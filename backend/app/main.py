import hashlib, secrets, io, zipfile, re, time, shutil
from pathlib import Path
from datetime import date, timedelta
from urllib.parse import urlsplit
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, text, func
from sqlalchemy.orm import Session as DBSession
from argon2.exceptions import VerifyMismatchError, InvalidHashError
import httpx
from .config import settings
from .db import get_db
from .models import User, Session, Case, Unit, Document, Draft, DraftVersion, Event, Job, AttachmentReview, Export, Chunk, uid, now
from .auth import current_user, require_admin, hasher, token_hash
from .services.domain import today, deadline_for, deadline_state, add_months, format_date, extract_questions, detect_pii, merge_redactions, STOPWORDS, remap_redactions, clean_text, suggest_case, STATUSES
from .services.documents import ALLOWED, digest, render_page, raster_redact, export_letter
from .services.ai import search

app=FastAPI(title='Inteligentny Asystent Urzędnika',version='0.1.0')
login_attempts={}

@app.on_event('startup')
def preload_models():
    # Pierwsze wczytanie polskiego NER trwa kilkadziesiąt sekund; nie może blokować zapisu pisma.
    import threading
    def load():
        try:
            from .services.ner import nlp
            nlp()
        except Exception:pass
    threading.Thread(target=load,daemon=True).start()

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Login(Strict):username:str; password:str
class Question(Strict):id:str; text:str=Field(max_length=4000); status:str='brak_materialu'
class CaseInput(Strict):
    reference:str=Field(min_length=1,max_length=160)
    title:str=Field(min_length=1,max_length=2000)
    applicant:str=Field(default='',max_length=2000)
    received:date
    owner:str=Field(default='',max_length=120)
    questions:list[Question]=Field(default_factory=list,max_length=30)
    delivery:str=''
class CasePatch(CaseInput):version:int; units:list[str]=Field(default_factory=list)
class Confirm(Strict):
    version:int
    text:str=Field(max_length=400000)
    metadata:dict=Field(default_factory=dict)
    case:CaseInput|None=None
class DraftPatch(Strict):version:int; text:str=Field(max_length=100000); coverage:list[dict]=Field(default_factory=list)
class Span(Strict):
    start:int=Field(ge=0); end:int=Field(gt=0)
    state:Literal['proposed','accepted','rejected']='proposed'
    category:str='ręcznie'; reason:str='Decyzja operatora'
class Spans(Strict):version:int; redactions:list[Span]=Field(max_length=1000)
class Approve(Strict):version:int; confirmed:bool
class Deadline(Strict):version:int; deadline:date; reason:str=Field(min_length=5); notified_on:date; basis:str=Field(min_length=3)
class Sent(Strict):version:int; answered:date; delivery:str=Field(min_length=2)
class Note(Strict):type:Literal['note','material_requested','clarification','query']='note'; text:str=Field(min_length=1,max_length=5000)
class Mask(Strict):
    page:int=Field(ge=1)
    box:tuple[float,float,float,float]
    state:Literal['proposed','accepted','rejected']='accepted'
    category:str='obszar'
class Review(Strict):version:int; masks:list[Mask]=Field(max_length=1000); reviewed_pages:list[int]
class Package(Strict):letter_export_id:str; attachment_export_ids:list[str]=Field(max_length=50)


def obj(db,model,ident,lock=False):
    result=db.scalar(select(model).where(model.id==ident).with_for_update()) if lock else db.get(model,ident)
    if not result:raise HTTPException(404,'Nie znaleziono zasobu')
    return result

def revision(item,version):
    if item.version!=version:raise HTTPException(409,'Dokument został zmieniony. Odśwież widok i sprawdź aktualną wersję.')

def log(db,user,case_id,type,detail=None):db.add(Event(actor=user.username,case_id=case_id,type=type,detail=detail or {}))
def enqueue(db,kind,target):
    existing=db.scalar(select(Job).where(Job.kind==kind,Job.target==target,Job.status.in_(['queued','running'])))
    if existing:return existing
    job=Job(kind=kind,target=target);db.add(job);db.flush();return job

def case_dict(c):
    return {k:getattr(c,k) for k in ['id','reference','title','applicant','received','original_deadline','deadline','answered','owner','status','questions','units','warnings','version','delivery']}|deadline_state(c)
def doc_dict(d):return {k:getattr(d,k) for k in ['id','case_id','name','kind','unit_id','text','active','version','state','created']}|{'pages':len(d.pages),'metadata':d.metadata_,'has_pdf':bool(d.pdf_path)}
def draft_dict(d):return {k:getattr(d,k) for k in ['id','case_id','text','evidence','coverage','redactions','version','approved_version','case_version','model','sources']}
def job_dict(j):return {k:getattr(j,k) for k in ['id','kind','target','status','progress','result','attempts']}

def assert_draft_current(db,d):
    c=obj(db,Case,d.case_id)
    if d.case_version!=c.version:raise HTTPException(409,'Sprawa zmieniła się od przygotowania pisma. Zapisz ponownie i zweryfikuj odpowiedź.')
    for ident,version in d.sources.items():
        doc=db.get(Document,ident)
        if not doc or not doc.active or doc.version!=version:raise HTTPException(409,'Materiał źródłowy zmienił się — przygotuj nowy projekt.')

@app.middleware('http')
async def headers(request,call_next):
    if request.method=='POST' and request.url.path=='/api/auth/login':
        origin=request.headers.get('origin')
        if origin and origin not in settings.trusted_origins and urlsplit(origin).netloc!=request.headers.get('host'):return Response('Niedozwolone źródło żądania',status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Frame-Options']='DENY';response.headers['Cache-Control']='no-store'
    return response

@app.post('/api/auth/login')
def login(body:Login,request:Request,response:Response,db:DBSession=Depends(get_db)):
    key=(request.client.host if request.client else '')+':'+body.username
    attempts=[x for x in login_attempts.get(key,[]) if time.monotonic()-x<300]
    if len(attempts)>=8:raise HTTPException(429,'Zbyt wiele prób. Spróbuj za kilka minut.')
    user=db.scalar(select(User).where(User.username==body.username))
    try:valid=user is not None and hasher.verify(user.password_hash,body.password)
    except (VerifyMismatchError,InvalidHashError):valid=False
    if not valid:
        login_attempts[key]=attempts+[time.monotonic()];raise HTTPException(401,'Niepoprawny login lub hasło')
    login_attempts.pop(key,None)
    old=request.cookies.get('umb_session')
    if old:
        prior=db.get(Session,token_hash(old))
        if prior:db.delete(prior)
    token=secrets.token_urlsafe(32);csrf=secrets.token_hex(32)
    db.add(Session(id=token_hash(token),csrf=csrf,user_id=user.id,expires=now()+timedelta(hours=8)));db.commit()
    response.set_cookie('umb_session',token,httponly=True,secure=settings.cookie_secure,samesite='strict',max_age=28800,path='/')
    return {'username':user.username,'role':user.role,'csrf':csrf}

@app.get('/api/auth/me')
def me(request:Request,user=Depends(current_user)):return {'username':user.username,'role':user.role,'csrf':request.state.auth_session.csrf}
@app.post('/api/auth/logout')
def logout(request:Request,response:Response,user=Depends(current_user),db:DBSession=Depends(get_db)):
    db.delete(db.get(Session,request.state.auth_session.id));db.commit();response.delete_cookie('umb_session');return {'ok':True}

@app.get('/health/live')
def live():return {'status':'ok'}
@app.get('/api/diagnostics')
def diagnostics(user=Depends(current_user),db:DBSession=Depends(get_db)):
    db.execute(text('SELECT 1'));model=False;ollama=False
    try:
        r=httpx.get(settings.ollama_url+'/api/tags',timeout=3,trust_env=False);r.raise_for_status();ollama=True
        model=any(m['name'].split(':')[0]==settings.ollama_model.split(':')[0] for m in r.json().get('models',[]))
    except (httpx.HTTPError,ValueError):pass
    checks={'database':True,'ollama':ollama,'model':model,'embeddings':(settings.embedding_model/'config.json').exists(),'ocr':shutil.which('tesseract') is not None and (settings.tessdata_prefix/'pol.traineddata').exists(),'word':shutil.which(settings.soffice) is not None,'ner':(settings.data_dir/'models/pl_core_news_lg/meta.json').exists()}
    latest=db.scalar(select(Job).where(Job.status=='running').order_by(Job.created.desc()))
    checks['worker']=bool(latest) or (settings.data_dir/'worker.heartbeat').exists() and time.time()-(settings.data_dir/'worker.heartbeat').stat().st_mtime<30
    return {'checks':checks,'ready':all(checks.values()),'model':settings.ollama_model,'generation':'local-only','date':today(),'limits':{'upload_mb':settings.max_upload_mb,'pages':settings.max_pages}}
@app.get('/health/ready')
def ready(db:DBSession=Depends(get_db)):
    try:db.execute(text('SELECT 1'))
    except Exception:raise HTTPException(503,'Baza danych niedostępna')
    state=diagnostics(user=None,db=db)
    if not state['ready']:raise HTTPException(503,'Usługi lokalne nie są jeszcze gotowe')
    return {'status':'ready'}

@app.get('/api/cases')
def cases(user=Depends(current_user),db:DBSession=Depends(get_db)):
    return [case_dict(c) for c in db.scalars(select(Case).order_by(Case.received,Case.reference)).all()]
@app.post('/api/cases',status_code=201)
def create_case(body:CaseInput,user=Depends(current_user),db:DBSession=Depends(get_db)):
    if db.scalar(select(Case).where(Case.reference==body.reference)):raise HTTPException(409,'Sygnatura już istnieje')
    c=Case(**body.model_dump(exclude={'questions'}),questions=[q.model_dump() for q in body.questions],original_deadline=deadline_for(body.received),deadline=deadline_for(body.received))
    db.add(c);db.flush();log(db,user,c.id,'case_created');db.commit();return case_dict(c)
@app.get('/api/cases/{ident}')
def get_case(ident:str,user=Depends(current_user),db:DBSession=Depends(get_db)):
    c=obj(db,Case,ident)
    return {'case':case_dict(c),'exports':[{'id':e.id,'draft_id':e.draft_id,'document_id':e.document_id,'format':e.format,'approved':e.approved,'version':e.version} for e in db.scalars(select(Export).where(Export.case_id==ident).order_by(Export.created.desc())).all()],'documents':[doc_dict(d) for d in db.scalars(select(Document).where(Document.case_id==ident).order_by(Document.created)).all()],'drafts':[draft_dict(d) for d in db.scalars(select(Draft).where(Draft.case_id==ident).order_by(Draft.created.desc())).all()],'events':[{'id':e.id,'type':e.type,'detail':e.detail,'actor':e.actor,'created':e.created} for e in db.scalars(select(Event).where(Event.case_id==ident).order_by(Event.created.desc())).all()]}
@app.patch('/api/cases/{ident}')
def edit_case(ident:str,body:CasePatch,user=Depends(current_user),db:DBSession=Depends(get_db)):
    c=obj(db,Case,ident,True);revision(c,body.version)
    duplicate=db.scalar(select(Case).where(Case.reference==body.reference,Case.id!=ident))
    if duplicate:raise HTTPException(409,'Sygnatura już istnieje')
    for u in body.units:obj(db,Unit,u)
    if len({q.id for q in body.questions})!=len(body.questions):raise HTTPException(422,'Powtórzone identyfikatory pytań')
    if c.answered and body.received>c.answered:raise HTTPException(422,'Data wpływu nie może być późniejsza niż udostępnienie informacji')
    if body.received!=c.received:
        automatic=c.deadline==c.original_deadline and not db.scalar(select(Event.id).where(Event.case_id==ident,Event.type=='deadline_changed').limit(1))
        if not automatic and body.received>c.deadline:raise HTTPException(422,'Data wpływu nie może być późniejsza niż odnotowany termin')
        c.original_deadline=deadline_for(body.received)
        if automatic:c.deadline=c.original_deadline
    content={'reference','title','applicant','received','questions'}
    new=body.model_dump(exclude={'version'})
    changed=any((getattr(c,k) if k!='questions' else [{'id':q['id'],'text':q['text']} for q in c.questions])!=(new[k] if k!='questions' else [{'id':q['id'],'text':q['text']} for q in new[k]]) for k in content)
    for key,value in new.items():setattr(c,key,value)
    old_version=c.version;c.version+=1
    if not changed:
        # Prowadzący, jednostki i forma udostępnienia nie zmieniają treści zatwierdzonego pisma.
        for d in db.scalars(select(Draft).where(Draft.case_id==ident,Draft.case_version==old_version)):d.case_version=c.version
    if c.answered:c.status='zakonczony'
    elif changed and c.status=='gotowy_do_eksportu':c.status='projekt_odpowiedzi'
    elif c.status=='zarejestrowany' and c.units:c.status='oczekuje_na_materialy'
    log(db,user,ident,'case_updated');db.commit();return case_dict(c)
@app.post('/api/cases/{ident}/events')
def event(ident:str,body:Note,user=Depends(current_user),db:DBSession=Depends(get_db)):
    c=obj(db,Case,ident,True)
    # Zakończonej sprawy notatka nie otwiera ponownie.
    if not c.answered and body.type=='material_requested' and c.status in ['do_weryfikacji','zarejestrowany','oczekuje_na_materialy']:c.status='oczekuje_na_materialy'
    if not c.answered and body.type=='query' and c.status not in ['gotowy_do_eksportu']:c.status='kwerenda'
    log(db,user,ident,body.type,{'text':body.text});db.commit();return {'ok':True}
@app.post('/api/cases/{ident}/deadline-events')
def deadline(ident:str,body:Deadline,user=Depends(current_user),db:DBSession=Depends(get_db)):
    c=obj(db,Case,ident,True);revision(c,body.version)
    if body.deadline<c.received or body.deadline>add_months(c.received,2):raise HTTPException(422,'Termin poza zakresem od wpływu do dwóch miesięcy')
    if body.notified_on>today() or body.notified_on<c.received:raise HTTPException(422,'Sprawdź datę powiadomienia')
    if body.notified_on>c.deadline:raise HTTPException(422,'Powiadomienie po dotychczasowym terminie — wymaga wyjaśnienia poza tym trybem')
    log(db,user,ident,'deadline_changed',{'old':c.deadline.isoformat(),'extension_days':(body.deadline-c.original_deadline).days,**body.model_dump(mode='json')})
    old_version=c.version;c.deadline=body.deadline;c.version+=1
    # Termin nie wpływa na treść pisma — aktualne projekty pozostają zgodne ze sprawą.
    for d in db.scalars(select(Draft).where(Draft.case_id==ident,Draft.case_version==old_version)):d.case_version=c.version
    if not c.answered and body.deadline>c.original_deadline and c.status in ['do_weryfikacji','zarejestrowany','oczekuje_na_materialy']:c.status='kwerenda'
    db.commit();return case_dict(c)
@app.post('/api/cases/{ident}/sent')
def sent(ident:str,body:Sent,user=Depends(current_user),db:DBSession=Depends(get_db)):
    c=obj(db,Case,ident,True);revision(c,body.version)
    if not c.received<=body.answered<=today():raise HTTPException(422,'Niepoprawna data udostępnienia')
    # Recording delivery changes workflow, not the verified contents of the letter.
    for d in db.scalars(select(Draft).where(Draft.case_id==ident,Draft.case_version==c.version)):
        d.case_version=c.version+1
    c.answered=body.answered;c.delivery=body.delivery;c.status='zakonczony';c.version+=1;log(db,user,ident,'manually_marked_sent',body.model_dump(mode='json'));db.commit();return case_dict(c)
@app.get('/api/units')
def units(user=Depends(current_user),db:DBSession=Depends(get_db)):return [{'id':u.id,'name':u.name,'description':u.description,'source':u.source} for u in db.scalars(select(Unit)).all()]
STOP=STOPWORDS
def _terms(text):return {w.lower() for w in re.findall(r'[^\W\d_]{4,}',text)}-STOP
@app.post('/api/cases/{ident}/unit-suggestions')
def unit_suggestions(ident:str,user=Depends(current_user),db:DBSession=Depends(get_db)):
    c=obj(db,Case,ident);query=c.title+' '+' '.join(q['text'] for q in c.questions);terms=_terms(query)
    scores={};reasons={}
    for u in db.scalars(select(Unit)).all():
        vocabulary={w.lower() for w in re.findall(r'[^\W\d_]{4,}',u.name+' '+u.description)}
        # Dopasowanie rdzenia: wspólny przedrostek co najmniej 5 liter (odmiana polskich wyrazów).
        matches=sorted({w for w in terms if any(len(v)>=5 and len(w)>=5 and (w[:max(5,min(len(w),len(v))-3)]==v[:max(5,min(len(w),len(v))-3)]) for v in vocabulary)})
        if matches:scores[u.id]=len(matches);reasons[u.id]=['kompetencje: '+', '.join(matches[:6])]
    # Archiwalne przypisania: jednostki, które odpowiadały w podobnych sprawach.
    for r in search(db,query,ident,True)['results'][:5]:
        if not r['case_id']:continue
        past=db.get(Case,r['case_id'])
        for u in set(past.units or [])|({r['unit_id']} if r['unit_id'] else set()):
            scores[u]=scores.get(u,0)+1.5;reasons.setdefault(u,[]).append('podobna sprawa '+past.reference)
    units={u.id:u for u in db.scalars(select(Unit)).all()}
    result=[{'id':k,'name':units[k].name,'reason':'; '.join(dict.fromkeys(reasons[k])).capitalize(),'score':round(v,1)} for k,v in scores.items() if k in units]
    return sorted(result,key=lambda r:r['score'],reverse=True)[:4]
@app.get('/api/cases/{ident}/similar')
def similar(ident:str,all_archive:bool=False,user=Depends(current_user),db:DBSession=Depends(get_db)):
    c=obj(db,Case,ident);return search(db,c.title+' '+' '.join(q['text'] for q in c.questions),ident,all_archive)

async def upload_file(file,kind,case_id,unit_id,db,user):
    name=Path(file.filename or '').name;suffix=Path(name).suffix.lower()
    if suffix not in ALLOWED:raise HTTPException(415,'Obsługiwane pliki: PDF, DOCX, DOC, TXT')
    content=await file.read(settings.max_upload_mb*1024*1024+1)
    if len(content)>settings.max_upload_mb*1024*1024:raise HTTPException(413,'Plik jest za duży')
    if not content:raise HTTPException(422,'Plik jest pusty')
    valid=(suffix=='.pdf' and content.startswith(b'%PDF-')) or (suffix=='.docx' and content.startswith(b'PK')) or (suffix=='.doc' and content.startswith(bytes.fromhex('d0cf11e0a1b11ae1'))) or suffix=='.txt'
    if not valid:raise HTTPException(415,'Typ pliku nie zgadza się z zawartością')
    if suffix=='.docx':
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                if sum(i.file_size for i in z.infolist())>100*1024*1024:raise ValueError()
                if any('vbaProject' in n for n in z.namelist()):raise ValueError()
        except (ValueError,zipfile.BadZipFile):raise HTTPException(415,'Niepoprawny lub niedozwolony dokument Word')
    sha=hashlib.sha256(content).hexdigest()
    duplicate_query=select(Document).where(Document.sha256==sha,Document.kind==kind)
    if kind!='request':duplicate_query=duplicate_query.where(Document.case_id==case_id)
    # Prefer a registered request to an abandoned upload of the same file.
    existing=db.scalar(duplicate_query.order_by(Document.case_id.is_(None),Document.created).limit(1))
    if existing and existing.state=='failed':
        # Ponowna próba odczytu tego samego pliku (np. po naprawie OCR) zamiast trwałej blokady.
        existing.state='queued';existing.name=name;job=enqueue(db,'document',existing.id);log(db,user,existing.case_id,'document_retry',{'document_id':existing.id});db.commit()
        return {'document':doc_dict(existing),'job':job_dict(job),'duplicate':False}
    if existing:return {'document':doc_dict(existing),'job':None,'duplicate':True}
    ident=uid();path=settings.data_dir/'files'/(ident+suffix);path.write_bytes(content)
    d=Document(id=ident,case_id=case_id,unit_id=unit_id,name=name,kind=kind,path=str(path),sha256=sha)
    db.add(d);db.flush();job=enqueue(db,'document',d.id);log(db,user,case_id,'document_uploaded',{'document_id':ident,'kind':kind});db.commit()
    return {'document':doc_dict(d),'job':job_dict(job),'duplicate':False}

@app.post('/api/imports',status_code=202)
async def imports(file:UploadFile=File(...),user=Depends(current_user),db:DBSession=Depends(get_db)):return await upload_file(file,'request',None,None,db,user)
@app.get('/api/imports/{ident}')
def get_import(ident:str,user=Depends(current_user),db:DBSession=Depends(get_db)):
    d=obj(db,Document,ident);jobs=db.scalars(select(Job).where(Job.target==ident).order_by(Job.created.desc())).all()
    questions=extract_questions(d.text)
    # Propozycja danych do rejestru — urzędnik sprawdza i akceptuje je w formularzu.
    suggested=suggest_case(d.text,questions,set(db.scalars(select(Case.reference)).all()),today()) if d.state=='ready' else None
    return {'document':doc_dict(d),'questions':questions,'jobs':[job_dict(j) for j in jobs],'suggested':suggested}
@app.get('/api/deadline-preview')
def deadline_preview(received:date,user=Depends(current_user)):
    return {'deadline':deadline_for(received).isoformat()}
@app.post('/api/imports/{ident}/confirm')
def confirm(ident:str,body:Confirm,user=Depends(current_user),db:DBSession=Depends(get_db)):
    d=obj(db,Document,ident,True);revision(d,body.version)
    if d.state!='ready':raise HTTPException(409,'Poczekaj na zakończenie odczytu')
    if d.kind=='knowledge' and user.role!='admin':raise HTTPException(403,'Tylko administrator zatwierdza bazę wiedzy')
    if d.kind=='request' and d.case_id and body.case:raise HTTPException(409,'Ten wniosek jest już przypisany do sprawy. Otwórz istniejącą sprawę.')
    if d.case_id is None and d.kind=='request':
        if not body.case:raise HTTPException(422,'Uzupełnij dane sprawy')
        existing_case=db.scalar(select(Case).where(Case.reference==body.case.reference))
        if existing_case:
            # Sprawa z kalendarium bez pliku wniosku: dołączamy wniosek zamiast odrzucać rejestrację.
            if db.scalar(select(Document.id).where(Document.case_id==existing_case.id,Document.kind=='request').limit(1)):raise HTTPException(409,'Sygnatura już istnieje i ma przypisany wniosek')
            d.case_id=existing_case.id
            if not existing_case.questions:existing_case.questions=[q.model_dump() for q in body.case.questions]
            log(db,user,existing_case.id,'request_attached',{'document_id':d.id})
        else:
            c=Case(**body.case.model_dump(exclude={'questions'}),questions=[q.model_dump() for q in body.case.questions],original_deadline=deadline_for(body.case.received),deadline=deadline_for(body.case.received));db.add(c);db.flush();d.case_id=c.id;log(db,user,c.id,'case_created',{'document_id':d.id})
    if d.case_id:
        c=obj(db,Case,d.case_id,True);c.version+=1
    d.text=body.text;d.version+=1;d.metadata_={k:v for k,v in {**d.metadata_,**body.metadata}.items() if k!='deactivated'};d.active=True
    # Corrected transcription is indexed, while page images and their locations remain original.
    d.pages=[{k:v for k,v in p.items() if k!='index_text'} for p in d.pages]
    if body.text!='\n\n'.join(p['text'] for p in d.pages):d.pages=[{**p,'index_text':body.text if i==0 else ''} for i,p in enumerate(d.pages)]
    enqueue(db,'index',d.id);log(db,user,d.case_id,'document_confirmed',{'document_id':d.id,'version':d.version});db.commit();return doc_dict(d)
@app.post('/api/cases/{ident}/documents',status_code=202)
async def upload_material(ident:str,file:UploadFile=File(...),kind:Literal['material','attachment']='material',unit_id:str|None=None,user=Depends(current_user),db:DBSession=Depends(get_db)):
    obj(db,Case,ident)
    if unit_id:obj(db,Unit,unit_id)
    return await upload_file(file,kind,ident,unit_id,db,user)
@app.get('/api/knowledge/documents')
def knowledge(user=Depends(current_user),db:DBSession=Depends(get_db)):return [doc_dict(d) for d in db.scalars(select(Document).where(Document.kind=='knowledge').order_by(Document.created.desc())).all()]
@app.post('/api/knowledge/documents',status_code=202)
async def knowledge_upload(file:UploadFile=File(...),user=Depends(require_admin),db:DBSession=Depends(get_db)):return await upload_file(file,'knowledge',None,None,db,user)
@app.post('/api/knowledge/documents/{ident}/activate')
def activate(ident:str,body:Confirm,user=Depends(require_admin),db:DBSession=Depends(get_db)):return confirm(ident,body,user,db)
@app.post('/api/knowledge/documents/{ident}/deactivate')
def deactivate(ident:str,user=Depends(require_admin),db:DBSession=Depends(get_db)):
    d=obj(db,Document,ident,True)
    if d.kind!='knowledge':raise HTTPException(422,'To nie jest dokument wiedzy')
    d.active=False;d.version+=1;d.metadata_={**d.metadata_,'deactivated':today().isoformat()};log(db,user,None,'knowledge_deactivated',{'id':ident});db.commit();return doc_dict(d)
@app.get('/api/jobs/{ident}')
def job(ident:str,user=Depends(current_user),db:DBSession=Depends(get_db)):return job_dict(obj(db,Job,ident))
@app.get('/api/jobs')
def jobs(user=Depends(current_user),db:DBSession=Depends(get_db)):return [job_dict(j) for j in db.scalars(select(Job).order_by(Job.created.desc()).limit(30)).all()]

@app.post('/api/cases/{ident}/drafts',status_code=202)
def generate_draft(ident:str,user=Depends(current_user),db:DBSession=Depends(get_db)):
    c=obj(db,Case,ident,True)
    if not c.questions:raise HTTPException(422,'Dodaj pytania z wniosku')
    j=enqueue(db,'draft',ident);db.commit();return job_dict(j)
@app.post('/api/cases/{ident}/manual-drafts',status_code=201)
def manual_draft(ident:str,user=Depends(current_user),db:DBSession=Depends(get_db)):
    c=obj(db,Case,ident);d=Draft(case_id=ident,case_version=c.version,text=f'Bydgoszcz, {format_date(today())}\nZnak sprawy: {c.reference}\n\nSzanowni Państwo,\n\nw odpowiedzi na wniosek z dnia {format_date(c.received)} o udostępnienie informacji publicznej przedstawiam poniższe informacje.\n\n'+'\n\n'.join(f'Ad {i+1}. [Do uzupełnienia: {q["text"]}]' for i,q in enumerate(c.questions))+'\n\nZ poważaniem\n[miejsce na podpis upoważnionej osoby]',coverage=[{'question_id':q['id'],'source_ids':[],'missing':['Brak odpowiedzi'],'reviewed':False} for q in c.questions])
    d.redactions=detect_pii(d.text)
    db.add(d);db.flush();db.add(DraftVersion(draft_id=d.id,version=1,text=d.text,redactions=d.redactions,author=user.username));log(db,user,ident,'manual_draft_created');db.commit();return draft_dict(d)
@app.patch('/api/drafts/{ident}')
def save_draft(ident:str,body:DraftPatch,user=Depends(current_user),db:DBSession=Depends(get_db)):
    d=obj(db,Draft,ident,True);revision(d,body.version);c=obj(db,Case,d.case_id)
    expected={q['id'] for q in c.questions}
    if {a.get('question_id') for a in body.coverage}!=expected:raise HTTPException(422,'Sprawdź pokrycie wszystkich pytań')
    # Decyzje anonimizacji przechodzą na poprawioną treść; nowe fragmenty są automatycznie proponowane do oceny.
    kept=remap_redactions(d.text,body.text,d.redactions)
    d.redactions=merge_redactions(body.text,kept,detect_pii(body.text,kept))
    d.text=body.text;d.coverage=body.coverage;d.version+=1;d.approved_version=None;d.case_version=c.version
    db.add(DraftVersion(draft_id=d.id,version=d.version,text=d.text,redactions=d.redactions,author=user.username));c.status='zakonczony' if c.answered else 'projekt_odpowiedzi';log(db,user,c.id,'draft_edited',{'id':ident,'version':d.version});db.commit();return draft_dict(d)
@app.post('/api/drafts/{ident}/redaction-scan')
def redaction_scan(ident:str,user=Depends(current_user),db:DBSession=Depends(get_db)):
    d=obj(db,Draft,ident,True)
    # A rescan must preserve manual masks and previous decisions on the same text.
    d.redactions=merge_redactions(d.text,d.redactions,detect_pii(d.text,d.redactions))
    d.version+=1;d.approved_version=None;db.commit();return draft_dict(d)
@app.patch('/api/drafts/{ident}/redactions')
def redactions(ident:str,body:Spans,user=Depends(current_user),db:DBSession=Depends(get_db)):
    d=obj(db,Draft,ident,True);revision(d,body.version)
    for r in body.redactions:
        if r.end>len(d.text) or r.end<=r.start:raise HTTPException(422,'Niepoprawny zakres')
    d.redactions=[r.model_dump() for r in body.redactions];d.version+=1;d.approved_version=None;log(db,user,d.case_id,'redactions_updated',{'id':ident,'count':len(body.redactions)});db.commit();return draft_dict(d)
@app.post('/api/drafts/{ident}/approve')
def approve_draft(ident:str,body:Approve,user=Depends(current_user),db:DBSession=Depends(get_db)):
    d=obj(db,Draft,ident,True);revision(d,body.version);assert_draft_current(db,d)
    if not body.confirmed or not d.coverage or any(not a.get('reviewed') or a.get('missing') for a in d.coverage):raise HTTPException(422,'Sprawdź kompletność i rozwiąż wszystkie braki')
    if any(r['state']=='proposed' for r in d.redactions):raise HTTPException(422,'Rozpatrz wszystkie propozycje anonimizacji')
    if '[Do uzupełnienia:' in d.text or 'DO UZUPEŁNIENIA:' in d.text:raise HTTPException(422,'W piśmie pozostały znaczniki braków')
    d.approved_version=d.version;c=obj(db,Case,d.case_id);c.status='zakonczony' if c.answered else 'gotowy_do_eksportu';log(db,user,d.case_id,'draft_approved',{'id':ident,'version':d.version});db.commit();return draft_dict(d)
@app.post('/api/drafts/{ident}/exports')
def letter_export(ident:str,format:Literal['txt','docx','pdf','doc']='pdf',user=Depends(current_user),db:DBSession=Depends(get_db)):
    d=obj(db,Draft,ident,True);assert_draft_current(db,d)
    if d.approved_version!=d.version:raise HTTPException(409,'Zatwierdź aktualną wersję pisma')
    eid=uid();path=settings.data_dir/'exports'/(eid+'.'+format)
    try:export_letter(clean_text(d.text,d.redactions),format,path)
    except (ValueError,TimeoutError) as exc:raise HTTPException(422,str(exc))
    e=Export(id=eid,case_id=d.case_id,draft_id=d.id,version=d.version,path=str(path),sha256=digest(path),format=format,approved=True);db.add(e);log(db,user,d.case_id,'letter_exported',{'export_id':eid,'format':format});db.commit();return {'id':eid,'url':'/api/exports/'+eid,'format':format}

@app.get('/api/documents/{ident}/pages/{page}')
def page_image(ident:str,page:int,user=Depends(current_user),db:DBSession=Depends(get_db)):
    d=obj(db,Document,ident)
    if not d.pdf_path:raise HTTPException(422,'Dokument nie ma podglądu PDF')
    try:image=render_page(d.pdf_path,page)
    except ValueError as exc:raise HTTPException(422,str(exc))
    out=io.BytesIO();image.save(out,format='PNG');return Response(out.getvalue(),media_type='image/png')
@app.get('/api/documents/{ident}/review')
def document_review(ident:str,user=Depends(current_user),db:DBSession=Depends(get_db)):
    d=obj(db,Document,ident)
    review=db.get(AttachmentReview,ident)
    return {'document':doc_dict(d),'review':{'version':review.version if review else 0,'masks':review.masks if review else [],'reviewed_pages':review.reviewed_pages if review else []},'pages':[{'page':p['page'],'text':p['text'],'words':p['words'],'ocr':p['ocr']} for p in d.pages],'exports':[{'id':e.id,'approved':e.approved,'version':e.version,'current':bool(review and review.document_version==d.version and e.version==review.version),'url':'/api/exports/'+e.id} for e in db.scalars(select(Export).where(Export.document_id==ident).order_by(Export.created.desc())).all()]}
@app.get('/api/documents/{ident}/pages/{page}/proposals')
def page_proposals(ident:str,page:int,user=Depends(current_user),db:DBSession=Depends(get_db)):
    """Propozycje obszarów do zamaskowania na skanie: reguły i NER na słowach OCR z położeniem."""
    d=obj(db,Document,ident)
    if page<1 or page>len(d.pages):raise HTTPException(404,'Brak strony')
    words=d.pages[page-1].get('words') or []
    if not words:return {'masks':[],'ocr':False}
    joined='';positions=[];previous=None
    for w in words:
        # Nowa linia OCR = znak nowej linii; reguły nie łączą danych z sąsiednich wierszy.
        if previous and w['box'][1]>=previous[3]-0.002:joined=joined.rstrip(' ')+'\n'
        start=len(joined);joined+=w['text']+' ';positions.append((start,len(joined)-1,w['box']));previous=w['box']
    masks=[]
    for r in detect_pii(joined):
        boxes=[box for start,end,box in positions if start<r['end'] and end>r['start']]
        # Wyrazy w jednym wierszu łączymy w jeden prostokąt.
        lines=[]
        for box in boxes:
            line=next((l for l in lines if abs(l[1]-box[1])<0.01 and abs(l[3]-box[3])<0.01),None)
            if line:line[0]=min(line[0],box[0]);line[2]=max(line[2],box[2])
            else:lines.append(list(box))
        fragment=joined[r['start']:r['end']].replace('\n',' ')
        masks+=[{'page':page,'box':[max(0,b[0]-0.003),max(0,b[1]-0.003),min(1,b[2]+0.003),min(1,b[3]+0.003)],'state':'proposed','category':f"OCR: {r['category']} · {fragment[:60]}"} for b in lines]
    return {'masks':masks,'ocr':True}
@app.patch('/api/documents/{ident}/redactions')
def masks(ident:str,body:Review,user=Depends(current_user),db:DBSession=Depends(get_db)):
    d=obj(db,Document,ident,True)
    if d.state!='ready' or not d.pdf_path:raise HTTPException(422,'Dokument nie jest gotowy do przeglądu')
    r=db.get(AttachmentReview,ident)
    if r:revision(r,body.version)
    elif body.version!=0:raise HTTPException(409,'Odśwież przegląd')
    for m in body.masks:
        a,b,c,e=m.box
        if m.page>len(d.pages) or not 0<=a<c<=1 or not 0<=b<e<=1:raise HTTPException(422,'Niepoprawny obszar strony')
    if not set(body.reviewed_pages)<=set(range(1,len(d.pages)+1)):raise HTTPException(422,'Niepoprawny numer strony')
    if not r:r=AttachmentReview(document_id=ident,document_version=d.version);db.add(r);r.version=0
    r.version+=1;r.document_version=d.version;r.masks=[m.model_dump() for m in body.masks];r.reviewed_pages=sorted(set(body.reviewed_pages));log(db,user,d.case_id,'attachment_reviewed',{'id':ident,'version':r.version});db.commit();return {'version':r.version,'masks':r.masks,'reviewed_pages':r.reviewed_pages}
@app.post('/api/documents/{ident}/redacted-exports')
def attachment_export(ident:str,user=Depends(current_user),db:DBSession=Depends(get_db)):
    d=obj(db,Document,ident,True);r=db.get(AttachmentReview,ident)
    if not r or r.document_version!=d.version or set(r.reviewed_pages)!=set(range(1,len(d.pages)+1)):raise HTTPException(422,'Sprawdź wszystkie strony aktualnej wersji dokumentu')
    if any(m['state']=='proposed' for m in r.masks):raise HTTPException(422,'Rozpatrz propozycje obszarów')
    eid=uid();path=settings.data_dir/'exports'/(eid+'.pdf')
    try:raster_redact(d.pdf_path,r.masks,path)
    except ValueError as exc:raise HTTPException(422,str(exc))
    e=Export(id=eid,case_id=d.case_id,document_id=ident,version=r.version,path=str(path),sha256=digest(path),format='pdf');db.add(e);log(db,user,d.case_id,'attachment_exported',{'export_id':eid});db.commit();return {'id':eid,'url':'/api/exports/'+eid,'version':r.version}
@app.post('/api/document-exports/{ident}/approve')
def approve_attachment(ident:str,body:Approve,user=Depends(current_user),db:DBSession=Depends(get_db)):
    e=obj(db,Export,ident,True)
    if not e.document_id:raise HTTPException(422,'To nie jest kopia załącznika')
    r=db.get(AttachmentReview,e.document_id);d=obj(db,Document,e.document_id)
    if not body.confirmed or not r or r.version!=e.version or r.version!=body.version or r.document_version!=d.version:raise HTTPException(409,'Ponownie przejrzyj aktualną kopię')
    e.approved=True;log(db,user,e.case_id,'attachment_export_approved',{'id':ident});db.commit();return {'ok':True}

def check_export(db,e,approved=True):
    if approved and not e.approved:raise HTTPException(409,'Kopia wymaga zatwierdzenia po przeglądzie')
    if e.draft_id:
        d=obj(db,Draft,e.draft_id);assert_draft_current(db,d)
        if d.version!=e.version or d.approved_version!=d.version:raise HTTPException(409,'Eksport pisma jest nieaktualny')
    if e.document_id:
        r=db.get(AttachmentReview,e.document_id);d=obj(db,Document,e.document_id)
        if not r or r.version!=e.version or r.document_version!=d.version:raise HTTPException(409,'Eksport załącznika jest nieaktualny')
    path=Path(e.path)
    if not path.is_relative_to(settings.data_dir/'exports') or not path.exists() or digest(path)!=e.sha256:raise HTTPException(409,'Plik eksportu nie przeszedł kontroli integralności')
    return path
@app.get('/api/exports/{ident}')
def download(ident:str,inline:bool=False,user=Depends(current_user),db:DBSession=Depends(get_db)):
    e=obj(db,Export,ident);path=check_export(db,e,False)
    return FileResponse(path,filename=('odpowiedz' if e.draft_id else 'kopia-po-anonimizacji')+'.'+e.format,content_disposition_type='inline' if inline and e.format=='pdf' else 'attachment')
@app.post('/api/cases/{ident}/export-packages')
def package(ident:str,body:Package,user=Depends(current_user),db:DBSession=Depends(get_db)):
    obj(db,Case,ident);letter=obj(db,Export,body.letter_export_id)
    if letter.case_id!=ident or not letter.draft_id:raise HTTPException(422,'Niewłaściwy eksport pisma')
    items=[letter]+[obj(db,Export,i) for i in body.attachment_export_ids]
    if any(e.case_id!=ident for e in items) or any(not e.document_id for e in items[1:]):raise HTTPException(422,'Załącznik należy do innej sprawy')
    paths=[check_export(db,e) for e in items]
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for i,(e,path) in enumerate(zip(items,paths)):z.write(path,('odpowiedz' if i==0 else f'zalacznik-{i:02d}')+'.'+e.format)
    log(db,user,ident,'package_downloaded',{'exports':[e.id for e in items]});db.commit();return Response(out.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="odpowiedz-z-zalacznikami.zip"'})

@app.post('/api/calendar-imports/preview')
async def calendar_preview(file:UploadFile=File(...),user=Depends(require_admin)):
    if not (file.filename or '').lower().endswith('.xlsx'):raise HTTPException(415,'Prześlij XLSX')
    data=await file.read(settings.max_upload_mb*1024*1024+1)
    if len(data)>settings.max_upload_mb*1024*1024:raise HTTPException(413,'Plik za duży')
    try:
        from .services.calendar_import import preview
        return preview(data)
    except ValueError as exc:raise HTTPException(422,str(exc))
    except Exception:raise HTTPException(422,'Nie można odczytać arkusza')
class CalendarRow(CaseInput):
    deadline:date
    answered:date|None=None
    warnings:list[str]=Field(default_factory=list)
class CalendarApply(Strict):rows:list[CalendarRow]=Field(max_length=1000);confirmed:bool
@app.post('/api/calendar-imports/confirm')
def calendar_apply(body:CalendarApply,user=Depends(require_admin),db:DBSession=Depends(get_db)):
    if not body.confirmed:raise HTTPException(422,'Potwierdź weryfikację danych importu')
    for row in body.rows:
        if row.deadline<row.received or row.answered and row.answered<row.received:raise HTTPException(422,'Popraw daty wcześniejsze niż wpływ: '+row.reference)
    if len({r.reference for r in body.rows})!=len(body.rows):raise HTTPException(422,'Sygnatury w arkuszu powtarzają się')
    skipped=[]
    for row in body.rows:
        # Sprawy już zarejestrowane pomijamy zamiast blokować cały import.
        if db.scalar(select(Case).where(Case.reference==row.reference)):skipped.append(row.reference);continue
        c=Case(**row.model_dump(exclude={'questions'}),questions=[q.model_dump() for q in row.questions],original_deadline=deadline_for(row.received),status='zakonczony' if row.answered else 'zarejestrowany')
        db.add(c);db.flush();log(db,user,c.id,'calendar_imported',{'warnings':row.warnings})
    db.commit();return {'count':len(body.rows)-len(skipped),'skipped':skipped}
