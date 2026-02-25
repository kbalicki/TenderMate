# TenderMate

Lokalne narzędzie webowe do analizy przetargów publicznych i zapytań ofertowych w Polsce. Scrapuje portale przetargowe, analizuje dokumentację za pomocą AI (Claude CLI) i prowadzi użytkownika przez strukturalny proces decyzyjny.

## Funkcje

- **Profil firmy** — dane firmy, zespół, portfolio, preferencje przetargowe, roczny obrót
- **Import przetargów** — z URL (scraping portali) lub ręczne wprowadzenie treści + załączników
- **Analiza AI** — 7-krokowy workflow:
  - Krok 0: Sprawdzenie warunków udziału (eligibility check)
  - Krok 1: Zakres i wymagania
  - Krok 2: Rozwiązanie techniczne (z analizą open source)
  - Krok 3: Wycena i koszty (stawka rbh × czas + margines)
  - Krok 4: Analiza ryzyk (GO/NO-GO)
  - Krok 5: Dokumenty ofertowe (wadium, lista dokumentów)
  - Krok 6: Weryfikacja dokumentów (upload + AI review)
- **Interaktywne naprawianie warunków** — wpisz uzasadnienie, AI doda do profilu firmy
- **Samorozwijający się profil** — z każdą analizą AI wzbogaca bazę wiedzy o firmie
- **Wykrywanie typu zamawiającego** — publiczny/prywatny (heurystyka + domena portalu)
- **Bulk actions** — zaznacz wiele przetargów, uruchom analizę hurtowo
- **Nawigacja tab-owa** — klikaj w kroki analizy, content się podmienia (bez scrollowania)

## Obsługiwane portale

| Portal | Scraper | Status |
|--------|---------|--------|
| [e-Zamówienia](https://ezamowienia.gov.pl) | Dedykowany (API publiczne) | Działa |
| [Baza Konkurencyjności](https://bazakonkurencyjnosci.funduszeeuropejskie.gov.pl) | Mikroserwis | Działa |
| [Logintrade](https://logintrade.net) | Dedykowany (HTML parser) | Działa |
| platformazakupowa.pl | Mikroserwis (fallback) | Działa |
| oneplace.marketplanet.pl | Mikroserwis (fallback) | Działa |
| Inne portale | Mikroserwis (fallback) | Działa |

## Stack technologiczny

| Warstwa | Technologia |
|---------|-------------|
| Backend | Python 3.12+, FastAPI, SQLAlchemy (async), SQLite, aiosqlite |
| Frontend | Vue 3, TypeScript, Tailwind CSS v4, Vite |
| AI | Claude CLI (subprocess) |
| Scraping | httpx + BeautifulSoup (dedykowane), mikroserwis (fallback) |

## Wymagania

- Python 3.12+
- Node.js 20+
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-cli) zainstalowane i skonfigurowane

## Instalacja

```bash
git clone https://github.com/kbalicki/TenderMate.git
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
API docs: **http://localhost:8000/docs**

### Auto-restart (systemd)

Aby backend i frontend restartowały się automatycznie po awarii lub restarcie systemu:

```bash
./scripts/install-services.sh
```

Logi i zarządzanie:
```bash
systemctl --user status tendermate-backend
journalctl --user -u tendermate-backend -f
systemctl --user restart tendermate-backend
```

## Konfiguracja

Opcjonalnie utwórz `backend/.env`:

```env
CLAUDE_MODEL=sonnet
DATA_DIR=./data
SCRAPER_URL=https://scraper.tools.k4.pl/scrape
```

## Struktura projektu

```
TenderMate/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routery
│   │   ├── models/       # SQLAlchemy ORM
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # Logika biznesowa (analysis, claude, scraper)
│   │   └── scrapers/     # Dedykowane scrapery (ezamowienia, logintrade)
│   └── data/             # SQLite + pliki przetargów (gitignored)
├── frontend/
│   └── src/
│       ├── pages/        # Strony (Dashboard, Profil, Przetargi, Analiza)
│       ├── components/   # Komponenty Vue
│       ├── api/          # Axios wrappery
│       └── types/        # TypeScript interfaces
└── scripts/              # Systemd services + install script
```

## Licencja

Projekt prywatny — Web Systems Krzysztof Balicki.
