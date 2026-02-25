# TenderMate

Lokalne narzędzie webowe do analizy przetargów publicznych i zapytań ofertowych w Polsce. Scrapuje portale przetargowe, analizuje dokumentację za pomocą AI (Claude) i prowadzi użytkownika przez strukturalny proces decyzyjny GO/NO-GO.

## Funkcje

- **Profil firmy** — dane firmy, zespół, portfolio, preferencje przetargowe, roczny obrót, stawka rbh
- **Import przetargów** — z URL (scraping portali) lub ręczne wprowadzenie treści + załączników
- **Analiza AI** — 7-krokowy workflow z interakcją użytkownika:
  - Krok 0: Sprawdzenie warunków udziału + wadium + kryteria oceny ofert
  - Krok 1: Zakres i wymagania (funkcjonalne, niefunkcjonalne, deliverables)
  - Krok 2: Rozwiązanie techniczne (architektura, stack, analiza open source)
  - Krok 3: Wycena i koszty + strategia punktowa (jak zdobyć max punktów w każdym kryterium)
  - Krok 4: Analiza ryzyk (macierz ryzyk, red flagi, rekomendacja GO/NO-GO)
  - Krok 5: Dokumenty ofertowe (instrukcje, wadium, checklist)
  - Krok 6: Weryfikacja dokumentów (upload + AI review)
- **Interaktywne naprawianie warunków** — wpisz uzasadnienie per warunek, AI ponownie sprawdzi eligibility (AJAX per-condition submit)
- **Samorozwijający się profil** — z każdą analizą AI wzbogaca bazę wiedzy o firmie (z deduplikacją — sprawdza istniejące dane przed dodaniem)
- **Wykrywanie typu zamawiającego** — publiczny/prywatny (heurystyka + domena portalu)
- **Szybkie odrzucanie** — przycisk "Nie spełnimy" per warunek udziału → reject + redirect
- **Statusy przetargów** — nowy, scraping, scraped, analyzing, completed, rejected, archived (termin minął)
- **AI podsumowanie** — automatyczne generowanie krótkiego opisu przetargu po scrapingu
- **Real-time progress** — SSE streaming postępu analizy z procentowym wskaźnikiem, opisem fazy i liczbą załączników
- **Upload załączników** — dodawanie brakujących dokumentów z poziomu analizy (drag & drop), auto-ekstrakcja ZIP, dedup
- **Rekurencyjna ekstrakcja ZIP** — ZIP-w-ZIP do 3 poziomów, obsługa polskich nazw plików (cp852/cp437)
- **Pobieranie ogłoszenia BZP** — automatyczny download PDF z Biuletynu Zamówień Publicznych
- **Wykrywanie duplikatów** — przy imporcie z URL i uploadu załączników sprawdzane są duplikaty
- **Multi-URL import** — wklej wiele URLi naraz (jeden na linię), każdy zostanie dodany osobno
- **Złóż ofertę** — przycisk z linkiem do portalu źródłowego po pozytywnej decyzji GO
- **Bulk re-analysis** — zaznacz wiele przetargów i uruchom ponowną analizę jednym klikiem
- **Auto-refresh** — lista przetargów automatycznie odświeża się co 5s gdy są zadania w trakcie przetwarzania
- **Ustawienia** — konfiguracja max. równoległych zadań (1-10, domyślnie 3), kontrola semafora asyncio
- **Kontrola współbieżności** — wspólny asyncio.Semaphore limitujący jednoczesny scraping i analizę

## Obsługiwane portale

| Portal | Scraper | Metoda | Formaty URL |
|--------|---------|--------|-------------|
| [e-Zamówienia](https://ezamowienia.gov.pl) | Dedykowany | API publiczne OCDS | `mp-client/search/list/ocds-148610-*`, `mo-client-board/bzp/notice-details/*` |
| [Logintrade](https://logintrade.net) | Dedykowany | HTML parser (BeautifulSoup) | `{firma}.logintrade.net/zapytania_email,*`, `{firma}.logintrade.net/portal,szczegolyZapytaniaOfertowe,*` |
| [Baza Konkurencyjności](https://bazakonkurencyjnosci.funduszeeuropejskie.gov.pl) | Mikroserwis | External scraper | dowolny URL |
| platformazakupowa.pl | Mikroserwis | External scraper | dowolny URL |
| oneplace.marketplanet.pl | Mikroserwis | External scraper | dowolny URL |
| Inne portale | Mikroserwis (fallback) | External scraper | dowolny URL |

## Stack technologiczny

| Warstwa | Technologia |
|---------|-------------|
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.0 (async), SQLite (aiosqlite) |
| Frontend | Vue 3 (Composition API), TypeScript, Tailwind CSS v4, Vite |
| AI | Claude CLI (subprocess, print mode) |
| Scraping | httpx + BeautifulSoup (dedykowane), mikroserwis zewnętrzny (fallback) |
| HTTP Client | Axios (frontend → backend), httpx (backend → external) |

## Wymagania

- Python 3.12+
- Node.js 20+
- Klucz API Anthropic (Claude) — `ANTHROPIC_API_KEY` w env

## Instalacja

```bash
git clone <repo-url>
cd TenderMate

# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Frontend
cd ../frontend
npm install
```

## Uruchomienie

```bash
# Terminal 1 — backend
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

Aplikacja dostępna pod: **http://localhost:5173**
API docs (Swagger): **http://localhost:8000/docs**

### Auto-restart (systemd)

```bash
./scripts/install-services.sh
```

Zarządzanie:
```bash
systemctl --user status tendermate-backend
journalctl --user -u tendermate-backend -f
systemctl --user restart tendermate-backend
```

## Konfiguracja

Opcjonalnie utwórz `backend/.env`:

```env
CLAUDE_MODEL=sonnet                              # model Claude (sonnet/opus/haiku)
DATA_DIR=./data                                  # katalog danych (SQLite + pliki)
SCRAPER_URL=https://scraper.tools.k4.pl/scrape   # URL mikroserwisu scrapera
```

---

## Architektura

### Struktura projektu

```
TenderMate/
├── backend/
│   ├── app/
│   │   ├── api/                # FastAPI routery
│   │   │   ├── tenders.py      #   /api/tenders — CRUD, scraping, attachments
│   │   │   ├── analysis.py     #   /api/tenders/{id}/analysis — 7-step pipeline
│   │   │   ├── company_profile.py  #   /api/company-profile — profil, zespół, portfolio
│   │   │   ├── settings.py     #   /api/settings — ustawienia aplikacji
│   │   │   └── router.py       #   Agregacja routerów
│   │   ├── models/             # SQLAlchemy ORM
│   │   │   ├── tender.py       #   Tender, TenderAttachment
│   │   │   ├── analysis.py     #   Analysis, AnalysisDocument
│   │   │   ├── verification_file.py  #   VerificationFile
│   │   │   ├── company_profile.py    #   CompanyProfile, TeamMember, PortfolioProject
│   │   │   ├── app_settings.py      #   AppSetting (key-value config)
│   │   │   └── user.py         #   User
│   │   ├── schemas/            # Pydantic schemas (request/response)
│   │   │   ├── tender.py
│   │   │   ├── analysis.py
│   │   │   └── company_profile.py
│   │   ├── services/           # Logika biznesowa
│   │   │   ├── analysis_service.py   #   Orkiestracja 7-krokowej analizy
│   │   │   ├── claude_service.py     #   Wrapper Claude API (json_mode, extract_text)
│   │   │   ├── scraper_service.py    #   Scraping + download + AI summary
│   │   │   └── concurrency.py       #   asyncio.Semaphore + max concurrent tasks
│   │   ├── scrapers/           # Dedykowane scrapery per portal
│   │   │   ├── base.py         #   detect_portal(), KNOWN_DOMAINS
│   │   │   ├── ezamowienia.py  #   API-based (OCDS ID → GetTender + GetDocuments)
│   │   │   └── logintrade.py   #   HTML-based (zapytania_email + portal format)
│   │   ├── config.py           # Settings (env vars)
│   │   ├── database.py         # SQLAlchemy async engine + session
│   │   └── main.py             # FastAPI app factory
│   └── data/                   # Runtime data (gitignored)
│       ├── tendermate.db       #   SQLite database
│       └── tenders/{id}/       #   Per-tender directory
│           └── attachments/    #     Downloaded files
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── TenderListPage.vue      # / — Dashboard + lista przetargów (merged)
│   │   │   ├── NewTenderPage.vue       # /tenders/new — Import z URL / ręczny
│   │   │   ├── TenderDetailPage.vue    # /tenders/:id — Szczegóły + załączniki
│   │   │   ├── AnalysisPage.vue        # /tenders/:id/analysis — 7-step workflow
│   │   │   ├── CompanyProfilePage.vue  # /company — Profil firmy
│   │   │   └── SettingsPage.vue        # /settings — Ustawienia aplikacji
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── AppLayout.vue       # Root wrapper
│   │   │   │   └── AppSidebar.vue      # Nawigacja boczna
│   │   │   ├── analysis/
│   │   │   │   └── CopyableText.vue    # Blok tekstu z KOPIUJ
│   │   │   └── PdfViewer.vue           # Podgląd PDF
│   │   ├── api/
│   │   │   ├── client.ts              # Axios instance (baseURL: /api)
│   │   │   ├── tenders.ts            # listTenders, createFromUrl, getTender, etc.
│   │   │   ├── analysis.ts           # startAnalysis, submitDecision, fixEligibility, etc.
│   │   │   ├── companyProfile.ts     # getProfile, updateProfile, team/portfolio CRUD
│   │   │   └── settings.ts          # getSettings, updateSettings
│   │   ├── composables/
│   │   │   └── useStatusLabels.ts    # statusLabels, getDisplayStatus, isDeadlineExpired
│   │   ├── types/
│   │   │   ├── tender.ts             # Tender, TenderDetail, PaginatedTenders
│   │   │   ├── analysis.ts           # Step0-6Result, Analysis, EligibilityCondition
│   │   │   └── companyProfile.ts     # CompanyProfile, TeamMember, PortfolioProject
│   │   └── router/
│   │       └── index.ts              # Vue Router konfiguracja
│   ├── vite.config.ts                # Vite + proxy /api → localhost:8000
│   └── package.json
└── scripts/                          # Systemd services + install script
```

### Przepływ danych

```
URL przetargu → scraper_service → dedykowany scraper / mikroserwis
     ↓
  Tender (DB) ← title, text, attachments, metadata
     ↓
  AI Summary (background) ← call_claude() → krótki opis
     ↓
  Start Analysis → analysis_service.run_step0()
     ↓
  Step 0: Eligibility → Claude sprawdza warunki vs profil firmy
     ↓                    ↑
  [nie spełnia] ←→ fixEligibility (user input) → re-run step0
     ↓
  User decision: GO → run steps 1-5 sequentially
                 NO-GO → status = rejected
     ↓
  Steps 1-5: każdy krok wysyła prompt do Claude z kontekstem przetargu + profil firmy
     ↓
  Step 6: Upload dokumentów → Claude weryfikuje kompletność
```

### API Endpoints

#### Przetargi (`/api/tenders`)

| Metoda | Endpoint | Opis |
|--------|----------|------|
| GET | `/` | Lista z paginacją, filtrami (status, search, sort) |
| POST | `/from-url` | Import z URL → background scraping |
| POST | `/manual` | Import ręczny (multipart: title, text, files) |
| GET | `/{id}` | Szczegóły z załącznikami |
| DELETE | `/{id}` | Usuń przetarg + dane |
| POST | `/{id}/rescrape` | Ponowny scraping |
| POST | `/{id}/attachments/upload` | Upload plików (ZIP auto-extract, dedup) |
| GET | `/{id}/attachments` | Lista załączników |
| GET | `/{id}/attachments/download-all` | ZIP ze wszystkimi |
| GET | `/{id}/attachments/{att_id}/download` | Pobierz plik |

#### Analiza (`/api/tenders/{id}/analysis`)

| Metoda | Endpoint | Opis |
|--------|----------|------|
| POST | `/start` | Uruchom krok 0 |
| GET | `/` | Status + wyniki |
| GET | `/stream` | SSE real-time progress (step, %, faza, załączniki) |
| POST | `/restart` | Restart od kroku 0 |
| POST | `/fix-eligibility` | Popraw warunki udziału |
| POST | `/decision` | GO / NO-GO |
| POST | `/continue` | Kontynuuj do następnego kroku |
| POST | `/verify` | Upload dokumentów do weryfikacji |
| GET | `/verification-files` | Lista uploadowanych plików |
| GET | `/documents` | Lista wygenerowanych dokumentów |
| PUT | `/documents/{doc_id}` | Oznacz dokument jako gotowy |

#### Ustawienia (`/api/settings`)

| Metoda | Endpoint | Opis |
|--------|----------|------|
| GET | `/` | Pobierz ustawienia (max_concurrent_tasks) |
| PUT | `/` | Zaktualizuj ustawienia (aktualizuje in-memory semaphore) |

#### Profil firmy (`/api/company-profile`)

| Metoda | Endpoint | Opis |
|--------|----------|------|
| GET | `/` | Pobierz/utwórz profil |
| PUT | `/` | Aktualizuj profil |
| GET/POST | `/team` | Lista / dodaj członka zespołu |
| PUT/DELETE | `/team/{id}` | Edytuj / usuń członka |
| GET/POST | `/portfolio` | Lista / dodaj projekt |
| PUT/DELETE | `/portfolio/{id}` | Edytuj / usuń projekt |

### Scrapery — jak dodać nowy portal

1. Utwórz `backend/app/scrapers/<portal>.py` z funkcją:
   ```python
   async def scrape_tender(url: str) -> dict:
       """Zwraca dict kompatybilny z scraper_service."""
       return {
           "title": str,
           "text": str,            # pełna treść ogłoszenia
           "attachments": [{"url": str, "name": str}],
           "metadata": {
               "authority": str,    # nazwa zamawiającego
               "ref_number": str,   # numer postępowania
               "deadline": str,     # termin składania ofert
           },
       }
   ```

2. Dodaj domenę do `KNOWN_DOMAINS` w `backend/app/scrapers/base.py`

3. Dodaj dispatch w `backend/app/services/scraper_service.py` w `_run_scraping()`:
   ```python
   is_my_portal = "myportal.pl" in url.lower()
   # ...
   elif is_my_portal:
       from app.scrapers.my_portal import scrape_tender as scrape_my_portal
       data = await scrape_my_portal(url)
       cookies = {}
   ```

4. (opcjonalnie) Dodaj portal do `detect_portal()` w `base.py`

### Moduły serwisowe

#### `scraper_service.py`
- Orkiestracja scrapingu: dispatch do dedykowanych scraperów lub mikroserwisu fallback
- Download załączników z cookie/header support
- **Rekurencyjna ekstrakcja ZIP** (`_extract_zip_files`): rozpakowanie ZIP-w-ZIP do 3 poziomów głębokości, dekodowanie polskich nazw plików (cp852/cp437 → UTF-8), pomijanie `__MACOSX`/`.DS_Store`
- `_download_attachment`: obsługa pre-downloaded content (`_content` key) dla plików pobranych wcześniej (np. BZP PDF)
- `_sanitize_filename`, `_guess_mime`: normalizacja nazw plików i detekcja MIME
- AI summary po zakończeniu scrapingu

#### `analysis_service.py`
- 7-krokowy pipeline analizy (step 0–6) z SSE streaming
- **Progress reporting**: emisja eventów `progress` z polami `step`, `total_steps`, `percent`, `label`, `phase`, `attachment_count`
- `_get_attachment_files`: zbiera pliki z `data_dir/attachments/`, uruchamia ekstrakcję ZIP przed analizą
- Każdy krok buduje prompt z kontekstem przetargu, profilu firmy i wyników poprzednich kroków
- Auto-wzbogacanie profilu firmy po każdej analizie (z deduplikacją)

#### `claude_service.py`
- Wrapper na Claude CLI (`claude -p --output-format json`)
- Ekstrakcja tekstu z plików: PDF (pymupdf), DOCX (python-docx), XLSX (openpyxl), plain text
- Max rozmiar pliku: **50 MB**, truncation tekstu: 100K znaków
- Robust JSON parsing: `_extract_json` (markdown fences, bracket matching), `_fix_json_quotes` (polskie cudzysłowy typograficzne)

#### `ezamowienia.py` (scraper)
- API-based scraper dla ezamowienia.gov.pl (OCDS format)
- Pobieranie dokumentów z zagnieżdżonych tablic `attachments` z deduplikacją po `object_id`
- Automatyczny download PDF ogłoszenia BZP z `search_bzp_notice` endpoint
- Parsowanie `tenderDocuments` z tender details + notice documents

### Modele danych

#### Tender
| Pole | Typ | Opis |
|------|-----|------|
| id | int | PK |
| source_type | str | "url" / "manual" |
| source_url | str | URL źródłowy |
| portal_name | str | Nazwa portalu (auto-detect) |
| title | str | Tytuł przetargu |
| contracting_authority | str | Zamawiający |
| authority_type | str | "public" / "private" |
| reference_number | str | Nr postępowania |
| submission_deadline | datetime | Termin składania ofert |
| tender_text | text | Pełna treść (po scrapingu) |
| ai_summary | str | AI-generated 2-3 zdania |
| status | str | new → scraping → scraped → analyzing → waiting_user → completed/rejected |
| data_dir | str | Ścieżka do katalogu danych |
| error_message | str | Komunikat błędu |

#### Analysis
| Pole | Typ | Opis |
|------|-----|------|
| id | int | PK |
| tender_id | int | FK → Tender |
| current_step | int | 0-6 |
| status | str | running / waiting_user / completed / error |
| step0_result — step6_result | JSON | Wyniki poszczególnych kroków |
| user_decision | str | "go" / "no_go" |

#### CompanyProfile
Dane firmy używane jako kontekst dla AI: nazwa, NIP, REGON, KRS, adres, telefon, email, strona WWW, forma prawna, rok założenia, nr konta bankowego, podpis elektroniczny, technologie, certyfikaty, stawka rbh, marginy QA/ryzyko, zespół (TeamMember[]), portfolio (PortfolioProject[]).

#### AppSetting
Key-value store dla ustawień aplikacji (np. `max_concurrent_tasks`). Tabela `app_settings` z kolumnami `key` (PK) i `value`.

## Licencja

Projekt prywatny — Web Systems Krzysztof Balicki.
