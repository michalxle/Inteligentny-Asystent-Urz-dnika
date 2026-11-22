"""Create first administrator and optional, explicitly synthetic demonstration data."""
import sys, secrets, json, argparse
from pathlib import Path
project_root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(project_root/'backend' if (project_root/'backend').exists() else project_root))
from sqlalchemy import select
from app.config import settings
from app.db import SessionLocal
from app.models import User, Case, Unit, Document, Chunk, uid
from app.auth import hasher
from app.services.domain import today, deadline_for, extract_questions
from app.services.documents import export_letter, digest

UNITS=[
('WAB','Wydział Administracji Budowlanej','pozwolenie na budowę projekt budowlany zgłoszenie robót budowlanych dokumentacja budowy apartamentowiec budynek rozbiórka samowola budowlana warunki techniczne'),
('WE','Wydział Edukacji i Sportu','szkoły przedszkola uczniowie edukacja nauczyciele oświata sport obiekty sportowe baseny kluby sportowe stypendia cudzoziemcy obcokrajowcy w szkołach'),
('WF','Wydział Funduszy Europejskich','fundusze europejskie dotacje unijne dofinansowanie projekty unijne wnioski o płatność umowa o dofinansowanie'),
('WGO','Wydział Gospodarki Odpadami','odpady komunalne odbiór odpadów opłata za gospodarowanie odpadami deklaracje odpadowe segregacja PSZOK liczba mieszkańców z deklaracji'),
('WI','Wydział Informatyki','informatyka systemy teleinformatyczne oprogramowanie licencje sprzęt komputerowy sieć'),
('WIM','Wydział Inwestycji Miasta','inwestycje miejskie budowa przebudowa remont umowa z wykonawcą roboty budowlane kompleks Astoria basen harmonogram inwestycji protokoły odbioru aneksy faktury inwestycji kierownik robót'),
('WK','Wydział Księgowości','księgowość płatności faktury przelewy rozliczenia finansowe ewidencja wydatków'),
('WMG','Wydział Mienia i Geodezji','nieruchomości grunty działki sprzedaż dzierżawa najem mienie gminy geodezja księgi wieczyste użytkowanie wieczyste'),
('WOŚ','Wydział Ochrony Środowiska','ochrona środowiska wycinka drzew zezwolenia środowiskowe powietrze hałas zwierzęta łowiectwo decyzje środowiskowe'),
('WOA','Wydział Organizacyjno-Administracyjny','organizacja urzędu regulamin organizacyjny zarządzenia prezydenta kadry zatrudnienie wynagrodzenia pracowników samochody służbowe zaopatrzenie urzędu'),
('WPL','Wydział Podatków i Opłat Lokalnych','podatek od nieruchomości podatki lokalne opłaty lokalne ulgi podatkowe umorzenia opłata targowa'),
('WSO','Wydział Spraw Obywatelskich','sprawy obywatelskie dowody osobiste meldunki ewidencja ludności działalność gospodarcza CEIDG zezwolenia na sprzedaż alkoholu punkty sprzedaży alkoholu'),
('WSR','Wydział Świadczeń Rodzinnych','świadczenia rodzinne zasiłki świadczenie wychowawcze fundusz alimentacyjny dodatki mieszkaniowe'),
('WUK','Wydział Uprawnień Komunikacyjnych','prawo jazdy rejestracja pojazdów uprawnienia komunikacyjne licencje taxi transport drogowy'),
('WW','Wydział Windykacji','windykacja zaległości należności egzekucja dłużnicy'),
('WZP','Wydział Zamówień Publicznych','zamówienia publiczne przetargi postępowania przetargowe oferty specyfikacja wykonawcy umowy w sprawie zamówienia'),
('WZB','Wydział Zarządzania Budżetem Miasta','budżet miasta wydatki dochody uchwała budżetowa zadłużenie miasta kredyty sprawozdania budżetowe koszty'),
('WZK','Wydział Zarządzania Kryzysowego i Ochrony Ludności','zarządzanie kryzysowe obrona cywilna ochrona ludności schrony powódź bezpieczeństwo imprezy masowe'),
('WGK','Wydział Zieleni i Gospodarki Komunalnej','zieleń miejska parki drzewa utrzymanie zieleni gospodarka komunalna bezdomne zwierzęta schronisko opieka nad zwierzętami wyłapywanie zwierząt cmentarze szalety'),
('BAS','Biuro Aktywności Społecznej','organizacje pozarządowe stowarzyszenia fundacje budżet obywatelski konsultacje społeczne dotacje dla organizacji wolontariat seniorzy rady osiedli'),
('BCB','Biuro Cyfryzacji i Bezpieczeństwa Informacji','cyfryzacja bezpieczeństwo informacji ochrona danych osobowych RODO cyberbezpieczeństwo'),
('BZS','Biuro ds. Zdrowia i Polityki Społecznej','zdrowie programy zdrowotne polityka społeczna profilaktyka uzależnienia osoby niepełnosprawne pomoc społeczna'),
('BKS','Biuro Komunikacji Społecznej','informacja publiczna koordynacja wniosków komunikacja z mieszkańcami skargi wnioski petycje'),
('BKZ','Biuro Konserwatora Zabytków','zabytki konserwator rejestr zabytków ochrona zabytków rewitalizacja kamienice pomniki'),
('BKB','Biuro Kultury Bydgoskiej','kultura instytucje kultury wydarzenia kulturalne festiwale rzeźby pomniki sztuka w przestrzeni publicznej muzea teatry biblioteki'),
('BPR','Biuro Prasowe','prasa media rzecznik prasowy komunikaty wywiady'),
('BP','Biuro Promocji Miasta i Współpracy z Zagranicą','promocja miasta reklama kampanie promocyjne miasta partnerskie współpraca zagraniczna sponsoring'),
('BRM','Biuro Rady Miasta','rada miasta radni sesje uchwały rady komisje rady interpelacje głosowania'),
('BZIT','Biuro ZIT','zintegrowane inwestycje terytorialne ZIT obszar metropolitalny projekty ZIT'),
]
TOPICS=[('Liczba uczniów w szkołach podstawowych','1. Ilu uczniów uczyło się w szkole demonstracyjnej w czerwcu 2026?\n2. Ilu uczniów uczyło się w tej szkole we wrześniu 2026?','WE'),('Opieka nad bezdomnymi zwierzętami','1. Jaki był rzeczywisty koszt opieki nad zwierzętami w 2025 roku?','WGK'),('Dokumentacja inwestycji miejskiej','1. Proszę o dokumentację budowy demonstracyjnego obiektu.','WIM'),('Liczba mieszkańców według deklaracji odpadowych','1. Proszę o zbiorczą liczbę mieszkańców dla wskazanych ulic.','WGO'),('Udostępnienie projektu budowlanego','1. Proszę o projekt zagospodarowania terenu.','WAB'),('Zezwolenia na sprzedaż alkoholu','1. Ile zezwoleń wydano w roku 2025?','WSO'),('Zestawienie uczniów za rok 2025','1. Jaka była liczba uczniów w szkole demonstracyjnej w 2025?','WE'),('Utrzymanie zieleni miejskiej','1. Ile kosztowało utrzymanie zieleni w 2025?','WGK'),('Harmonogram remontu obiektu','1. Proszę o harmonogram remontu obiektu demonstracyjnego.','WIM'),('Odbiór odpadów komunalnych','1. Proszę o informacje o zasadach odbioru odpadów.','WGO')]

def run(demo=False):
    from datetime import timedelta
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.username=='admin')):
            password=secrets.token_urlsafe(18);db.add(User(username='admin',password_hash=hasher.hash(password),role='admin'))
            target=settings.data_dir/'bootstrap-credentials.json';target.write_text(json.dumps({'username':'admin','password':password}));target.chmod(0o600)
            print('Utworzono administratora. Dane logowania: .data/bootstrap-credentials.json (niepublikowane).')
        for ident,name,description in UNITS:
            # Lista jednostek: BIP UM Bydgoszczy (wydziały i biura); opis kompetencji do weryfikacji przy wdrożeniu.
            unit=db.get(Unit,ident)
            if not unit:db.add(Unit(id=ident,name=name,description=description,source='BIP UM Bydgoszczy; kompetencje do weryfikacji przy wdrożeniu'))
            elif unit.source.startswith(('Przykłady historyczne','BIP UM')):unit.name=name;unit.description=description;unit.source='BIP UM Bydgoszczy; kompetencje do weryfikacji przy wdrożeniu'
        db.flush()
        if demo and not db.scalar(select(Case).where(Case.reference.like('DEMO.%'))):
            for i,(title,request,unit) in enumerate(TOPICS):
                received=today()-timedelta(days=[14,13,17,10,7,2,370,8,5,4][i]);due=deadline_for(received)
                c=Case(reference=f'DEMO.1431.{i+1}.{received.year}',title=title+' [DANE SYNTETYCZNE]',applicant='Wnioskodawca demonstracyjny',received=received,original_deadline=due,deadline=due,owner='Operator '+str(i%2+1),questions=extract_questions(request),units=[unit],warnings=['Dane syntetyczne do demonstracji'],answered=min(today(),received+timedelta(days=10)) if i in [5,6,8] else None,status='zakonczony' if i in [5,6,8] else 'oczekuje_na_materialy')
                db.add(c);db.flush()
                texts=[('request',request)]
                if i==0:texts.append(('material','MATERIAŁ SYNTETYCZNY — odpowiedź Wydziału Edukacji.\nW czerwcu 2026 szkoła demonstracyjna miała 120 uczniów.\nWe wrześniu 2026 szkoła demonstracyjna miała 132 uczniów.\nKontakt osoby prywatnej do usunięcia: jan.test@example.invalid\nPESEL testowy: 90010112345'))
                if i==6:texts.append(('material','MATERIAŁ SYNTETYCZNY. W 2025 szkoła demonstracyjna miała 110 uczniów.'))
                for kind,body in texts:
                    ident=uid();path=settings.data_dir/'files'/(ident+'.txt');path.write_text(body)
                    pdf=path.with_suffix('.pdf');export_letter(body,'pdf',pdf)
                    d=Document(id=ident,case_id=c.id,name=f'demo-{i+1}-{kind}.txt',kind=kind,unit_id=unit,path=str(path),pdf_path=str(pdf),sha256=digest(path),text=body,pages=[{'page':1,'text':body,'words':[],'ocr':False}],active=True,state='ready',metadata_={'synthetic':True,'indexed':False});db.add(d);db.flush();db.add(Chunk(document_id=d.id,page=1,text=body))
            print('Dodano 10 spraw i materiały syntetyczne. Oryginalna paczka UMB nie została zmodyfikowana.')
        db.commit()
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--demo',action='store_true');run(parser.parse_args().demo)
