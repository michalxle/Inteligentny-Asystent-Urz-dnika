import re
from datetime import date, timedelta, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo
from calendar import monthrange

# Etapy zgodne z opisem wyzwania: brak działań, zapytania do wydziałów, kwerenda, przygotowana odpowiedź, odpowiedź wysłana.
STATUSES = ['do_weryfikacji','zarejestrowany','oczekuje_na_materialy','kwerenda','projekt_odpowiedzi','do_akceptacji','gotowy_do_eksportu','zakonczony']

def today(): return datetime.now(ZoneInfo('Europe/Warsaw')).date()

def _easter(year):
    a=year%19;b=year//100;c=year%100;d=b//4;e=b%4;f=(b+8)//25;g=(b-f+1)//3;h=(19*a+b-d-g+15)%30
    i=c//4;k=c%4;l=(32+2*e+2*i-h-k)%7;m=(a+11*h+22*l)//451;month=(h+l-7*m+114)//31;day=(h+l-7*m+114)%31+1
    return date(year,month,day)

@lru_cache(maxsize=64)
def holidays(year):
    """Dni ustawowo wolne od pracy w Polsce (ustawa z 18 stycznia 1951 r.)."""
    e=_easter(year)
    days={date(year,1,1),date(year,1,6),e,e+timedelta(days=1),date(year,5,1),date(year,5,3),e+timedelta(days=49),e+timedelta(days=60),date(year,8,15),date(year,11,1),date(year,11,11),date(year,12,25),date(year,12,26)}
    if year>=2025:days.add(date(year,12,24))
    return frozenset(days)

def is_working_day(value): return value.weekday()<5 and value not in holidays(value.year)

def next_working_day(value):
    while not is_working_day(value):value+=timedelta(days=1)
    return value

def deadline_for(received):
    # Art. 13 ust. 1 UDIP: 14 dni; koniec terminu w sobotę lub dzień wolny przesuwa się na najbliższy dzień roboczy (art. 57 § 4 KPA).
    return next_working_day(received + timedelta(days=14))

def add_months(value, count):
    month = value.month - 1 + count
    year = value.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))

def deadline_state(c):
    days = (c.deadline - today()).days
    if c.answered: return {'days':None,'state':'zakonczona','on_time':c.answered <= c.deadline,'extension_days':(c.deadline-c.original_deadline).days}
    return {'days':days,'state':'overdue' if days<0 else 'today' if days==0 else 'tomorrow' if days==1 else 'later','on_time':None,'extension_days':(c.deadline-c.original_deadline).days}

def format_date(value):
    return value.strftime('%d.%m.%Y') + ' r.'

STOPWORDS={'informacji','informacja','informację','publicznej','publiczna','publicznych','udostępnienie','udostępnienia','udostępnić','wniosek','wniosku','proszę','prosimy','trybie','dostępu','państwa','również','dotyczy','dotyczące','dotyczącej','który','która','które','których','zakresie','podstawie','ustawy','jakim','jakie','jaki','jaka','oraz','także','takie','został','została','zostały','będzie','mają','miała','miał','tych','tego','temat','także','ponadto','bydgoszcz','bydgoszczy','miasta','miasto','urząd','urzędu','gmina','gminy','aktualne','aktualnie','pragnę','zapytać','zwracam','uprzejmą','prośbą','dzień','dobry','witam','pozdrawiam','szanowni','wnioskuję','przesłanie','podanie','dane','danych','liczba','liczby','ilość','ilości','roku','lata','stan','stanie','pozwolą','pozwoli','określenie','właściwej','naszej','następujących','przynależą','uzyskane','dokumentacji','dokumentów','zestawienie','zestawienia','poszczególnych','edytowalne','jeżeli','dostępne'}

def stems(text):
    """Przybliżone rdzenie polskich wyrazów (bez słów ogólnych), odporne na odmianę."""
    return {w[:max(5,len(w)-3)] for w in (x.lower() for x in re.findall(r'[^\W\d_]{4,}',text)) if w not in STOPWORDS}

# ---------------------------------------------------------------- pytania z wniosku

_BULLET=r'(?:[•●▪◦‣\-–*]|\d{1,2}[.)]|[a-z][.)])\s'
_SKIP=re.compile(r'^(dzień dobry|witam|szanown|pozdrawiam|z (wyrazami|poważaniem)|z poważaniem|dziękuję|--|biuro komunikacji|urząd miasta|tel\.|e-?mail:|wniosek o udostępnienie informacji publicznej\W*$)',re.I)
_REQUEST=re.compile(r'\?|prosz|prosimy|wnosz|wnioskuj|zapyta|pytam|pragn[eę]|zwracam|zwracamy|udost[eę]pn|przes[łl]a|poda(nie|ć)|informacj|zestawien',re.I)

def _reflow(text):
    """Scala wiersze zawinięte przez układ strony (PDF, DOCX→PDF, OCR) w akapity."""
    lines=[l.rstrip() for l in text.replace('\r','').split('\n')]
    lengths=sorted(len(l.strip()) for l in lines if l.strip())
    wide=lengths[int(len(lengths)*0.8)] if lengths else 0
    paragraphs=[];current=''
    for i,raw in enumerate(lines):
        line=raw.strip()
        if not line:
            if current:paragraphs.append(current);current=''
            continue
        if re.match(_BULLET,line) and current:paragraphs.append(current);current=''
        current=(current+' '+line).strip() if current else line
        nxt=next((l.strip() for l in lines[i+1:i+2]),'')
        # Zawinięty wiersz: następny zaczyna się małą literą albo bieżący sięga prawie pełnej szerokości strony.
        wrapped=not line.endswith((':',';')) and (bool(re.match(r'[a-ząęółśżźćń(„"]',nxt)) or (wide>=40 and len(line)>=0.85*wide and not line.endswith(('.','?','!'))))
        if not wrapped or (nxt and re.match(_BULLET,nxt)):
            paragraphs.append(current);current=''
    if current:paragraphs.append(current)
    return [re.sub(r'\s+',' ',p).strip() for p in paragraphs if p.strip()]

def _numbered(text):
    markers=[(m.start(),int(m.group(1)),m.end()) for m in re.finditer(r'(?:(?<=^)|(?<=\s))(\d{1,2})[.)](?=\s)',text)]
    best=[]
    for i,(_,n,_e) in enumerate(markers):
        if n!=1:continue
        seq=[markers[i]];expected=2
        for m in markers[i+1:]:
            if m[1]==expected:seq.append(m);expected+=1
        if len(seq)>len(best):best=seq
    if not best or (len(best)<2 and not re.search(r'(^|\n)\s*1[.)]\s',text)):return []
    items=[]
    for j,(start,_,body) in enumerate(best):
        end=best[j+1][0] if j+1<len(best) else len(text)
        item=text[body:end]
        if j+1==len(best):
            item=item.split("\n")[0].strip()   # akapit po ostatnim punkcie nie jest częścią pytania
            tail=re.search(r'(?<=[,.;])\s+(?=[A-ZŁŚŻŹĆ][a-ząęółśżźćń]+\s)',item)
            if tail and item[:1].islower():item=item[:tail.start()]
        items.append(re.sub(r'\s+',' ',item).strip(' ,;'))
    return [i for i in items if i]

_ABBR={'art','ust','pkt','poz','nr','ul','al','pl','os','dz','u','r','zm','tj','ww','np','pn','im','św','tel','sp','o.o','tzw','dot','jw','ok'}
def _sentences(paragraph):
    parts=[];start=0
    for m in re.finditer(r'(?<=[.?!])\s+(?=[A-ZŁŚŻŹĆŃÓĄĘ])',paragraph):
        word=re.findall(r'([\wąęółśżźćń.]+)[.?!]$',paragraph[start:m.start()])
        if word and word[-1].lower().strip('.') in _ABBR:continue
        parts.append(paragraph[start:m.start()]);start=m.end()
    parts.append(paragraph[start:])
    return [s.strip() for s in parts if s.strip()]

def extract_questions(text):
    paragraphs=_reflow(text or '')
    items=_numbered('\n'.join(paragraphs))
    if not items:
        i=0
        while i<len(paragraphs):
            p=paragraphs[i]
            if p.endswith(':'):
                listed=[];j=i+1
                while j<len(paragraphs) and len(paragraphs[j])<=90 and not paragraphs[j].endswith(':') and not re.search(r'\?|^(prosz|prosimy|wnosz|wnioskuj|pragn|zwracam|jednocze|ponadto|również)',paragraphs[j],re.I):
                    listed.append(re.sub('^'+_BULLET,'',paragraphs[j]+' ').strip(' ,;'));j+=1
                intro=[s for s in _sentences(p) if not _SKIP.match(s)]
                if 2<=len(listed)<=8:
                    items+=[s for s in intro[:-1] if _REQUEST.search(s)]+listed
                elif listed:
                    items+=[s for s in intro[:-1] if _REQUEST.search(s)]+[(intro[-1] if intro else p)+' '+', '.join(listed)]
                else:
                    items+=[s for s in intro if _REQUEST.search(s)]
                i=j;continue
            items+=[s for s in _sentences(p) if not _SKIP.match(s) and _REQUEST.search(s) and len(s)>15]
            i+=1
        if not items:items=[p for p in paragraphs if len(p)>30 and not _SKIP.match(p)][:8]
    return [{'id':f'q{i+1}','text':s[:4000],'status':'brak_materialu'} for i,s in enumerate(items[:30])]

# ---------------------------------------------------------------- dane osobowe

_UP='A-ZŁŚŻŹĆŃÓĄĘ';_LOW='a-ząęółśżźćń'
PII_PATTERNS=[
    ('email',r'\b[\w.+-]+@[\w.-]+\.[\w-]{2,}\b'),
    ('rachunek',r'(?<!\d)(?:PL\s?)?\d{2}(?:[  ]?\d{4}){6}(?!\d)'),
    ('PESEL',r'(?<!\d)\d{11}(?!\d)'),
    ('księga wieczysta',r'\b[A-Z]{2}\d[A-Z]/\d{8}/\d\b'),
    ('dokument tożsamości',r'\b[A-Z]{3}\s?\d{6}\b|\b[A-Z]{2}\s?\d{7}\b'),
    ('NIP',r'(?<!\d)\d{3}-\d{3}-\d{2}-\d{2}(?!\d)|(?<!\d)\d{3}-\d{2}-\d{2}-\d{3}(?!\d)|(?i:NIP)[:\s]*(\d{10})(?!\d)'),
    ('telefon',r'(?<![\d/.])(?:\+48[ -]?|0048[ -]?)?(?:\d{3}[ -]?\d{3}[ -]?\d{3}|\(?\d{2}\)?[ -]\d{3}[ -]\d{2}[ -]\d{2})(?![\d/]|\.\d)(?!\s*(?:zł|PLN|tys|mln|mld|%|osób|uczni|m2|m²|km))'),
    ('data urodzenia',r'(?i:ur\.|urodzon\w*)\s*(?:dnia\s*)?(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}(?:\s*r\.)?)'),
    ('nr rejestracyjny',r'(?i:nr\.?\s*rej\w*\.?|rejestracyjn\w*|pojazd\w*|samoch\w*)[^\n]{0,25}?\b([A-Z]{1,3}\s?[0-9][0-9A-Z]{3,4})\b'),
    ('adres',rf'\b(?:[Uu]l\.?|[Aa]l\.|[Oo]s\.|[Pp]l\.|[Uu]lica|[Aa]leja|[Oo]siedle|[Pp]lac)\s+[{_UP}][\w{_LOW} .-]*?\s+\d+[\w]*(?:\s?/\s?\d+\w*)?(?:\s*(?:m\.|lok\.)\s*\d+)?'),
    ('kod pocztowy',rf'(?<![\d-])\d{{2}}-\d{{3}}(?![\d-])(?:\s+[{_UP}][{_LOW}]+(?:[ -][{_UP}][{_LOW}]+)?)?'),
]

def find_pii(text):
    found=[]
    for category, pattern in PII_PATTERNS:
        for m in re.finditer(pattern,text):
            start,end=(m.span(1) if m.lastindex and m.group(1) else m.span())
            if not any(start<r['end'] and end>r['start'] for r in found):
                found.append({'start':start,'end':end,'category':category,'state':'proposed','reason':'Reguła wykrycia; wymaga oceny kontekstu'})
    return sorted(found,key=lambda r:r['start'])

def detect_pii(text,existing=None):
    """Reguły + polski NER (jeśli model jest dostępny)."""
    detected=find_pii(text)
    try:
        from . import ner
        detected+=ner.ner_spans(text,(existing or [])+detected)
    except (ImportError,OSError):pass
    return sorted(detected,key=lambda r:r['start'])

def merge_redactions(text,current,detected):
    """Dokłada nowe propozycje, nie zmieniając decyzji operatora ani zakresów ręcznych."""
    kept=[r for r in current if 0<=r['start']<r['end']<=len(text)]
    new=[r for r in detected if not any(r['start']<k['end'] and r['end']>k['start'] for k in kept)]
    return sorted(kept+new,key=lambda r:r['start'])

def remap_redactions(old_text,new_text,redactions):
    """Przenosi decyzje anonimizacji na poprawioną treść pisma (fragment szukany najbliżej poprzedniego położenia)."""
    result=[]
    for r in redactions:
        phrase=old_text[r['start']:r['end']]
        if not phrase.strip():continue
        hits=[m.start() for m in re.finditer(re.escape(phrase),new_text)]
        if not hits:continue
        start=min(hits,key=lambda h:abs(h-r['start']))
        if any(start<x['end'] and start+len(phrase)>x['start'] for x in result):continue
        result.append({**r,'start':start,'end':start+len(phrase)})
    return sorted(result,key=lambda r:r['start'])

def clean_text(text, redactions):
    spans=sorted([(r['start'],r['end']) for r in redactions if r['state']=='accepted'])
    merged=[]
    for start,end in spans:
        if start<0 or end>len(text) or end<=start: raise ValueError('Niepoprawny zakres anonimizacji')
        if merged and start<=merged[-1][1]: merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else: merged.append((start,end))
    for start,end in reversed(merged): text=text[:start]+'[DANE USUNIĘTE]'+text[end:]
    return text

# ---------------------------------------------------------------- propozycja danych rejestracyjnych

_MONTHS={'stycznia':1,'lutego':2,'marca':3,'kwietnia':4,'maja':5,'czerwca':6,'lipca':7,'sierpnia':8,'września':9,'października':10,'listopada':11,'grudnia':12}
REFERENCE_PREFIX='BKS.IV.1431'

def _parse_date(text):
    m=re.search(r'(\d{1,2})[.\-/ ](\d{1,2})[.\-/ ](\d{4})',text) or None
    if m:
        try:return date(int(m.group(3)),int(m.group(2)),int(m.group(1)))
        except ValueError:pass
    m=re.search(r'(\d{4})-(\d{2})-(\d{2})',text)
    if m:
        try:return date(int(m.group(1)),int(m.group(2)),int(m.group(3)))
        except ValueError:pass
    m=re.search(r'(\d{1,2})\s+('+'|'.join(_MONTHS)+r')\s+(\d{4})',text,re.I)
    if m:return date(int(m.group(3)),_MONTHS[m.group(2).lower()],int(m.group(1)))
    return None

def suggest_received(text,fallback):
    """Data wpływu z pieczęci kancelarii, nagłówka e-maila lub daty pisma; w razie braku — dzisiaj."""
    for pattern in [r'(?i)data\s*wp[łl]ywu[^\n]{0,40}',r'(?i)wp[łl]yn[ęe][łl]o[^\n]{0,40}',r'(?i)(?:wys[łl]ano|sent|date)\s*:[^\n]{0,60}',r'(?i)referat obs[łl]ugi[^\n]*\n[^\n]{0,20}',r'(?i)bydgoszcz,?\s*(?:dnia\s*)?[^\n]{0,25}']:
        for m in re.finditer(pattern,text):
            value=_parse_date(m.group(0))
            if value and date(2000,1,1)<=value<=fallback:return value
    return fallback

def next_reference(existing,year):
    numbers=[int(m.group(1)) for r in existing for m in [re.fullmatch(re.escape(REFERENCE_PREFIX)+r'\.(\d+)\.'+str(year),r)] if m]
    return f'{REFERENCE_PREFIX}.{max(numbers,default=0)+1}.{year}'

def suggest_applicant(text):
    lines=[l.strip(' |-–') for l in text.replace('\r','').split('\n')]
    for i,l in enumerate(lines):
        m=re.match(r'(?i)(pozdrawiam|z wyrazami szacunku|z poważaniem|z powa[żz]aniem|łączę pozdrowienia)\W*(.*)$',l)
        if m:
            rest=m.group(2).strip(' |,-')
            if rest and len(rest)<=60:return rest
            for nxt in lines[i+1:i+4]:
                if nxt and len(nxt)<=60 and not re.search(r'@|\d{3}',nxt):return nxt
    m=re.search(r'\b((?:Stowarzyszenie|Fundacja|Spółka|Kancelaria|Fundacji|Związek|Towarzystwo|Parafia)[^,.\n]{3,80})',text)
    if m:return m.group(1).strip()
    return ''

def suggest_title(questions,text):
    source=questions[0]['text'] if questions else next((p for p in _reflow(text) if len(p)>30),'')
    source=re.sub(r'(?i)^(w trybie (?:dostępu do )?informacji publicznej|w trybie ustawy o dostępie do informacji publicznej|działając na podstawie[^,]*,)\s*','',source)
    source=re.sub(r'(?i)^(chcę|chciał(?:a|bym)|pragnę)\s+(państwa\s+)?zapytać\s+(o\s+to,?\s*)?|^(proszę|prosimy|wnoszę|wnioskuję)\s+(o\s+)?(udostępnienie|przesłanie|podanie)?\s*(informacji\s+)?(o|dot\.?|dotyczącej|w zakresie)?\s*','',source).strip(' ,.:')
    if len(source)>140:source=source[:140].rsplit(' ',1)[0]+'…'
    return source[:1].upper()+source[1:]

def suggest_case(text,questions,existing_refs,day):
    found=re.search(re.escape(REFERENCE_PREFIX)+r'\.\d+\.\d{4}',text)
    received=suggest_received(text,day)
    reference=found.group(0) if found and found.group(0) not in existing_refs else next_reference(existing_refs,received.year)
    return {'reference':reference,'received':received.isoformat(),'deadline':deadline_for(received).isoformat(),'applicant':suggest_applicant(text),'title':suggest_title(questions,text)}
