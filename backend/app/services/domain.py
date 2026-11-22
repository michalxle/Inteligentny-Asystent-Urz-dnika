import re
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from calendar import monthrange

STATUSES = ['do_weryfikacji','zarejestrowany','oczekuje_na_materialy','projekt_odpowiedzi','do_akceptacji','gotowy_do_eksportu','zakonczony']

def today(): return datetime.now(ZoneInfo('Europe/Warsaw')).date()
def deadline_for(received): return received + timedelta(days=14)
def add_months(value, count):
    month = value.month - 1 + count
    year = value.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))

def deadline_state(c):
    days = (c.deadline - today()).days
    if c.answered: return {'days':None,'state':'zakonczona','on_time':c.answered <= c.deadline}
    return {'days':days,'state':'overdue' if days<0 else 'today' if days==0 else 'tomorrow' if days==1 else 'later','on_time':None}

def extract_questions(text):
    lines = re.split(r'\n(?=\s*\d+[.)]\s)', text.strip())
    items = [re.sub(r'^\s*\d+[.)]\s*','',s).strip() for s in lines if re.match(r'^\s*\d+[.)]\s',s)]
    if not items:
        items = [s.strip() for s in text.split('\n') if len(s.strip())>30 and not s.startswith(('URZĄD','tel.','email:'))][:8]
    return [{'id':f'q{i+1}','text':s[:4000],'status':'brak_materialu'} for i,s in enumerate(items[:30])]

def find_pii(text):
    patterns = [('email',r'\b[\w.+-]+@[\w.-]+\.[\w-]{2,}\b'),('PESEL',r'(?<!\d)\d{11}(?!\d)'),('rachunek',r'(?<!\d)(?:PL\s*)?\d{2}(?:[ \u00a0]?\d{4}){6}(?!\d)'),('telefon',r'(?<!\d)(?:\+48[ -]?)?\d{3}[ -]\d{3}[ -]\d{3}(?!\d)'),('adres',r'\bul\.?\s+[A-ZŁŚŻŹĆŃÓĄĘ][\wąęółśżźćńĄĘÓŁŚŻŹĆŃ .-]+\s+\d+[\w/-]*')]
    found=[]
    for category, pattern in patterns:
        for m in re.finditer(pattern,text):
            if not any(m.start()<r['end'] and m.end()>r['start'] for r in found):
                found.append({'start':m.start(),'end':m.end(),'category':category,'state':'proposed','reason':'Reguła wykrycia; wymaga oceny kontekstu'})
    return sorted(found,key=lambda r:r['start'])

def clean_text(text, redactions):
    spans=sorted([(r['start'],r['end']) for r in redactions if r['state']=='accepted'])
    merged=[]
    for start,end in spans:
        if start<0 or end>len(text) or end<=start: raise ValueError('Niepoprawny zakres anonimizacji')
        if merged and start<=merged[-1][1]: merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else: merged.append((start,end))
    for start,end in reversed(merged): text=text[:start]+'[DANE USUNIĘTE]'+text[end:]
    return text
