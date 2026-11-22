"""Import archiwum spraw UDIP: kalendarium XLSX + pliki „Wniosek - <sygnatura>” i „Odpowiedź - <sygnatura>”.

Użycie:  python scripts/import_archive.py --dir "<katalog z wnioskami i odpowiedziami>" --calendar <kalendarium.xlsx>
Zakłada zamknięte, archiwalne sprawy wraz z odczytanymi i zaindeksowanymi dokumentami, aby wyszukiwarka
podobnych spraw i podpowiedź jednostek miały dane historyczne. Pliki źródłowe nie są modyfikowane.
"""
import sys, argparse, shutil, re, unicodedata
from pathlib import Path
project_root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(project_root/'backend' if (project_root/'backend').exists() else project_root))
from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal
from app.models import Case, Document, Unit, Event, uid
from app.services.calendar_import import preview
from app.services.documents import extract, digest
from app.services.domain import extract_questions, deadline_for
from app.services.ai import index_document

COORDINATOR='BKS'  # Biuro Komunikacji Społecznej koordynuje wnioski i podpisuje odpowiedzi — nie jest jednostką merytoryczną
KINDS=[('Wniosek','request'),('Odpowied','material'),('Kwerenda','material'),('Doprecyzowanie','material')]

def norm(text):return unicodedata.normalize('NFC',text)

def run(folder,calendar):
    rows=preview(Path(calendar).read_bytes())['rows']
    files=[p for p in Path(folder).iterdir() if p.suffix.lower() in ['.pdf','.docx','.doc','.txt']]
    with SessionLocal() as db:
        units=db.scalars(select(Unit)).all()
        for row in rows:
            ref=row['reference'].strip()
            c=db.scalar(select(Case).where(Case.reference==ref))
            if c and db.scalar(select(Document.id).where(Document.case_id==c.id).limit(1)):print('pominięto (sprawa ma dokumenty):',ref);continue
            if not c:
                received=row['received'];warnings=list(row['warnings'])
                if not received:print('pominięto (brak daty wpływu):',ref);continue
                deadline=row['deadline'] if row['deadline'] and row['deadline']>=received else deadline_for(received)
                answered=row['answered'] if row['answered'] and row['answered']>=received else None
                if row['answered'] and not answered:warnings.append('Data odpowiedzi z arkusza wcześniejsza niż wpływ — do weryfikacji')
                c=Case(reference=ref,title=row['title'] or ref,applicant=row['applicant'],received=received,original_deadline=deadline_for(received),deadline=deadline,answered=answered,owner=row['owner'],status='zakonczony' if answered else 'zarejestrowany',warnings=warnings+['Sprawa archiwalna z importu'],questions=[],units=[])
                db.add(c);db.flush();db.add(Event(case_id=c.id,type='calendar_imported',actor='import-archiwum',detail={'warnings':warnings}))
            matched=[p for p in files if ref in norm(p.name)]
            for path in sorted(matched):
                kind=next((k for prefix,k in KINDS if norm(path.name).startswith(prefix)),'material')
                ident=uid();target=settings.data_dir/'files'/(ident+path.suffix.lower());shutil.copyfile(path,target)
                try:text,pages,pdf_path=extract(target)
                except Exception as exc:print('  błąd odczytu',path.name,exc);continue
                d=Document(id=ident,case_id=c.id,name=path.name,kind=kind,path=str(target),pdf_path=pdf_path,sha256=digest(target),text=text,pages=pages,active=True,state='ready',metadata_={'archive_import':True,'ocr_used':any(p['ocr'] for p in pages)})
                db.add(d);db.flush()
                try:index_document(db,d);d.metadata_={**d.metadata_,'indexed':True}
                except (ValueError,ImportError,OSError):pass
                if kind=='request' and not c.questions:c.questions=extract_questions(text)
                if kind=='material':
                    # Jednostki, które przygotowały odpowiedź — źródło archiwalnych podpowiedzi.
                    c.units=sorted(set(c.units)|{u.id for u in units if u.id!=COORDINATOR and u.name.lower() in text.lower()})
                print('  ',ref,kind,path.name)
            db.commit();print('zaimportowano',ref,'jednostki:',c.units)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dir',required=True);parser.add_argument('--calendar',required=True)
    a=parser.parse_args();run(a.dir,a.calendar)
