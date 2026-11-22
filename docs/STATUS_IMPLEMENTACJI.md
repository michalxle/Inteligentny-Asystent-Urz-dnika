# Stan implementacji

Wersja 0.1 obejmuje lokalny prototyp aplikacji. Poniższe ograniczenia należy uwzględnić przed uznaniem całego zakresu specyfikacji za odebrany.

## Zaimplementowane moduły

- Logowanie z Argon2, sesją HttpOnly, CSRF i rolami administrator/operator. Wspólna przestrzeń zespołu UDIP.
- PostgreSQL z pgvector, migracja początkowa, syntetyczny zestaw 10 spraw.
- Rejestr od najstarszych, filtry, kalendarium, terminy i oś zdarzeń; ręczne potwierdzenie udostępnienia poza aplikacją.
- Import PDF, DOCX, DOC i TXT, lokalny OCR, korekta i zatwierdzenie treści, deduplikacja w obrębie kontekstu.
- Import kalendarium XLSX z podglądem i ostrzeżeniami o datach; oryginał pozostaje niezmieniony.
- Baza wiedzy z aktywacją/dezaktywacją i metadanymi; lokalne indeksowanie dokumentów.
- Wyszukiwanie tekstowe i wektorowe z RRF oraz przełącznikiem okresu archiwum. Brak modelu E5 jest jawnie sygnalizowany jako tryb tekstowy.
- Katalog 29 jednostek UMB (wydziały i biura z BIP) z opisem kompetencji do weryfikacji przy wdrożeniu. Podpowiedź łączy dopasowanie kompetencji z jednostkami przypisanymi do podobnych spraw z archiwum; decyzję podejmuje operator.
- Projekt odpowiedzi przez lokalny Bielik w JSON, wskazanie bieżących źródeł, kontrola liczbowych dopisków, lista braków, ręczna korekta i zatwierdzenie wersji.
- Reguły PII i lokalny NER; decyzje o zakresach tekstu oraz ręczne dodanie fragmentu do usunięcia.
- Eksport pisma TXT, DOCX, PDF i DOC; anonimizacja załączników PDF i skanów przez odtworzenie obrazów po usunięciu pikseli; zatwierdzenie wynikowej kopii i pobranie ZIP.
- Trwałe zadania w workerze, blokady wersji, kontrola aktualności eksportów i diagnostyka.

## Granice pierwszej wersji

- Pytania, przypisania jednostek i pokrycie odpowiedzi są zapisane w JSON rekordów, a nie w pełni znormalizowanych tabelach wymienionych w docelowym modelu README. API izoluje tę decyzję od interfejsu; dalsza normalizacja wymaga kolejnej migracji.
- Wersja dokumentu i historia zatwierdzeń są zachowywane, lecz nie ma jeszcze osobnego interfejsu porównywania wszystkich wcześniejszych transkrypcji. Nie zmieniaj zatwierdzonych źródeł w celu zastępowania ustawy nowym brzmieniem; wgraj nowy dokument i wyłącz poprzedni.
- Domyślny termin to 14 dni od wpływu; koniec terminu w sobotę, niedzielę lub dzień ustawowo wolny przesuwa się na najbliższy dzień roboczy (art. 57 § 4 KPA). Przedłużenie (art. 13 ust. 2 UDIP) odnotowuje operator; sprawa otrzymuje etap „Kwerenda +N dni”. Reguły prawne terminów wymagają odbioru merytorycznego przez urząd.
- Generator bazuje na bieżących materiałach sprawy. Baza wiedzy jest przeszukiwalna, ale nie służy automatycznemu doborowi przepisów ani wydawaniu decyzji prawnych. Zawiadomienia proceduralne przygotowuje się jako szkic ręczny.
- Dopasowanie odpowiedzi do wszystkich żądań i rozróżnienie np. planu od kosztu są pomocą AI oraz kontrolą człowieka, nie zweryfikowanym automatycznym rozstrzygnięciem.
- OCR pisma ręcznego jest niskiej jakości (Tesseract); przy niskiej pewności system ponawia odczyt po usunięciu linii papieru w kratkę i oznacza dokument jako wymagający przepisania. Propozycje obszarów na skanie obejmują reguły (e-mail, PESEL, telefon, adres, dokumenty) i NER na słowach OCR; podpisy i wizerunki zaznacza operator.
- Kopie załączników PDF są obrazowe, bez warstwy tekstowej i podpisu cyfrowego. Trwałe usunięcie dotyczy zaznaczonych obszarów; kompletność wyboru wymaga przejrzenia wszystkich stron.
- Starszy DOC wymaga działającego LibreOffice. Katalog jednostek jest zbiorem startowym na podstawie przykładów, a nie kompletną, zatwierdzoną mapą aktualnych kompetencji.
- Schemat początkowy jest zamrożony w migracji 0001. Dalsze zmiany wymagają kolejnych migracji.
- Nie wykonano jeszcze pełnego odbioru na nieznanym sprzęcie jury ani serwerze urzędu, fizycznego testu z odłączoną siecią, przeglądu prawnego, audytu produkcyjnego i testów obciążeniowych.

Film i prezentacja konkursowa są osobnymi materiałami do wykonania zgodnie ze specyfikacją; nie powstają automatycznie wraz z aplikacją.

## Wykonana weryfikacja

- 35 testów backendu przeszło (w tym 15 testów regresji z przeglądu zgodności z wyzwaniem) oraz 5 testów interfejsu.
- Trzy testy interfejsu sprawdzają współrzędne zaznaczeń Unicode oraz rok wpływu w rejestrze. Kompilacja TypeScript/Vite przeszła.
- Lokalny Bielik przygotował odpowiedź 120/132 uczniów na podstawie jednego syntetycznego źródła; czas jednego testu około 18 sekund. To test działania, a nie porównanie modeli ani pomiar jakości na całym archiwum.
- Potwierdzono gotowość lokalnych usług i wyszukiwanie w trybie hybrydowym.
- Sprawdzono odczyt dostarczonego DOCX, PDF z tekstem i dwóch skanów; skan drukowany 543.2026 zwrócił tekst z obu stron. Wynik pisma ręcznego jest niskiej wiarygodności i wymaga korekty. Zadziałały eksporty TXT/DOCX/PDF/DOC.
- W przeglądarce potwierdzono logowanie, filtrowanie 10 spraw, otwarcie odpowiedzi AI i ręczne utworzenie maski oraz nowej kopii PDF. Znalezioną pętlę renderowania TanStack Table usunięto przez stabilizację danych. Automatyczny skrypt przeglądarkowy pozostaje do ponownego pełnego przebiegu po tej poprawce; nie został oznaczony jako zaliczony.
- Nie wykonano fizycznego odłączenia Internetu ani pełnego testu kontenerowego profilu aplikacji.

## Poprawki po testach użytkowych 22.11.2026

- Ponowne wykrywanie danych w piśmie zachowuje ręczne zakresy i decyzje operatora. Test regresji sprawdza również wynik eksportu.
- Korekta wpływu przelicza domyślny termin; termin odnotowany osobnym zdarzeniem zostaje zachowany. Edycja zamkniętej sprawy zachowuje jej status i kontroluje kolejność dat.
- Filtr roku bazuje na dacie wpływu i obsługuje sygnatury bez roku.
- Nieudany odczyt ma komunikat błędu zamiast bezterminowego komunikatu przetwarzania. Zastąpienie importowanego pliku odświeża treść i pytania. Ponowny import już przypisanego wniosku kieruje do istniejącej sprawy.
- Odświeżenie dokumentu w tle nie resetuje edytowanego tekstu, jeśli jego wersja się nie zmieniła.
- Zakończono ręczne testy sekwencji użytkowych w lokalnej przeglądarce; opis wyników znajduje się w [TESTY_UZYTKOWE.md](TESTY_UZYTKOWE.md). Osobny skrypt automatyczny pozostaje bez potwierdzonego pełnego przebiegu.
- Po ponownym otwarciu załącznika wraca aktualna kopia PDF i stan jej zatwierdzenia. Kopie starszych wersji przeglądu nie są przywracane jako aktualne.
- Odnotowanie wysyłki nie unieważnia aktualnego pisma. Praca z odpowiedzią po zamknięciu nie zmienia sprawy ponownie w otwartą.
- Poprawiono ponowne tworzenie korzenia React podczas aktualizacji kodu przez Vite, opisy przycisków nawigacji i pusty stan bazy wiedzy.


## Poprawki zgodności z wyzwaniem — 22.11.2026

Przegląd na przykładowych materiałach UMB i poprawki:

- OCR: parser TSV Tesseracta nie łączy już wierszy przy cudzysłowie w rozpoznanym wyrazie (wcześniej treść skanu 16.2026 zawierała surowe wiersze TSV). Dodano pewność odczytu i drugą próbę po usunięciu siatki.
- Pytania z wniosku: wiersze zawinięte przez układ strony są scalane w akapity; obsługa numeracji w jednym akapicie, list po dwukropku i zdań z prośbą. Akapit po ostatnim punkcie nie jest doklejany do pytania.
- Ponowne wgranie pliku, którego odczyt się nie powiódł, wznawia przetwarzanie zamiast zwracać trwale błędny dokument.
- Anonimizacja pisma: propozycje powstają automatycznie przy każdym utworzeniu i zapisie pisma; zatwierdzenie wymaga rozpatrzenia wszystkich. Decyzje przechodzą na poprawioną treść. Podgląd pisma: szare — propozycja, czarne — do usunięcia. Rozszerzone reguły (telefon, dokument tożsamości, NIP, adresy, kod pocztowy, data urodzenia, nr rejestracyjny, księga wieczysta); NER proponuje wyłącznie osoby.
- Etapy: brak działań, zapytania wysłane do wydziałów, kwerenda (+N dni), odpowiedź w przygotowaniu, odpowiedź przygotowana, odpowiedź wysłana. Notatka nie otwiera ponownie zakończonej sprawy.
- Rejestr i kalendarium: kolor wiersza i wpisu w kalendarzu dla spraw po terminie, z terminem dziś i jutro; legenda; kolumny Lp. i data odpowiedzi, inicjały prowadzącego, oznaczenie odpowiedzi po terminie.
- Podobne sprawy: okno „ostatni rok” obejmuje także sprawy z tego samego dnia; wyniki niezwiązane tematycznie są odcinane (wspólne rdzenie wyrazów lub podobieństwo znaczeniowe bliskie najlepszemu wynikowi).
- Zmiana jednostek, prowadzącego lub terminu nie unieważnia zatwierdzonego pisma; zmiana treści sprawy nadal tak.
- Generator: limit czasu w konfiguracji (`OLLAMA_TIMEOUT`, domyślnie 900 s), okno kontekstu dopasowane do objętości materiałów, polski format dat w piśmie, wyrównanie odpowiedzi do kolejności pytań.
- Import XLSX pomija sprawy już zarejestrowane i zwraca ich listę. Interfejs pozwala oznaczyć dokument jako załącznik do udostępnienia.
