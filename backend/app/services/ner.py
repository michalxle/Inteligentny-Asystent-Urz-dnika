import re
from functools import lru_cache
from ..config import settings

@lru_cache(maxsize=1)
def nlp():
    import spacy
    path=settings.data_dir/'models/pl_core_news_lg'
    if not path.exists():raise OSError('Brak modelu NER')
    return spacy.load(path)

PERSON_LABELS={'persName','PERSON','PER'}

def ner_spans(text,existing):
    # Tylko osoby fizyczne: nazwy miejscowości i instytucji nie są danymi osobowymi.
    result=[]
    for e in nlp()(text).ents:
        if e.label_ not in PERSON_LABELS:continue
        if re.search(r'\d',e.text) or len(e.text.strip())<3 or not re.search(r'[A-ZŁŚŻŹĆŃÓ]',e.text):continue
        if any(e.start_char<r['end'] and e.end_char>r['start'] for r in existing+result):continue
        result.append({'start':e.start_char,'end':e.end_char,'state':'proposed','category':'imię i nazwisko','reason':'Model NER; sprawdź, czy osoba nie pełni funkcji publicznej'})
    return result
