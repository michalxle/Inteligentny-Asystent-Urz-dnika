"""Regresje dla błędów znalezionych w przeglądzie zgodności z wyzwaniem UMB."""
from datetime import date, timedelta
from uuid import uuid4
from app.services.domain import today, extract_questions, find_pii, deadline_for, remap_redactions, holidays


def mk_case(client, **kw):
    body = {'reference': 'TEST.' + str(uuid4()), 'title': 'Wniosek testowy', 'received': today().isoformat(),
            'questions': [{'id': 'q1', 'text': 'Ile?'}]} | kw
    r = client.post('/api/cases', json=body); assert r.status_code == 201, r.text
    return r.json()


def reviewed(d): return [{'question_id': 'q1', 'reviewed': True, 'missing': []}]


# --- pytania z wniosku ---------------------------------------------------------

WRAPPED = ('W trybie dostępu do informacji publicznej chcę Państwa zapytać o to w\n'
           'jakim aktualnie stanie znajduje się i w jakiej lokalizacji jest\n'
           'przechowywana rzeźba która w ubiegłym roku została usunięta z ronda.\n'
           'Również w trybie dostępu do informacji publicznej pragnę zapytać jaki\n'
           'plan mają Państwo odnośnie jej przyszłości.\n')

def test_wrapped_lines_are_joined_into_two_questions():
    qs = extract_questions(WRAPPED)
    assert len(qs) == 2, qs
    assert qs[0]['text'].startswith('W trybie') and 'rzeźba' in qs[0]['text']


def test_inline_numbering_is_split():
    text = ('Wniosek o udostępnienie informacji publicznej\nStowarzyszenie zwraca się z prośbą. '
            '1. z kim gmina miała umowy w 2024 r.? 2. komu udzielała zleceń? 3. jaki był koszt w 2024 r.?')
    assert [q['text'] for q in extract_questions(text)] == ['z kim gmina miała umowy w 2024 r.?', 'komu udzielała zleceń?', 'jaki był koszt w 2024 r.?']


def test_paragraph_after_last_item_is_not_part_of_question():
    text = '1. umowę podstawową,\n2. aneksy do umowy,\n\nJednocześnie proszę o skany na adres abc@example.invalid'
    qs = extract_questions(text)
    assert len(qs) == 2 and 'abc@' not in qs[-1]['text']


def test_short_list_after_colon_becomes_items_and_long_list_is_merged():
    text = 'Proszę o przesłanie dokumentacji budynku:\nProjekt zagospodarowania terenu\nWizualizacje\nZestawienie parametrów\n'
    assert [q['text'] for q in extract_questions(text)] == ['Projekt zagospodarowania terenu', 'Wizualizacje', 'Zestawienie parametrów']
    streets = 'Proszę o liczbę mieszkańców ulic:\n' + '\n'.join(f'• Ulica{i}' for i in range(12))
    qs = extract_questions(streets)
    assert len(qs) == 1 and 'Ulica11' in qs[0]['text']


# --- terminy --------------------------------------------------------------------

def test_deadline_moves_past_weekend_and_holidays():
    assert deadline_for(date(2026, 11, 7)) == date(2026, 11, 23)     # sobota -> poniedziałek
    assert deadline_for(date(2026, 10, 28)) == date(2026, 11, 12)    # 11.11 -> 12.11
    assert date(2026, 4, 6) in holidays(2026)                         # Poniedziałek Wielkanocny


# --- dane osobowe ---------------------------------------------------------------

def test_pii_rules_cover_common_identifiers():
    samples = ['tel. 601234567', 'tel. 52 123 45 67', 'dowód osobisty ABC123456', 'NIP 123-456-78-90',
               'zam. al. Mickiewicza 12/3', '85-001 Bydgoszcz', 'pojazd nr rej. CB 12345', 'KW BY1B/00012345/6',
               'ur. 01.02.1980 r.', 'konto 61 1090 1014 0000 0712 1981 2874']
    assert [s for s in samples if not find_pii(s)] == []


def test_amounts_are_not_phone_numbers():
    assert find_pii('Koszt wyniósł 102 230 000 zł, a uczniów było 120.') == []


def test_redactions_follow_edited_text():
    old = 'Pan X, PESEL 90010112345.'
    new = 'Dzień dobry. Pan X, PESEL 90010112345, dziękujemy.'
    r = remap_redactions(old, new, [{'start': 13, 'end': 24, 'state': 'accepted', 'category': 'PESEL', 'reason': ''}])
    assert new[r[0]['start']:r[0]['end']] == '90010112345' and r[0]['state'] == 'accepted'


def test_letter_cannot_leave_with_unreviewed_personal_data(client, monkeypatch):
    import app.services.ner
    monkeypatch.setattr(app.services.ner, 'ner_spans', lambda *_: [])
    c = mk_case(client)
    d = client.post(f"/api/cases/{c['id']}/manual-drafts").json()
    d = client.patch('/api/drafts/' + d['id'], json={'version': d['version'], 'text': 'PESEL 90010112345, e-mail jan@example.com', 'coverage': reviewed(d)}).json()
    assert {r['category'] for r in d['redactions']} == {'PESEL', 'email'}   # propozycje bez ręcznego skanowania
    assert client.post(f"/api/drafts/{d['id']}/approve", json={'version': d['version'], 'confirmed': True}).status_code == 422
    d = client.patch(f"/api/drafts/{d['id']}/redactions", json={'version': d['version'], 'redactions': [{**r, 'state': 'accepted'} for r in d['redactions']]}).json()
    # Edycja treści nie kasuje decyzji operatora.
    d = client.patch('/api/drafts/' + d['id'], json={'version': d['version'], 'text': 'Dane: PESEL 90010112345, e-mail jan@example.com', 'coverage': d['coverage']}).json()
    assert all(r['state'] == 'accepted' for r in d['redactions']) and len(d['redactions']) == 2
    assert client.post(f"/api/drafts/{d['id']}/approve", json={'version': d['version'], 'confirmed': True}).status_code == 200
    body = client.get(client.post(f"/api/drafts/{d['id']}/exports?format=txt").json()['url']).text
    assert '90010112345' not in body and 'jan@example.com' not in body


# --- import, statusy, edycja ------------------------------------------------------

def test_failed_import_can_be_retried(client, db, monkeypatch):
    from contextlib import contextmanager
    import app.worker as worker
    r = client.post('/api/imports', files={'file': ('w.pdf', b'%PDF-1.7\nX', 'application/pdf')}).json()
    @contextmanager
    def session(): yield db
    monkeypatch.setattr(worker, 'SessionLocal', session)
    monkeypatch.setattr(worker, 'extract', lambda _: (_ for _ in ()).throw(ValueError('chwilowy błąd OCR')))
    worker.execute(r['job']['id'])
    again = client.post('/api/imports', files={'file': ('w.pdf', b'%PDF-1.7\nX', 'application/pdf')}).json()
    assert again['job'] and again['document']['state'] == 'queued' and again['document']['id'] == r['document']['id']


def test_notes_do_not_reopen_closed_case_and_query_sets_kwerenda(client):
    c = mk_case(client)
    client.post(f"/api/cases/{c['id']}/events", json={'type': 'query', 'text': 'kwerenda'})
    assert client.get(f"/api/cases/{c['id']}").json()['case']['status'] == 'kwerenda'
    c = client.get(f"/api/cases/{c['id']}").json()['case']
    client.post(f"/api/cases/{c['id']}/sent", json={'version': c['version'], 'answered': today().isoformat(), 'delivery': 'e-mail'})
    client.post(f"/api/cases/{c['id']}/events", json={'type': 'material_requested', 'text': 'pytanie'})
    assert client.get(f"/api/cases/{c['id']}").json()['case']['status'] == 'zakonczony'


def test_deadline_extension_reports_days(client):
    c = mk_case(client)
    new = (date.fromisoformat(c['original_deadline']) + timedelta(days=30))
    r = client.post(f"/api/cases/{c['id']}/deadline-events", json={'version': c['version'], 'deadline': new.isoformat(), 'notified_on': today().isoformat(), 'reason': 'Kwerenda w archiwum', 'basis': 'art. 13 ust. 2 UDIP'}).json()
    assert r['status'] == 'kwerenda' and r['extension_days'] == 30


def test_assigning_unit_keeps_approved_letter_exportable(client):
    c = mk_case(client)
    d = client.post(f"/api/cases/{c['id']}/manual-drafts").json()
    d = client.patch('/api/drafts/' + d['id'], json={'version': d['version'], 'text': 'Treść odpowiedzi', 'coverage': reviewed(d)}).json()
    assert client.post(f"/api/drafts/{d['id']}/approve", json={'version': d['version'], 'confirmed': True}).status_code == 200
    case = client.get(f"/api/cases/{c['id']}").json()['case']
    body = {k: case[k] for k in ['reference', 'title', 'applicant', 'received', 'owner', 'questions', 'delivery', 'version']} | {'units': ['WE'], 'owner': 'AB'}
    assert client.patch(f"/api/cases/{c['id']}", json=body).status_code == 200
    assert client.post(f"/api/drafts/{d['id']}/exports?format=txt").status_code == 200
    assert client.get(f"/api/cases/{c['id']}").json()['case']['status'] == 'gotowy_do_eksportu'


def test_calendar_import_skips_existing_references(client, db):
    from sqlalchemy import select
    from app.models import User
    u = db.scalar(select(User).where(User.username == 'test-operator')); u.role = 'admin'; db.commit()
    existing = mk_case(client)
    rows = [{'reference': existing['reference'], 'title': 'x', 'received': '2026-01-02', 'deadline': '2026-01-16'},
            {'reference': 'TEST.' + str(uuid4()), 'title': 'nowa', 'received': '2026-01-02', 'deadline': '2026-01-16'}]
    r = client.post('/api/calendar-imports/confirm', json={'confirmed': True, 'rows': rows})
    assert r.status_code == 200 and r.json() == {'count': 1, 'skipped': [existing['reference']]}


def test_ocr_tsv_with_quotes_is_parsed(monkeypatch, tmp_path):
    import subprocess
    from PIL import Image
    from app.services import documents
    from app.config import settings
    (tmp_path / 'tmp').mkdir(); (tmp_path / 'pol.traineddata').write_bytes(b'')
    monkeypatch.setattr(settings, 'data_dir', tmp_path); monkeypatch.setattr(settings, 'tessdata_prefix', tmp_path)
    header = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
    rows = '5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t90\t"Cytat\n5\t1\t1\t1\t1\t2\t20\t0\t10\t10\t90\tdalej\n5\t1\t1\t1\t2\t1\t0\t20\t10\t10\t90\tlinia2\n'
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a, 0, (header + rows).encode(), b''))
    text, words = documents.ocr_image(Image.new('RGB', (100, 100)))
    assert text == '"Cytat dalej\nlinia2' and len(words) == 3


# --- propozycje danych rejestracyjnych ---------------------------------------------

def test_registration_suggestions_from_email_request():
    from app.services.domain import suggest_case
    text = ('Wysłano: 20 listopada 2026 10:15\nWitam,\nW trybie dostępu do informacji publicznej proszę o edytowalne '
            'zestawienie liczby uczniów w szkołach podstawowych.\n-- \nPozdrawiam | E. Góra\n')
    s = suggest_case(text, extract_questions(text), {'BKS.IV.1431.598.2026', 'BKS.IV.1431.12.2025'}, date(2026, 11, 22))
    assert s['received'] == '2026-11-20' and s['reference'] == 'BKS.IV.1431.599.2026'
    assert s['applicant'] == 'E. Góra' and s['title'].startswith('Edytowalne zestawienie liczby uczniów')
    assert s['deadline'] == '2026-12-04'


def test_registration_suggestion_uses_stamp_and_organisation():
    from app.services.domain import suggest_case
    text = 'URZĄD MIASTA BYDGOSZCZY\nData wpływu: 09.01.2026\nStowarzyszenie Obrony Zwierząt zwraca się z prośbą o informację o kosztach.'
    s = suggest_case(text, extract_questions(text), set(), date(2026, 11, 22))
    assert s['received'] == '2026-01-09' and s['applicant'].startswith('Stowarzyszenie Obrony Zwierząt') and s['reference'].endswith('.1.2026')


def test_unit_suggestion_endpoint_accepts_post(client):
    c = mk_case(client, title='Liczba uczniów w szkołach podstawowych', questions=[{'id': 'q1', 'text': 'Ilu uczniów uczy się w szkołach?'}])
    r = client.post(f"/api/cases/{c['id']}/unit-suggestions")
    assert r.status_code == 200 and r.json()[0]['id'] == 'WE'


def test_phone_at_end_of_sentence():
    assert [r['category'] for r in find_pii('Kontakt: tel. 601 234 567. Dziękuję.')] == ['telefon']


def test_ai_numbers_keep_source_formatting():
    from app.services.ai import restore_number_format
    src = 'Na koniec czerwca 2026 r.: 24 518 uczniów; koszt 2.746.693 zł.'
    assert restore_number_format('24,518 uczniów, 2746693 zł, 24,902', src) == '24 518 uczniów, 2.746.693 zł, 24,902'


def test_scan_proposals_do_not_join_lines(client, db):
    from app.models import Document
    c = mk_case(client)
    words = [{'text': 'ul.', 'box': [0.1, 0.10, 0.12, 0.12]}, {'text': 'Jezuicka', 'box': [0.13, 0.10, 0.2, 0.12]}, {'text': '1,', 'box': [0.21, 0.10, 0.22, 0.12]},
             {'text': '85-102', 'box': [0.23, 0.10, 0.28, 0.12]}, {'text': 'Bydgoszcz', 'box': [0.29, 0.10, 0.36, 0.12]},
             {'text': 'Wniosek', 'box': [0.1, 0.30, 0.17, 0.32]}, {'text': 'o', 'box': [0.18, 0.30, 0.19, 0.32]}]
    doc = Document(case_id=c['id'], name='s.pdf', kind='attachment', path='/dev/null', pdf_path='/dev/null', sha256='x', state='ready',
                   pages=[{'page': 1, 'text': '', 'words': words, 'ocr': True}])
    db.add(doc); db.commit()
    masks = client.get(f'/api/documents/{doc.id}/pages/1/proposals').json()['masks']
    assert masks and all(m['box'][1] < 0.2 for m in masks)
    assert any('85-102' in m['category'] for m in masks)


def test_request_file_attaches_to_case_imported_from_calendar(client, db):
    from app.models import Document
    c = mk_case(client, questions=[])
    up = client.post('/api/imports', files={'file': ('w.txt', ('Wniosek ' + str(uuid4())).encode(), 'text/plain')}).json()['document']
    d = db.get(Document, up['id']); d.state = 'ready'; db.commit()
    body = {'reference': c['reference'], 'title': 'x', 'received': c['received'], 'questions': [{'id': 'q1', 'text': 'Pytanie z pliku'}]}
    r = client.post(f"/api/imports/{d.id}/confirm", json={'version': d.version, 'text': 'treść', 'case': body})
    assert r.status_code == 200 and r.json()['case_id'] == c['id']
    assert client.get(f"/api/cases/{c['id']}").json()['case']['questions'][0]['text'] == 'Pytanie z pliku'


def test_email_request_greeting_headers_and_delivery():
    text = ('Od: Karol P\nWysłano: 21 listopada 2026 09:12\nTemat: wniosek\n\nDzień dobry,\nw trybie dostępu do informacji publicznej proszę o informację, jaki był w 2025 r. koszt opieki nad\n'
            'zwierzętami oraz ile psów trafiło do schroniska.\nProszę o odpowiedź na adres k@example.invalid.\n\nPozdrawiam\nKarol P\n')
    qs = extract_questions(text)
    assert len(qs) == 1 and 'koszt opieki' in qs[0]['text']
    from app.services.domain import suggest_case
    s = suggest_case(text, qs, set(), date(2026, 11, 22))
    assert s['delivery'] == 'e-mail' and s['title'].startswith('Jaki był w 2025 r. koszt') and s['applicant'] == 'Karol P'
