# Uruchomienie lokalnej aplikacji

## Wymagania

Python 3.12, Node 22.12+ (lub nowszy obsługiwany przez Vite), Docker z Compose, Tesseract oraz LibreOffice. Dla modeli potrzebne są lokalne pliki opisane poniżej. Wersja demonstracyjna pracuje na lokalnym hoście; konta operatorów mają wspólną przestrzeń zespołu UDIP. Nie jest to wdrożenie produkcyjne z uprawnieniami indywidualnymi do każdej sprawy.

## Instalacja

Polecenia wykonuj w katalogu głównym repozytorium.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-ai.txt
npm --prefix frontend ci
cp .env.example .env
docker compose -p umb-assistant -f infra/compose.yaml up -d db
PYTHONPATH=backend .venv/bin/python -m alembic -c backend/alembic.ini upgrade head
.venv/bin/python scripts/bootstrap.py --demo
```

Pierwsze uruchomienie tworzy konto `admin` z losowym hasłem. Dane są zapisane wyłącznie w `.data/bootstrap-credentials.json`, z uprawnieniami `0600`. Plik jest wyłączony z Git. `--demo` dodaje 10 jawnie oznaczonych syntetycznych spraw, a nie oryginalne dane z paczki UMB. Bez `--demo` powstaje tylko konto i słownik jednostek. Ponowne wywołanie nie resetuje hasła ani danych.

Port PostgreSQL dla tego projektu: `127.0.0.1:55436`. Domyślne hasło bazy w Compose służy wyłącznie lokalnemu środowisku z portem związanym z loopback. Zmiana hasła istniejącej bazy wymaga zmiany hasła w PostgreSQL, nie tylko edycji Compose.

## Zasoby AI i OCR

Pobieranie jest jawnie wykonywanym etapem przygotowania, wymagającym Internetu. Praca aplikacji nie uruchamia pobierania modeli.

- Bielik: `speakleash/Bielik-4.5B-v3.0-Instruct-GGUF`, plik `Bielik-4.5B-v3.0-Instruct.Q8_0.gguf` w `.data/models/bielik-q8.gguf`.
- Wyszukiwanie: `.venv/bin/python scripts/setup_models.py` zapisuje `intfloat/multilingual-e5-base` w `.data/models/multilingual-e5-base`.
- NER: model `pl_core_news_lg` 3.8.0 z oficjalnego wydania spaCy. Katalog zawierający `meta.json`, `config.cfg` i komponenty modelu umieść w `.data/models/pl_core_news_lg`.
- OCR: oficjalny `pol.traineddata` z `tesseract-ocr/tessdata_fast` w `.data/tessdata/`.
- Ollama: zainstalowana lokalnie albo w ignorowanym `.data/ollama-runtime/`. Silnik nie jest częścią kodu projektu; przy dystrybucji dołącz jego wymagane licencje.

Uruchomienie silnika i utworzenie aliasu modelu:

```sh
OLLAMA_NO_CLOUD=1 OLLAMA_MODELS="$PWD/.data/models/ollama" ollama serve
```

W drugim terminalu:

```sh
printf 'FROM ./bielik-q8.gguf\nPARAMETER temperature 0\nPARAMETER num_ctx 16384\n' > .data/models/Modelfile
ollama create umb-bielik -f .data/models/Modelfile
```

Jeżeli silnik jest w katalogu projektu, zastąp `ollama` przez `.data/ollama-runtime/ollama`. Tworzenie aliasu odbywa się na już działającym lokalnym serwerze. `.data/models/ollama` może zawierać dodatkową kopię wag, więc uwzględnij wolne miejsce na dysku.

## Start

```sh
.venv/bin/python scripts/dev.py
```

- Interfejs: http://127.0.0.1:5173/
- API/OpenAPI: http://127.0.0.1:8000/docs
- Logi: `.data/logs/`

Skrypt uruchamia API, worker i frontend; PostgreSQL i Ollama muszą być uruchomione osobno. `Ctrl+C` zatrzymuje trzy procesy aplikacji. Worker odzyskuje zadania po wygaśnięciu blokady; `failed` pozostaje widoczne w diagnostyce.

Po pierwszym przygotowaniu modeli można zlecić indeksowanie istniejących dokumentów:

```sh
.venv/bin/python scripts/reindex.py
```

Samo wgranie nowego dokumentu nie aktywuje go w archiwum. Operator najpierw zatwierdza odczyt. Korekta tekstu tworzy nową wersję i unieważnia zależne zatwierdzenia.

## Kontrola działania

Panel „Diagnostyka” sprawdza bazę, silnik i model, E5, NER, OCR, LibreOffice i proces roboczy. `/health/ready` zwraca 503, jeśli któryś z tych składników nie jest gotowy. Brak gotowości nie jest podstawiany fikcyjnym wynikiem AI.

```sh
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run build
.venv/bin/python scripts/check_runtime.py
.venv/bin/python scripts/smoke_ai.py
```

Testy API używają lokalnego schematu w transakcjach i wycofują dane testowe. Uruchamiaj je na bazie demonstracyjnej, nigdy na produkcyjnej.

Scenariusz automatyczny nie ma jeszcze potwierdzonego pełnego przebiegu po poprawce tabeli. Test przeglądarkowy wymaga instalacji Chromium i działa na syntetycznych danych z bootstrap oraz projekcie wygenerowanym przez `smoke_ai.py`:

```sh
cd frontend
PLAYWRIGHT_BROWSERS_PATH=../.data/playwright npx playwright install chromium
PLAYWRIGHT_BROWSERS_PATH=../.data/playwright node tests/browser-smoke.mjs
```

Zrzuty i wyniki trafiają do `.data/qa/`. Test anonimizacji zapisuje przegląd jednego syntetycznego załącznika i tworzy jego kopię. Żadne testy nie wysyłają pism do mieszkańców ani wydziałów.

## Wariant kontenerowy

```sh
docker compose -p umb-assistant -f infra/compose.yaml --profile full build
docker compose -p umb-assistant -f infra/compose.yaml --profile full run --rm api python -m alembic -c alembic.ini upgrade head
docker compose -p umb-assistant -f infra/compose.yaml --profile full run --rm api python scripts/bootstrap.py --demo
docker compose -p umb-assistant -f infra/compose.yaml --profile full up -d
```

Interfejs jest wówczas na http://127.0.0.1:8080/. Model działa na hoście, a baza wewnątrz sieci Compose. Jeśli Ollama jest związana tylko z loopback hosta, kontener może nie mieć do niej dostępu: w takim wdrożeniu należy zapewnić osiągalną usługę modelu i ograniczyć jej dostęp do sieci aplikacji. Nie należy publicznie wystawiać portu Ollama. Ten profil wymaga osobnego testu na docelowym systemie; bazowy profil sprawdzany podczas implementacji używa natywnego API/worker i kontenerowej bazy na macOS.

## Wydajność lokalnego modelu

Na komputerze bez GPU generowanie trwa od kilkudziesięciu sekund do kilku minut. Limit czasu ustawia `OLLAMA_TIMEOUT` (domyślnie 900 s). Gdy Ollama działa w maszynie wirtualnej (Docker Desktop), może uruchomić więcej wątków niż fizycznych rdzeni, co spowalnia model wielokrotnie: ustaw `OLLAMA_NUM_THREAD` na liczbę fizycznych rdzeni, np. `OLLAMA_NUM_THREAD=6 docker compose ... up -d`. Okno kontekstu jest dobierane do objętości materiałów.

## Przygotowanie do odłączenia Internetu

Zbuduj frontend, przygotuj obrazy kontenerów na architekturę docelową, zarchiwizuj lokalne wagi, OCR, fonty, zależności i ich licencje. `scripts/model_manifest.py` zapisuje wersje oraz sumy kontrolne zasobów do `.data/model-manifest.json`. Skrypt uruchomieniowy ustawia `HF_HUB_OFFLINE=1` i `TRANSFORMERS_OFFLINE=1`; Ollama uruchamiaj z `OLLAMA_NO_CLOUD=1`.

Przed odbiorem wykonaj restart całego pakietu po odłączeniu Internetu i przejdź import, OCR, wyszukiwanie, generowanie oraz eksport. Samo ustawienie flag offline i udany test lokalnego modelu nie oznaczają jeszcze zaliczenia pełnego testu izolacji sieciowej.
