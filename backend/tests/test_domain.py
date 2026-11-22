from datetime import date
from app.services.domain import add_months, clean_text, extract_questions, find_pii
import pytest

def test_months_are_not_sixty_days():
    assert add_months(date(2026,1,31),2)==date(2026,3,31)
    assert add_months(date(2026,12,31),2)==date(2027,2,28)

def test_redaction_merges_overlaps_without_leaking():
    source='ABC prywatny tekst XYZ'
    result=clean_text(source,[{'start':4,'end':12,'state':'accepted'},{'start':9,'end':18,'state':'accepted'}])
    assert result=='ABC [DANE USUNIĘTE] XYZ'
    with pytest.raises(ValueError):clean_text(source,[{'start':-1,'end':5,'state':'accepted'}])

def test_pii_suggestions_do_not_automatically_remove_data():
    text='Kontakt: test@example.invalid i PESEL 90010112345'
    spans=find_pii(text)
    assert {r['category'] for r in spans}=={'email','PESEL'}
    assert all(r['state']=='proposed' for r in spans)
    assert clean_text(text,spans)==text

def test_numbered_questions_remain_distinct():
    result=extract_questions('Wniosek\n1. Liczba uczniów w czerwcu?\n2. Liczba uczniów we wrześniu?')
    assert len(result)==2 and result[1]['id']=='q2'
