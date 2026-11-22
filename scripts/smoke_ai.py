import json,time,sys
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[1]
credentials=json.loads((root/'.data/bootstrap-credentials.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=300,trust_env=False) as client:
    response=client.post('/api/auth/login',json=credentials);response.raise_for_status();client.headers['X-CSRF-Token']=response.json()['csrf']
    cases=client.get('/api/cases').json();case=next(c for c in cases if c['reference'].startswith('DEMO.') and c['title'].startswith('Liczba uczniów'))
    response=client.post('/api/cases/'+case['id']+'/drafts');response.raise_for_status();job=response.json();start=time.monotonic()
    for _ in range(150):
        status=client.get('/api/jobs/'+job['id']).json()
        if status['status'] in ['done','failed']:break
        time.sleep(2)
    elapsed=round(time.monotonic()-start,1)
    result={'job_status':status['status'],'elapsed_seconds':elapsed,'result':status['result']}
    if status['status']=='done':
        detail=client.get('/api/cases/'+case['id']).json();draft=next(d for d in detail['drafts'] if d['id']==status['result']['draft_id'])
        result['draft_preview']=draft['text'];result['coverage']=draft['coverage'];result['source_count']=len(draft['evidence'])
    (root/'.data/ai-smoke-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ['draft_preview','coverage']},ensure_ascii=False))
    if status['status']!='done':sys.exit(1)
