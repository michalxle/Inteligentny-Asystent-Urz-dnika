import sys,json
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[1]
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=120,trust_env=False) as c:
 r=c.post('/api/auth/login',json=json.loads((root/'.data/bootstrap-credentials.json').read_text()));r.raise_for_status();c.headers['X-CSRF-Token']=r.json()['csrf']
 print(json.dumps(c.get('/api/diagnostics').json(),ensure_ascii=False))
 case=next(x for x in c.get('/api/cases').json() if x['reference'].startswith('DEMO.') and x['title'].startswith('Liczba uczniów'))
 response=c.get('/api/cases/'+case['id']+'/similar?all_archive=true');print('Search',response.status_code,response.json().get('mode'),len(response.json().get('results',[])))
