# Składniki zewnętrzne

Kod projektu korzysta z poniższych składników. Ich prawa i warunki licencyjne pozostają przy autorach; nie stanowią praw wytworzonych przez zespół konkursowy. Wersje JavaScript są w `frontend/package-lock.json`, podstawowe wersje Python w `backend/requirements*.txt`, a pełne rozwiązanie środowiska w `backend/requirements-lock.txt`.

| Składnik | Deklarowana licencja / źródło |
|---|---|
| React, Vite, Tailwind, TanStack, Tiptap Core/StarterKit | MIT; zachować noty z dystrybuowanych pakietów |
| Lucide | ISC |
| FastAPI, Pydantic, SQLAlchemy, Alembic | MIT |
| PostgreSQL i pgvector | PostgreSQL License |
| psycopg | LGPL-3.0; dołączyć wymagane informacje dla dystrybuowanych bibliotek |
| Ollama | MIT; dystrybucja silnika zawiera również licencje zależności, Metal/MLX/llama.cpp |
| Bielik 4.5B v3 Instruct GGUF | Apache-2.0; https://huggingface.co/speakleash/Bielik-4.5B-v3.0-Instruct-GGUF |
| multilingual-e5-base | MIT; https://huggingface.co/intfloat/multilingual-e5-base |
| spaCy oraz pl_core_news_lg | MIT; sprawdzić także noty danych modelu w jego `meta.json` i plikach licencji |
| Tesseract i pol.traineddata | Apache-2.0 |
| pypdf | BSD-3-Clause |
| pypdfium2 / PDFium | Apache-2.0 lub BSD-3-Clause dla wrappera; PDFium i jego zależności zawierają dodatkowe noty |
| Pillow | HPND |
| ReportLab, python-docx, openpyxl | BSD dla ReportLab; MIT dla python-docx i openpyxl |
| LibreOffice | MPL-2.0 / LGPL; wymagane noty jego dystrybucji |
| pytest, Vitest, Playwright | MIT dla pytest i Vitest; Apache-2.0 dla Playwright |

Wykaz jest pomocą do przygotowania dystrybucji. Pakiet przekazywany organizatorowi musi zawierać właściwe pliki LICENSE/NOTICE dla faktycznych wersji bibliotek, modeli, fontów i obrazów systemowych. Fonty hosta wykorzystane podczas lokalnego testu nie są automatycznie objęte prawem redystrybucji; obraz Linux używa DejaVu z pakietu systemowego. Nie dołączaj fontów macOS do paczki dla innych systemów.
