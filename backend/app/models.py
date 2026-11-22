from datetime import datetime, date, timezone
from uuid import uuid4
from sqlalchemy import String, Text, Date, DateTime, Integer, JSON, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from .db import Base

def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default='operator')

class Session(Base):
    __tablename__ = 'sessions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    csrf: Mapped[str] = mapped_column(String(64))
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Case(Base):
    __tablename__ = 'cases'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    reference: Mapped[str] = mapped_column(String(160), unique=True)
    title: Mapped[str] = mapped_column(Text)
    applicant: Mapped[str] = mapped_column(Text, default='')
    received: Mapped[date] = mapped_column(Date)
    original_deadline: Mapped[date] = mapped_column(Date)
    deadline: Mapped[date] = mapped_column(Date)
    answered: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner: Mapped[str] = mapped_column(String(120), default='')
    status: Mapped[str] = mapped_column(String(40), default='zarejestrowany')
    questions: Mapped[list] = mapped_column(JSON, default=list)
    units: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    delivery: Mapped[str] = mapped_column(Text, default='')
    version: Mapped[int] = mapped_column(Integer, default=1)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Unit(Base):
    __tablename__ = 'units'
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default='')

class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str | None] = mapped_column(ForeignKey('cases.id'), nullable=True, index=True)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30))
    unit_id: Mapped[str | None] = mapped_column(ForeignKey('units.id'), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text, default='')
    pages: Mapped[list] = mapped_column(JSON, default=list)
    metadata_: Mapped[dict] = mapped_column('metadata', JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(20), default='queued')
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Chunk(Base):
    __tablename__ = 'document_chunks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'), index=True)
    page: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(Vector(768), nullable=True)

class Draft(Base):
    __tablename__ = 'drafts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey('cases.id'), index=True)
    text: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    coverage: Mapped[list] = mapped_column(JSON, default=list)
    redactions: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    approved_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    case_version: Mapped[int] = mapped_column(Integer)
    sources: Mapped[dict] = mapped_column(JSON, default=dict)
    model: Mapped[str] = mapped_column(Text, default='manual')
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class DraftVersion(Base):
    __tablename__ = 'draft_versions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    draft_id: Mapped[str] = mapped_column(ForeignKey('drafts.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    redactions: Mapped[list] = mapped_column(JSON)
    author: Mapped[str] = mapped_column(String(120))
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class AttachmentReview(Base):
    __tablename__ = 'attachment_reviews'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'), primary_key=True)
    document_version: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    masks: Mapped[list] = mapped_column(JSON, default=list)
    reviewed_pages: Mapped[list] = mapped_column(JSON, default=list)

class Export(Base):
    __tablename__ = 'exports'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str | None] = mapped_column(ForeignKey('cases.id'), nullable=True)
    draft_id: Mapped[str | None] = mapped_column(ForeignKey('drafts.id'), nullable=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey('documents.id'), nullable=True)
    version: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    format: Mapped[str] = mapped_column(String(10))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Event(Base):
    __tablename__ = 'case_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str | None] = mapped_column(ForeignKey('cases.id'), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(60))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    actor: Mapped[str] = mapped_column(String(120))
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Job(Base):
    __tablename__ = 'processing_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(30))
    target: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), default='queued', index=True)
    progress: Mapped[str] = mapped_column(Text, default='Oczekuje')
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
