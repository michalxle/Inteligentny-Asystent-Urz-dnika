import sys
from pathlib import Path
project_root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(project_root/'backend' if (project_root/'backend').exists() else project_root))
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Document, Job
with SessionLocal() as db:
    for d in db.scalars(select(Document).where(Document.state=='ready')).all():db.add(Job(kind='index',target=d.id))
    db.commit()
print('Zlecono lokalne indeksowanie gotowych dokumentów.')
