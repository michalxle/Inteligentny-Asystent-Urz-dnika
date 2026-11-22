import time, traceback
from datetime import timedelta
from sqlalchemy import select, or_
from .db import SessionLocal
from .models import Job, Document, Case, Chunk, Event, now
from .services.documents import extract
from .services.domain import extract_questions
from .services.ai import index_document, generate


def execute(job_id):
    with SessionLocal() as db:
        job=db.get(Job,job_id)
        try:
            if job.kind=='document':
                doc=db.get(Document,job.target)
                from pathlib import Path
                text,pages,pdf_path=extract(Path(doc.path))
                doc.text=text;doc.pages=pages;doc.pdf_path=pdf_path;doc.state='ready'
                doc.metadata_={**doc.metadata_,'ocr_used':any(p['ocr'] for p in pages),'indexed':False}
                # Index vectors when available; lexical chunks remain usable before model setup.
                try:index_document(db,doc);doc.metadata_={**doc.metadata_,'indexed':True}
                except (ValueError,ImportError,OSError):
                    db.add_all([Chunk(document_id=doc.id,page=p['page'],text=p['text'][:16000]) for p in pages if p['text'].strip()])
                job.result={'document_id':doc.id,'questions':extract_questions(text),'warning':'Zweryfikuj OCR i metadane przed zatwierdzeniem.'}
            elif job.kind=='index':
                doc=db.get(Document,job.target);index_document(db,doc);doc.metadata_={**doc.metadata_,'indexed':True};job.result={'document_id':doc.id}
            elif job.kind=='draft':
                case=db.get(Case,job.target);draft=generate(db,case);job.result={'draft_id':draft.id};case.status='projekt_odpowiedzi'
                db.add(Event(case_id=case.id,type='draft_generated',actor='local-ai',detail={'draft_id':draft.id}))
            job.status='done';job.progress='Gotowe';job.lease_until=None;db.commit()
        except Exception as exc:
            db.rollback();job=db.get(Job,job_id);job.status='failed';job.progress='Przetwarzanie nie powiodło się'
            # Operational detail only; no source text or prompts are logged.
            job.result={'error':str(exc)[:400] if isinstance(exc,(ValueError,FileNotFoundError)) else f'{type(exc).__name__}: sprawdź diagnostykę lokalnych usług'}
            if job.kind=='document':
                doc=db.get(Document,job.target)
                if doc:doc.state='failed'
            job.lease_until=None;db.commit()

def run():
    while True:
        from .config import settings
        (settings.data_dir/"worker.heartbeat").touch()
        with SessionLocal() as db:
            job=db.scalar(select(Job).where(or_(Job.status=='queued',(Job.status=='running') & (Job.lease_until<now()))).order_by(Job.created).with_for_update(skip_locked=True).limit(1))
            if job:
                if job.attempts>=3:job.status='failed';job.result={'error':'Przekroczony limit prób'};db.commit();continue
                job.status='running';job.attempts+=1;job.lease_until=now()+timedelta(minutes=15);job.progress='Przetwarzanie lokalne';jid=job.id;db.commit()
            else:jid=None
        if jid:execute(jid)
        else:time.sleep(1)

if __name__=='__main__':run()
