import csv, io, os, subprocess, tempfile, hashlib, shutil
from pathlib import Path
from contextlib import closing
from functools import wraps
from threading import RLock
from PIL import ImageDraw
from pypdf import PdfReader
import pypdfium2 as pdfium
from docx import Document as WordDocument
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xml.sax.saxutils import escape
from ..config import settings

_pdf_lock=RLock()

def pdf_serialized(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        with _pdf_lock:return fn(*args,**kwargs)
    return wrapper

ALLOWED={'.pdf','.docx','.doc','.txt'}

def digest(path):
    with open(path,'rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def font_path():
    candidates=[Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),Path('/Library/Fonts/Arial Unicode.ttf'),Path('/System/Library/Fonts/Supplemental/Arial.ttf')]
    return next((p for p in candidates if p.exists()),None)

def word_to_pdf(path):
    with tempfile.TemporaryDirectory(dir=settings.data_dir/'tmp') as tmp:
        result=subprocess.run([settings.soffice,'-env:UserInstallation='+ (Path(tmp)/'profile').as_uri(),'--headless','--convert-to','pdf','--outdir',tmp,str(path)],capture_output=True,timeout=90)
        converted=Path(tmp)/(path.stem+'.pdf')
        if result.returncode or not converted.exists(): raise ValueError('Konwersja Word do PDF nie powiodła się')
        target=path.with_suffix('.converted.pdf'); shutil.copyfile(converted,target); return target

def _tesseract(image):
    with tempfile.TemporaryDirectory(dir=settings.data_dir/'tmp') as tmp:
        source=Path(tmp)/'page.png'; image.save(source)
        env={**os.environ,'TESSDATA_PREFIX':str(settings.tessdata_prefix)}
        r=subprocess.run(['tesseract',str(source),'stdout','-l','pol','-c','tessedit_create_tsv=1'],capture_output=True,timeout=90,env=env)
        if r.returncode: raise ValueError('Błąd lokalnego OCR')
        words=[]; lines={}
        # TSV Tesseracta nie używa cudzysłowów — cudzysłów w rozpoznanym wyrazie nie może łączyć wierszy.
        for row in csv.DictReader(io.StringIO(r.stdout.decode("utf-8")),delimiter="\t",quoting=csv.QUOTE_NONE):
            text=(row.get('text') or '').strip()
            if not text:continue
            left,top,width,height=[int(row[k]) for k in ['left','top','width','height']]
            try:conf=float(row.get('conf') or 0)
            except ValueError:conf=0.0
            words.append({'text':text,'conf':round(conf,1),'box':[left/image.width,top/image.height,(left+width)/image.width,(top+height)/image.height]})
            key=tuple(row[k] for k in ['block_num','par_num','line_num']);lines.setdefault(key,[]).append(text)
        confidence=sum(w['conf'] for w in words)/len(words) if words else 0.0
        return '\n'.join(' '.join(v) for v in lines.values()),words,confidence

def remove_grid(image):
    """Usuwa linie papieru w kratkę/liniowanego, które zakłócają OCR pisma odręcznego."""
    import numpy as np
    gray=np.array(image.convert('L'))
    dark=gray<170
    cleaned=gray.copy()
    cleaned[dark.mean(axis=1)>0.3,:]=255
    cleaned[:,dark.mean(axis=0)>0.3]=255
    cleaned=np.where(cleaned<170,0,255).astype('uint8')
    from PIL import Image
    return Image.fromarray(cleaned)

def ocr_image(image):
    if not (settings.tessdata_prefix/'pol.traineddata').exists(): raise ValueError('Brak polskiego modelu OCR. Uruchom scripts/setup_models.py')
    text,words,confidence=_tesseract(image)
    if confidence<60:
        # Druga próba po usunięciu siatki; wybieramy odczyt o wyższej pewności.
        try:
            second=_tesseract(remove_grid(image))
            if second[2]>confidence:text,words,confidence=second
        except Exception:pass
    return text,words

@pdf_serialized
def extract(path):
    suffix=path.suffix.lower(); pages=[]; pdf_path=None
    if suffix=='.txt':
        text=path.read_text(encoding='utf-8-sig');pages=[{'page':1,'text':text,'words':[],'ocr':False}]
    else:
        if suffix in ['.docx','.doc']:pdf_path=word_to_pdf(path)
        else:pdf_path=path
        reader=PdfReader(pdf_path)
        if reader.is_encrypted:raise ValueError('PDF zaszyfrowany — prześlij odblokowaną kopię')
        if len(reader.pages)>settings.max_pages:raise ValueError('Przekroczony limit stron')
        with closing(pdfium.PdfDocument(pdf_path)) as doc:
            for i,page in enumerate(reader.pages):
                text=page.extract_text() or ''; words=[]; ocr=False
                if len(text.strip())<30:
                    rendered=doc[i].render(scale=2).to_pil();text,words=ocr_image(rendered);ocr=True
                confidence=round(sum(w.get('conf',0) for w in words)/len(words),1) if words else None
                pages.append({'page':i+1,'text':text,'words':words,'ocr':ocr,'ocr_confidence':confidence})
    return '\n\n'.join(p['text'] for p in pages),pages,str(pdf_path) if pdf_path else None

@pdf_serialized
def render_page(pdf_path,page,scale=1.5):
    with closing(pdfium.PdfDocument(pdf_path)) as d:
        if page<1 or page>len(d):raise ValueError('Brak strony')
        p=d[page-1]; w,h=p.get_size()
        if w*h*scale*scale>settings.max_page_pixels:raise ValueError('Strona przekracza limit pikseli')
        return p.render(scale=scale).to_pil().convert('RGB')

@pdf_serialized
def raster_redact(pdf_path,masks,output):
    with closing(pdfium.PdfDocument(pdf_path)) as source:
        if len(source)>settings.max_pages:raise ValueError('Przekroczony limit stron')
        canvas=Canvas(str(output),pageCompression=1); canvas.setTitle('Kopia po anonimizacji');canvas.setAuthor('')
        for i in range(len(source)):
            page=source[i]; w,h=page.get_size(); scale=300/72
            if w*h*scale*scale>settings.max_page_pixels:raise ValueError('Strona przekracza limit pikseli')
            image=page.render(scale=scale).to_pil().convert('RGB');draw=ImageDraw.Draw(image)
            for mask in masks:
                if mask['page']!=i+1 or mask['state']!='accepted':continue
                x0,y0,x1,y1=mask['box']
                if not (0<=x0<x1<=1 and 0<=y0<y1<=1):raise ValueError('Niepoprawny obszar')
                draw.rectangle([max(0,int(x0*image.width)-2),max(0,int(y0*image.height)-2),min(image.width,int(x1*image.width)+2),min(image.height,int(y1*image.height)+2)],fill='black')
            canvas.setPageSize((w,h));canvas.drawImage(ImageReader(image),0,0,width=w,height=h);canvas.showPage()
        canvas.save()
    result=PdfReader(output)
    if len(result.pages)!=len(PdfReader(pdf_path).pages) or any((p.extract_text() or '').strip() for p in result.pages):raise ValueError('Walidacja kopii PDF nie powiodła się')
    return output

def export_letter(text,fmt,output):
    if fmt=='txt':output.write_text(text,encoding='utf-8')
    elif fmt in ['docx','doc']:
        d=WordDocument()
        for line in text.split('\n'):d.add_paragraph(line)
        d.core_properties.author='';d.core_properties.last_modified_by='';d.core_properties.title='Odpowiedź'
        if fmt=='docx':d.save(output)
        else:
            with tempfile.TemporaryDirectory(dir=settings.data_dir/'tmp') as tmp:
                src=Path(tmp)/'letter.docx';d.save(src)
                r=subprocess.run([settings.soffice,'-env:UserInstallation='+ (Path(tmp)/'profile').as_uri(),'--headless','--convert-to','doc:MS Word 97','--outdir',tmp,str(src)],capture_output=True,timeout=90)
                if r.returncode or not src.with_suffix('.doc').exists():raise ValueError('Błąd eksportu DOC')
                shutil.copyfile(src.with_suffix('.doc'),output)
    elif fmt=='pdf':
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import ParagraphStyle
        fp=font_path()
        if not fp:raise ValueError('Brak lokalnego fontu z polskimi znakami')
        if 'Polish' not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont('Polish',str(fp)))
        style=ParagraphStyle('letter',fontName='Polish',fontSize=11,leading=16)
        story=[]
        for line in text.split('\n'):story.extend([Paragraph(escape(line) or ' ',style),Spacer(1,5)])
        SimpleDocTemplate(str(output),author='',title='Odpowiedź').build(story)
    else:raise ValueError('Nieobsługiwany format')
    return output
