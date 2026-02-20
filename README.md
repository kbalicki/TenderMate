# TenderMate

Lokalne narzedzie webowe do analizy przetargow publicznych w Polsce. Scrapuje portale przetargowe, analizuje dokumentacje za pomoca AI (Claude CLI) i prowadzi uzytkownika przez strukturalny proces decyzyjny.

## Funkcje

- **Profil firmy** — dane firmy, zespol, portfolio, preferencje przetargowe
- **Import przetargow** — z URL (scraping 9 portali) lub reczne wprowadzenie tresci + zalacznikow
- **Analiza AI** — 6-krokowy workflow:
  - Krok 0: Sprawdzenie warunkow udzialu (eligibility check)
  - Krok 1: Lista wymaganych dokumentow
  - Krok 2: Pozycje wyceny, kryteria oceny, terminy, personel
  - Krok 3: Analiza ryzyk
  - Krok 4: Estymacja kosztow
  - Krok 5: Wytyczne do dokumentow (z przyciskiem KOPIUJ)
- **Predefined options** — klikalne opcje zamiast czatu, oszczednosc czasu

## Obslugiwane portale

| Portal | Status |
|---|---|
| ezamowienia.gov.pl | Planowany |
| bazakonkurencyjnosci.funduszeeuropejskie.gov.pl | Planowany |
| oneplace.marketplanet.pl | Planowany |
| platformazakupowa.pl | Planowany |
| platformaofertowa.pl | Planowany |
| platforma.eb2b.com.pl | Planowany |
| e-propublico.pl | Planowany |
| ted.europa.eu | Planowany |
| platformazakupowa.logintrade.pl | Planowany |

## Stack technologiczny

| Warstwa | Technologia |
|---|---|
| Backend | Python 3.12+, FastAPI, SQLAlchemy, SQLite |
| Frontend | Vue 3, TypeScript, Tailwind CSS, Pinia |
| AI | Claude CLI (subprocess, bez kosztow API) |
| Scraping | Playwright (headless Chromium) |

## Wymagania

- Python 3.12+
- Node.js 20+
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-cli) zainstalowane i skonfigurowane
- Chromium (instalowany przez Playwright)

## Instalacja

```bash
# Klonowanie
git clone https://github.com/kbalicki/TenderMate.git
cd TenderMate

# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
cp .env .env.local  # opcjonalnie dostosuj

# Frontend
cd ../frontend
npm install
```

## Uruchomienie

```bash
# Terminal 1 — backend
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

Lub jednym poleceniem:

```bash
./scripts/dev.sh
```

Aplikacja dostepna pod: **http://localhost:5173**
API docs: **http://localhost:8000/docs**

## Struktura projektu

```
TenderMate/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routery
│   │   ├── models/       # SQLAlchemy ORM
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # Logika biznesowa + Claude CLI
│   │   ├── scrapers/     # Plugin per portal
│   │   └── prompts/      # Szablony promptow AI
│   └── data/             # SQLite + pliki przetargow (gitignored)
├── frontend/
│   └── src/
│       ├── pages/        # Strony (Dashboard, Profil, Przetargi, Analiza)
│       ├── components/   # Komponenty Vue
│       ├── api/          # Axios wrappery
│       └── types/        # TypeScript interfaces
└── scripts/              # Skrypty dev
```

## Licencja

Projekt prywatny — Web Systems Krzysztof Balicki.
