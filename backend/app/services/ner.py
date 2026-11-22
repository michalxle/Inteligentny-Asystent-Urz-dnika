from functools import lru_cache
from ..config import settings

@lru_cache(maxsize=1)
def nlp():
    import spacy
    path=settings.data_dir/'models/pl_core_news_lg'
    if not path.exists():raise OSError('Brak modelu NER')
    return spacy.load(path)

def ner_spans(text,existing):
    result=[]
    for e in nlp()(text).ents:
        if e.label_ not in ['persName','geogName','placeName','PERSON','PER']:continue
        if any(e.start_char<r['end'] and e.end_char>r['start'] for r in existing):continue
        result.append({'start':e.start_char,'end':e.end_char,'state':'proposed','category':e.label_,'reason':'Model NER; sprawdź kontekst funkcji publicznej'})
    return result
