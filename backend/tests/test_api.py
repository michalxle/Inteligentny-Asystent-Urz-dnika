from uuid import uuid4
from datetime import timedelta
from sqlalchemy import select
from app.models import Document, Draft, Case
from app.services.domain import today, deadline_for

def create_case(client):
    r=client.post('/api/cases',json={'reference':'TEST.'+str(uuid4()),'title':'Wniosek testowy','received':today().isoformat(),'questions':[{'id':'q1','text':'Ilu uczniów było w szkole w 2026?'}]})
    assert r.status_code==201,r.text
    return r.json()

def test_auth_csrf_and_administrator_permissions(client):
    assert client.get('/api/cases').status_code==200
    token=client.headers.pop('X-CSRF-Token')
    assert client.post('/api/cases',json={}).status_code==403
    client.headers['X-CSRF-Token']=token
    assert client.post('/api/knowledge/documents',files={'file':('x.txt',b'ustawa','text/plain')}).status_code==403

def test_optimistic_concurrency(client):
    c=create_case(client)
    payload={k:c[k] for k in ['reference','title','applicant','received','owner','questions','delivery','units','version']}
    payload['title']='Zmieniono'
    assert client.patch('/api/cases/'+c['id'],json=payload).status_code==200
    assert client.patch('/api/cases/'+c['id'],json=payload).status_code==409

def test_manual_export_requires_completeness_and_current_version(client):
    c=create_case(client);d=client.post('/api/cases/'+c['id']+'/manual-drafts').json()
    assert client.post('/api/drafts/'+d['id']+'/approve',json={'version':1,'confirmed':True}).status_code==422
    d=client.patch('/api/drafts/'+d['id'],json={'version':d['version'],'text':'Dane syntetyczne: 120 uczniów. Kontakt test@example.invalid','coverage':[{'question_id':'q1','reviewed':True,'missing':[]}]}).json()
    d=client.post('/api/drafts/'+d['id']+'/redaction-scan').json()
    assert client.post('/api/drafts/'+d['id']+'/approve',json={'version':d['version'],'confirmed':True}).status_code==422
    for r in d['redactions']:r['state']='accepted'
    d=client.patch('/api/drafts/'+d['id']+'/redactions',json={'version':d['version'],'redactions':d['redactions']}).json()
    assert client.post('/api/drafts/'+d['id']+'/approve',json={'version':d['version'],'confirmed':True}).status_code==200
    e=client.post('/api/drafts/'+d['id']+'/exports?format=txt').json()
    result=client.get(e['url']);assert result.status_code==200
    assert b'test@example.invalid' not in result.content and b'DANE USUNI' in result.content
    client.patch('/api/drafts/'+d['id'],json={'version':d['version'],'text':'Nowa wersja','coverage':d['coverage']})
    assert client.get(e['url']).status_code==409

def test_upload_rejects_disguised_executable(client):
    assert client.post('/api/imports',files={'file':('x.pdf',b'not a PDF','application/pdf')}).status_code==415

def test_deadline_does_not_change_with_query_note(client):
    c=create_case(client)
    client.post('/api/cases/'+c['id']+'/events',json={'type':'query','text':'Trwa kwerenda.'})
    after=client.get('/api/cases/'+c['id']).json()['case']
    assert after['deadline']==c['deadline']

def patch_payload(c):
    return {k:c[k] for k in ['reference','title','applicant','received','owner','questions','delivery','units','version']}

def test_receipt_correction_recalculates_only_automatic_deadline(client):
    c=create_case(client);p=patch_payload(c)
    p['received']=(today()-timedelta(days=1)).isoformat()
    r=client.patch('/api/cases/'+c['id'],json=p);assert r.status_code==200,r.text
    corrected=r.json()
    assert corrected['deadline']==corrected['original_deadline']==deadline_for(today()-timedelta(days=1)).isoformat()
    r=client.post('/api/cases/'+c['id']+'/deadline-events',json={'version':corrected['version'],'deadline':(today()+timedelta(days=25)).isoformat(),'notified_on':today().isoformat(),'reason':'Testowe uzupełnienie materiałów','basis':'Test QA'})
    assert r.status_code==200,r.text
    p=patch_payload(r.json());p['received']=(today()-timedelta(days=2)).isoformat()
    r=client.patch('/api/cases/'+c['id'],json=p);assert r.status_code==200,r.text
    assert r.json()['deadline']==(today()+timedelta(days=25)).isoformat()
    assert r.json()['original_deadline']==deadline_for(today()-timedelta(days=2)).isoformat()

def test_edit_of_closed_case_preserves_status_and_chronology(client):
    c=create_case(client)
    r=client.post('/api/cases/'+c['id']+'/sent',json={'version':c['version'],'answered':today().isoformat(),'delivery':'Test QA'})
    assert r.status_code==200,r.text
    p=patch_payload(r.json());p['owner']='Inny operator'
    r=client.patch('/api/cases/'+c['id'],json=p);assert r.status_code==200,r.text
    assert r.json()['status']=='zakonczony'
    p=patch_payload(r.json());p['received']=(today()+timedelta(days=1)).isoformat()
    assert client.patch('/api/cases/'+c['id'],json=p).status_code==422

def test_rescan_keeps_manual_masks_and_operator_decisions(client,monkeypatch):
    import app.services.ner
    monkeypatch.setattr(app.services.ner,'ner_spans',lambda *_:[])
    c=create_case(client);d=client.post('/api/cases/'+c['id']+'/manual-drafts').json()
    text='POUFNE test@example.invalid pozostaw@example.invalid'
    d=client.patch('/api/drafts/'+d['id'],json={'version':d['version'],'text':text,'coverage':[{'question_id':'q1','reviewed':True,'missing':[]}]}).json()
    d=client.post('/api/drafts/'+d['id']+'/redaction-scan').json()
    d['redactions'][0]['state']='accepted';d['redactions'][1]['state']='rejected'
    d['redactions'].append({'start':0,'end':6,'state':'accepted','category':'ręcznie','reason':'Test operatora'})
    d=client.patch('/api/drafts/'+d['id']+'/redactions',json={'version':d['version'],'redactions':d['redactions']}).json()
    expected=sorted(d['redactions'],key=lambda r:r['start'])
    for _ in range(2):
        d=client.post('/api/drafts/'+d['id']+'/redaction-scan').json()
        assert d['redactions']==expected
    assert client.post('/api/drafts/'+d['id']+'/approve',json={'version':d['version'],'confirmed':True}).status_code==200
    e=client.post('/api/drafts/'+d['id']+'/exports?format=txt').json()
    result=client.get(e['url']).text
    assert 'POUFNE' not in result and ' test@example.invalid' not in result
    assert 'pozostaw@example.invalid' in result

def test_attachment_export_requires_review_and_invalidates_previous_copy(client,db,tmp_path):
    from app.services.documents import export_letter,digest
    p=tmp_path/'files'/'source.pdf';export_letter('Kontakt SECRET@example.invalid','pdf',p)
    c=create_case(client)
    doc=Document(case_id=c['id'],name='source.pdf',kind='attachment',path=str(p),pdf_path=str(p),sha256=digest(p),state='ready',pages=[{'page':1,'text':'secret','words':[],'ocr':False}]);db.add(doc);db.commit()
    assert client.post('/api/documents/'+doc.id+'/redacted-exports').status_code==422
    r=client.patch('/api/documents/'+doc.id+'/redactions',json={'version':0,'masks':[{'page':1,'box':[0,0,1,1],'state':'accepted'}],'reviewed_pages':[1]}).json()
    response=client.post('/api/documents/'+doc.id+'/redacted-exports');assert response.status_code==200,response.text
    e=response.json()
    assert client.post('/api/document-exports/'+e['id']+'/approve',json={'version':r['version'],'confirmed':True}).status_code==200
    assert client.get(e['url']).status_code==200
    restored=client.get('/api/documents/'+doc.id+'/review').json()['exports'][0]
    assert restored['id']==e['id'] and restored['current'] and restored['approved']
    client.patch('/api/documents/'+doc.id+'/redactions',json={'version':r['version'],'masks':[],'reviewed_pages':[1]})
    assert client.get(e['url']).status_code==409
    assert not client.get('/api/documents/'+doc.id+'/review').json()['exports'][0]['current']

def test_duplicate_request_returns_registered_case_and_cannot_reregister(client,db):
    original=client.post('/api/imports',files={'file':('qa.txt',b'DANE SYNTETYCZNE QA','text/plain')}).json()['document']
    doc=db.get(Document,original['id']);doc.state='ready';db.commit()
    body={'reference':'TEST.'+str(uuid4()),'title':'Import testowy','received':today().isoformat()}
    r=client.post('/api/imports/'+doc.id+'/confirm',json={'version':doc.version,'text':'DANE SYNTETYCZNE QA','case':body})
    assert r.status_code==200,r.text
    saved=r.json()
    duplicate=client.post('/api/imports',files={'file':('qa-kopia.txt',b'DANE SYNTETYCZNE QA','text/plain')}).json()
    assert duplicate['duplicate'] and duplicate['document']['case_id']==saved['case_id']
    assert duplicate['document']['id']==saved['id']
    body['reference']='TEST.'+str(uuid4())
    r=client.post('/api/imports/'+doc.id+'/confirm',json={'version':saved['version'],'text':'Inny tekst','case':body})
    assert r.status_code==409
    assert client.get('/api/imports/'+doc.id).json()['document']['text']=='DANE SYNTETYCZNE QA'

def test_failed_document_job_has_terminal_document_state(client,db,monkeypatch):
    from contextlib import contextmanager
    import app.worker as worker
    from app.models import Job
    r=client.post('/api/imports',files={'file':('bad.pdf',b'%PDF-1.7\nINVALID','application/pdf')}).json()
    @contextmanager
    def session():yield db
    def failed_extract(_):raise ValueError('Niepoprawny dokument testowy')
    monkeypatch.setattr(worker,'SessionLocal',session)
    monkeypatch.setattr(worker,'extract',failed_extract)
    worker.execute(r['job']['id'])
    assert db.get(Job,r['job']['id']).status=='failed'
    assert client.get('/api/imports/'+r['document']['id']).json()['document']['state']=='failed'

def test_recording_delivery_preserves_verified_exports_and_closed_status(client):
    c=create_case(client);d=client.post('/api/cases/'+c['id']+'/manual-drafts').json()
    d=client.patch('/api/drafts/'+d['id'],json={'version':d['version'],'text':'Dane syntetyczne: 120 uczniów.','coverage':[{'question_id':'q1','reviewed':True,'missing':[]}]}).json()
    assert client.post('/api/drafts/'+d['id']+'/approve',json={'version':d['version'],'confirmed':True}).status_code==200
    e=client.post('/api/drafts/'+d['id']+'/exports?format=txt').json()
    assert client.post('/api/cases/'+c['id']+'/sent',json={'version':c['version'],'answered':today().isoformat(),'delivery':'Test QA'}).status_code==200
    assert client.get(e['url']).status_code==200
    assert client.post('/api/drafts/'+d['id']+'/exports?format=txt').status_code==200
    d=client.patch('/api/drafts/'+d['id'],json={'version':d['version'],'text':'Korekta testowa: 120 uczniów.','coverage':d['coverage']}).json()
    assert client.get('/api/cases/'+c['id']).json()['case']['status']=='zakonczony'
    assert client.post('/api/drafts/'+d['id']+'/approve',json={'version':d['version'],'confirmed':True}).status_code==200
    assert client.get('/api/cases/'+c['id']).json()['case']['status']=='zakonczony'
