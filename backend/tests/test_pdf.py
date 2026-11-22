from reportlab.pdfgen.canvas import Canvas
from pypdf import PdfReader
from PIL import Image
from app.services.documents import raster_redact,render_page,export_letter

def test_raster_export_removes_underlying_text_and_pixels(tmp_path):
    source=tmp_path/'source.pdf';c=Canvas(str(source),pagesize=(200,200));c.setAuthor('SECRET_METADATA');c.drawString(30,150,'SECRET_UNDER_MASK');c.showPage();c.save()
    out=tmp_path/'redacted.pdf';raster_redact(source,[{'page':1,'box':[.1,.15,.95,.3],'state':'accepted'}],out)
    reader=PdfReader(out)
    assert not reader.pages[0].extract_text()
    assert 'SECRET_METADATA' not in str(reader.metadata)
    assert '/Annots' not in reader.pages[0] and '/EmbeddedFiles' not in reader.trailer['/Root'].get('/Names',{})
    image=render_page(out,1,scale=2)
    assert image.getpixel((120,80))==(0,0,0)
    assert all(b'SECRET_UNDER_MASK' not in obj.get_data() for obj in reader.pages[0]['/Resources']['/XObject'].values() if hasattr(obj,'get_data'))

def test_rotated_page_masks_follow_visible_coordinates(tmp_path):
    from pypdf import PdfWriter
    source=tmp_path/'portrait.pdf';c=Canvas(str(source),pagesize=(200,300));c.drawString(20,200,'CONTROL');c.save()
    r=PdfReader(source);r.pages[0].rotate(90);writer=PdfWriter();writer.add_page(r.pages[0]);rotated=tmp_path/'rotated.pdf';writer.write(rotated)
    out=tmp_path/'out.pdf';raster_redact(rotated,[{'page':1,'box':[0,0,.5,.5],'state':'accepted'}],out)
    im=render_page(out,1,1)
    assert im.width==300 and im.height==200
    assert im.getpixel((20,20))==(0,0,0)

def test_clean_docx_has_no_tracked_source_data(tmp_path):
    import zipfile
    p=tmp_path/'letter.docx';export_letter('Treść po anonimizacji [DANE USUNIĘTE]','docx',p)
    with zipfile.ZipFile(p) as z:
        xml=z.read('word/document.xml')
        assert b'DANE USUNI' in xml
        assert b'<w:del' not in xml and b'<w:ins' not in xml
