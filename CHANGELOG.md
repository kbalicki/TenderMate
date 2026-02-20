# Changelog

Wszystkie istotne zmiany w projekcie TenderMate.

Format oparty na [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/).

## [0.1.0] - 2026-02-20

### Dodane

- Scaffolding backendu: FastAPI, SQLAlchemy, SQLite, Alembic-ready
- Modele ORM: User, CompanyProfile, TeamMember, PortfolioProject, Tender, TenderAttachment, Analysis, AnalysisDocument
- API endpoints: profil firmy (CRUD), przetargi (tworzenie z URL i reczne z uploadem plikow), analiza (start, eligibility fix, go/no-go, continue, dokumenty)
- Claude CLI service (`claude_service.py`) — wywolanie Claude przez subprocess w trybie print
- Szablon prompta step 0 (eligibility check)
- Analysis service z implementacja kroku 0 i placeholderami krokow 1-5
- Framework scraperow: BaseScraper ABC, registry URL-to-scraper, lista 9 obslugiwanych portali
- Scaffolding frontendu: Vue 3 + TypeScript + Vite + Tailwind CSS v4 + Pinia + vue-router
- Layout aplikacji z sidebar i nawigacja
- Strona Dashboard z podsumowaniem przetargow
- Strona Profil firmy — 4 zakladki: dane, zespol, portfolio, preferencje (pelny CRUD)
- Strona Nowy przetarg — dwa tryby: z URL i reczny (drag-and-drop zalacznikow)
- Strona Lista przetargow z filtrowaniem po statusie
- Strona Szczegoly przetargu z podgladem tresci i zalacznikow
- Strona Analiza — stepper 6-krokowy, eligibility check z opcjami naprawy, GO/NO-GO, wyswietlanie wynikow krokow 1-5
- Komponent CopyableText — blok tekstu z przyciskiem KOPIUJ do schowka
- API client (Axios) z proxy Vite na backend
- TypeScript typy dla wszystkich encji
