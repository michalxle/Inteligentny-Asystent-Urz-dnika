# Testy użytkowe — 22.11.2026

Testy ręczne wykonano w lokalnej przeglądarce pod `http://localhost:5173/`, na zalogowanym koncie administratora. PostgreSQL, worker, Ollama/Bielik, E5, NER, OCR i LibreOffice działały lokalnie. Dodano dwie osobne sprawy `QA.1431.1.2026` i `QA.1431.2.2026` z tytułami `[TEST QA]`. Materiały testowe są syntetyczne i znajdują się w ignorowanym katalogu `.data/qa/`.

## Przeprowadzone sekwencje

| Scenariusz | Czynności i wynik końcowy |
| --- | --- |
| Rejestr | Wyszukiwanie nieistniejącej sprawy → pusty wynik → wyczyszczenie → filtr zakończonych → powrót do wszystkich. Brak zawieszenia interfejsu. |
| Rejestracja ręczna | Numer, przedmiot, prowadzący i dwa pytania → zatwierdzenie → szczegóły nowej sprawy i historia. |
| Import i zastąpienie pliku | Uszkodzony PDF → komunikat błędu → poprawny TXT A → TXT B → ponownie gotowy TXT A → rejestracja. Pytania i odczyt odpowiadają ostatnio wybranemu plikowi. |
| Korekta daty | Zmiana wpływu z 22 na 21 listopada → zapis. Domyślny termin sprawy QA.2 zmienił się z 6 na 5 grudnia. |
| Lokalne AI | Wgranie materiału → zatwierdzenie odczytu → zlecenie AI → projekt z dwiema odpowiedziami: 24 drzewa i 4800 zł, zgodnie ze źródłem. |
| Pismo i anonimizacja | Korekta projektu → przegląd obu pytań → zapis → ręczne ukrycie testowego e-maila → ponowne skanowanie → pozostawienie nazwy miasta → zatwierdzenie → eksport PDF i TXT. Ręczna decyzja została zachowana, a TXT zawiera `[DANE USUNIĘTE]` zamiast e-maila. |
| Ponowny import wniosku | Wgranie tego samego pliku po jego rejestracji → komunikat o istniejącej sprawie → otwarcie QA.2. Bez ponownego przypisywania dokumentu i zmiany odczytu. |
| Wznowienie przeglądu PDF | Otwarcie syntetycznego materiału DEMO.1 → przywrócony link do kopii → wizualne sprawdzenie w przeglądarce PDF → zatwierdzenie → zamknięcie i ponowne otwarcie. Widoczny stan „Kopia zatwierdzona”. |
| Zamknięcie i eksport | Zatwierdzenie pisma QA.1 → eksport → odnotowanie symulowanej wysyłki → ponowne otwarcie pisma → kolejny eksport PDF. Sprawa pozostaje zakończona, eksport działa. |
| Pozostałe ekrany | Kalendarium, podobne sprawy, baza wiedzy, diagnostyka i menu na wąskim ekranie. Diagnostyka potwierdziła gotowość wszystkich ośmiu usług. W kalendarium na wąskim ekranie nie stwierdzono przepełnienia całej strony. |

## Błędy i poprawki

- Ponowne skanowanie pisma usuwało ręczne zakresy oraz decyzje operatora. Skan scala nowe propozycje z istniejącymi decyzjami; edycja samego tekstu nadal unieważnia poprzednie zakresy.
- Korekta wpływu zostawiała stary domyślny termin. Przeliczany jest termin automatyczny; odnotowanego osobno terminu system nie zastępuje automatycznie.
- Filtr lat wykorzystywał końcówkę sygnatury i pokazywał jako lata dowolne napisy. Wykorzystuje rok daty wpływu.
- Nieudany odczyt pozostawiał formularz w stanie „Trwa odczyt”. Formularz obsługuje nieudane zadanie, a worker zapisuje końcowy stan dokumentu `failed`.
- Zmiana między dwoma już odczytanymi importami mogła pozostawić tekst poprzedniego pliku. Aktualizacja zależy także od identyfikatora i wersji dokumentu.
- Deduplikacja nie znajdowała wniosku po przypisaniu go do sprawy. Identyczny plik wniosku wskazuje istniejącą sprawę; materiały są deduplikowane w obrębie sprawy.
- Zamknięcie okna załącznika gubiło dostęp do wygenerowanej kopii PDF. Przywracana jest aktualna kopia, a stan zatwierdzenia pozostaje widoczny po ponownym otwarciu.
- Odnotowanie wysyłki unieważniało pismo przez zmianę wersji sprawy. Aktualne projekty zachowują zgodność po tej czynności. Kontrole zmian treści i źródeł nadal obowiązują.
- Edycja zakończonej sprawy lub jej odpowiedzi mogła zmieniać etap na otwarty. Status zakończenia jest zachowywany; testy API obejmują edycję danych, zapis pisma i zatwierdzenie.
- Aktualizacja kodu przez Vite tworzyła kolejny korzeń React. Korzeń jest współdzielony między aktualizacjami modułu; ponowna aktualizacja po przeładowaniu nie dodała nowego komunikatu tego błędu.

Dodatkowo zabezpieczono tekst edytowany w oknie dokumentu przed resetowaniem przy odświeżeniu tej samej wersji i uzupełniono etykiety przycisków nawigacji.

## Testy regresji

- `.venv/bin/python -m pytest backend/tests -q --tb=short`: **20 zaliczonych**. Transakcje testowe są wycofywane.
- `npm --prefix frontend test`: **3 zaliczone**.
- `npm --prefix frontend run build`: **zaliczona kompilacja TypeScript i budowa Vite**. Pozostaje ostrzeżenie o wielkości głównego pakietu JavaScript.
- Sprawdzono rzeczywistą zawartość TXT wygenerowanego przez interfejs oraz wizualny wynik PDF po anonimizacji.
- Zrzuty: `.data/qa/odpowiedz-po-poprawkach.jpg`, `.data/qa/zalacznik-po-anonimizacji.jpg`, `.data/qa/rejestr-po-testach.jpg`. Nie są publikowane w Git.

## Zakres i ograniczenia

To ręczne testy opisanych ścieżek oraz testy regresji API. Nie oznaczają zaliczenia osobnego skryptu `frontend/tests/browser-smoke.mjs`, pełnego odbioru wszystkich funkcji, wszystkich formatów wejściowych, testu bez fizycznego dostępu do Internetu ani audytu prawnego i produkcyjnego.

Test uszkodzonego PDF pozostawił celowo nieudane zadanie w diagnostyce; jego komunikat nie oznacza niedostępności usług. Sprawy QA i pliki wynikowe pozostawiono do ponownego przeglądu. Odnotowanie wysyłki w sprawach QA było wyłącznie symulacją — aplikacja nie wysyłała żadnych wiadomości.
