"""Orchestrates multi-step tender analysis workflow using Claude CLI."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.analysis import Analysis
from app.models.analysis_document import AnalysisDocument
from app.models.company_profile import CompanyProfile
from app.models.tender import Tender
from app.services.claude_service import call_claude

logger = logging.getLogger(__name__)

# In-memory event queues for SSE streaming (keyed by analysis_id)
_event_queues: dict[int, list[asyncio.Queue]] = {}


def subscribe(analysis_id: int) -> asyncio.Queue:
    """Subscribe to SSE events for an analysis."""
    queue: asyncio.Queue = asyncio.Queue()
    _event_queues.setdefault(analysis_id, []).append(queue)
    return queue


def unsubscribe(analysis_id: int, queue: asyncio.Queue) -> None:
    """Unsubscribe from SSE events."""
    if analysis_id in _event_queues:
        _event_queues[analysis_id] = [q for q in _event_queues[analysis_id] if q is not queue]
        if not _event_queues[analysis_id]:
            del _event_queues[analysis_id]


async def _emit(analysis_id: int, event: str, data: dict) -> None:
    """Send event to all SSE subscribers."""
    if analysis_id in _event_queues:
        msg = {"event": event, "data": data}
        for queue in _event_queues[analysis_id]:
            await queue.put(msg)


# --- Company context ---

def _build_company_context(profile: CompanyProfile) -> str:
    """Serialize company profile for Claude prompt."""
    return json.dumps(
        {
            "company_name": profile.company_name,
            "nip": profile.nip,
            "regon": profile.regon,
            "krs": profile.krs,
            "address": f"{profile.address_street}, {profile.address_postal_code} {profile.address_city}",
            "phone": profile.phone,
            "email": profile.email,
            "website": profile.website,
            "contact_person": profile.contact_person,
            "bank_account": profile.bank_account,
            "description": profile.description,
            "technologies": profile.technologies,
            "certifications": profile.certifications,
            "team": [
                {
                    "name": m.full_name,
                    "role": m.role,
                    "experience_years": m.experience_years,
                    "qualifications": m.qualifications,
                    "bio": m.bio,
                }
                for m in profile.team_members
            ],
            "portfolio": [
                {
                    "project": p.project_name,
                    "client": p.client_name,
                    "description": p.description,
                    "value_pln": p.contract_value_pln,
                    "year_started": p.year_started,
                    "year_completed": p.year_completed,
                    "technologies": p.technologies_used,
                }
                for p in profile.portfolio_projects
            ],
            "hourly_rate_pln": profile.hourly_rate_pln,
            "qa_buffer_pct": profile.qa_buffer_pct,
            "risk_buffer_pct": profile.risk_buffer_pct,
            "annual_revenue_pln": profile.annual_revenue_pln,
        },
        ensure_ascii=False,
        indent=2,
    )


async def enrich_profile_from_text(text: str, add_to_portfolio: bool = False) -> None:
    """Use Claude to extract structured data from user text and add to company profile.

    Includes existing profile data as context so AI can detect duplicates and
    suggest updates to existing entries rather than creating new ones.
    """
    from app.models.company_profile import CompanyProfile
    from app.models.team_member import TeamMember
    from app.models.portfolio_project import PortfolioProject

    # First, fetch existing profile data for deduplication context
    async with async_session() as db:
        from sqlalchemy.orm import selectinload
        res = await db.execute(
            select(CompanyProfile).options(
                selectinload(CompanyProfile.team_members),
                selectinload(CompanyProfile.portfolio_projects),
            ).where(CompanyProfile.user_id == 1)
        )
        profile = res.scalar_one_or_none()
        if not profile:
            return

    # Build context of existing data for deduplication
    existing_projects = []
    for p in profile.portfolio_projects:
        existing_projects.append({
            "id": p.id,
            "project_name": p.project_name,
            "client_name": p.client_name,
            "description": (p.description or "")[:200],
        })
    existing_members = []
    for m in profile.team_members:
        existing_members.append({
            "id": m.id,
            "full_name": m.full_name,
            "role": m.role,
            "qualifications": (m.qualifications or "")[:200],
        })
    existing_techs = profile.technologies or []
    existing_certs = profile.certifications or []

    prompt = f"""Na podstawie poniższego tekstu użytkownika wyciągnij dane firmy.
Tekst może opisywać: projekt (referencję), osobę w zespole, certyfikat, technologię, lub ogólne informacje o firmie.

WAŻNE: Poniżej podaję ISTNIEJĄCE dane firmy. Sprawdź czy tekst użytkownika nie dotyczy czegoś co JUŻ JEST w profilu.
- Jeśli projekt/osoba/technologia już istnieje — ustaw action="update" i podaj id istniejącego elementu.
- Jeśli to coś nowego — ustaw action="add".
- NIE DUPLIKUJ istniejących danych.

ISTNIEJĄCE PROJEKTY PORTFOLIO:
{json.dumps(existing_projects, ensure_ascii=False)}

ISTNIEJĄCY ZESPÓŁ:
{json.dumps(existing_members, ensure_ascii=False)}

ISTNIEJĄCE TECHNOLOGIE: {json.dumps(existing_techs, ensure_ascii=False)}
ISTNIEJĄCE CERTYFIKATY: {json.dumps(existing_certs, ensure_ascii=False)}

Tekst użytkownika:
{text}

Odpowiedz TYLKO jako JSON:
{{
  "portfolio_projects": [
    {{
      "action": "add" lub "update",
      "existing_id": null lub id istniejącego projektu,
      "project_name": "nazwa projektu",
      "client_name": "nazwa klienta lub null",
      "description": "opis projektu",
      "contract_value_pln": null,
      "year_started": null,
      "year_completed": null,
      "technologies_used": ["tech1"]
    }}
  ],
  "team_members": [
    {{
      "action": "add" lub "update",
      "existing_id": null lub id istniejącego członka,
      "full_name": "imię i nazwisko",
      "role": "rola",
      "experience_years": null,
      "qualifications": "kwalifikacje",
      "bio": "krótki opis"
    }}
  ],
  "technologies": ["nowa_technologia"],
  "certifications": ["nowy_certyfikat"],
  "description_addition": "tekst do dopisania do opisu firmy lub null"
}}

Wypełnij TYLKO te pola, dla których znalazłeś dane w tekście. Puste tablice dla reszty.
Dla technologies i certifications podaj TYLKO te, których NIE MA jeszcze w profilu."""

    result = _safe_result(await call_claude(prompt, system_prompt="Wyciągnij dane z tekstu. Sprawdź duplikaty. Zwróć TYLKO JSON."))

    async with async_session() as db:
        from sqlalchemy.orm import selectinload
        res = await db.execute(
            select(CompanyProfile).options(
                selectinload(CompanyProfile.team_members),
                selectinload(CompanyProfile.portfolio_projects),
            ).where(CompanyProfile.user_id == 1)
        )
        profile = res.scalar_one_or_none()
        if not profile:
            return

        # Handle portfolio projects (update existing always, add new only if add_to_portfolio)
        for proj in result.get("portfolio_projects", []):
            if not proj.get("project_name"):
                continue
            action = proj.get("action", "add")
            existing_id = proj.get("existing_id")

            if action == "update" and existing_id:
                # Update existing project — always allowed (no need for add_to_portfolio flag)
                existing = next((p for p in profile.portfolio_projects if p.id == existing_id), None)
                if existing:
                    if proj.get("description"):
                        existing.description = proj["description"]
                    if proj.get("client_name"):
                        existing.client_name = proj["client_name"]
                    if proj.get("contract_value_pln"):
                        existing.contract_value_pln = proj["contract_value_pln"]
                    if proj.get("year_started"):
                        existing.year_started = proj["year_started"]
                    if proj.get("year_completed"):
                        existing.year_completed = proj["year_completed"]
                    if proj.get("technologies_used"):
                        existing.technologies_used = proj["technologies_used"]
                    logger.info(f"[Profile] Zaktualizowano projekt: {existing.project_name}")
            elif add_to_portfolio:
                # Add new project — only when checkbox is checked
                existing_names = [p.project_name.lower() for p in profile.portfolio_projects]
                if proj["project_name"].lower() not in existing_names:
                    db.add(PortfolioProject(
                        company_profile_id=profile.id,
                        project_name=proj["project_name"],
                        client_name=proj.get("client_name"),
                        description=proj.get("description"),
                        contract_value_pln=proj.get("contract_value_pln"),
                        year_started=proj.get("year_started"),
                        year_completed=proj.get("year_completed"),
                        technologies_used=proj.get("technologies_used", []),
                    ))

        # Handle team members (add or update)
        for member in result.get("team_members", []):
            if not member.get("full_name"):
                continue
            action = member.get("action", "add")
            existing_id = member.get("existing_id")

            if action == "update" and existing_id:
                existing = next((m for m in profile.team_members if m.id == existing_id), None)
                if existing:
                    if member.get("role"):
                        existing.role = member["role"]
                    if member.get("experience_years"):
                        existing.experience_years = member["experience_years"]
                    if member.get("qualifications"):
                        existing.qualifications = member["qualifications"]
                    if member.get("bio"):
                        existing.bio = member["bio"]
                    logger.info(f"[Profile] Zaktualizowano członka zespołu: {existing.full_name}")
            else:
                existing_names = [m.full_name.lower() for m in profile.team_members]
                if member["full_name"].lower() not in existing_names:
                    db.add(TeamMember(
                        company_profile_id=profile.id,
                        full_name=member["full_name"],
                        role=member.get("role"),
                        experience_years=member.get("experience_years"),
                        qualifications=member.get("qualifications"),
                        bio=member.get("bio"),
                    ))

        # Add technologies (AI already filters out existing ones)
        new_techs = result.get("technologies", [])
        if new_techs and isinstance(profile.technologies, list):
            existing = [t.lower() for t in profile.technologies]
            for tech in new_techs:
                if tech and tech.lower() not in existing:
                    profile.technologies = [*profile.technologies, tech]

        # Add certifications (AI already filters out existing ones)
        new_certs = result.get("certifications", [])
        if new_certs and isinstance(profile.certifications, list):
            existing = [c.lower() for c in profile.certifications]
            for cert in new_certs:
                if cert and cert.lower() not in existing:
                    profile.certifications = [*profile.certifications, cert]

        # Append to description
        desc_add = result.get("description_addition")
        if desc_add and isinstance(desc_add, str) and desc_add.strip():
            current = profile.description or ""
            if desc_add.strip() not in current:
                profile.description = (current + "\n" + desc_add.strip()).strip()

        await db.commit()
        logger.info(f"[Profile] Wzbogacono profil firmy na podstawie tekstu użytkownika")


def _get_attachment_files(tender: Tender) -> list[Path]:
    """Get all attachment file paths for a tender.

    ZIP files are auto-extracted in-place (recursively) so their contents can be analysed.
    """
    if not tender.data_dir:
        return []
    att_dir = Path(tender.data_dir) / "attachments"
    if not att_dir.exists():
        return []

    # Use scraper_service's robust ZIP extraction (recursive, Polish encoding)
    from app.services.scraper_service import _extract_zip_files, _sanitize_filename
    all_files = [f for f in att_dir.iterdir() if f.is_file()]
    extracted = _extract_zip_files(all_files, att_dir)
    if extracted:
        logger.info(f"[Attachments] Wyekstrahowano {len(extracted)} plików z ZIP-ów")

    result = [f for f in att_dir.iterdir() if f.is_file()]
    logger.info(f"[Attachments] Znaleziono {len(result)} plików: {[f.name for f in result]}")
    return result


SYSTEM_PROMPT = (
    "Jesteś krytycznym asystentem do analizy przetargów publicznych w Polsce. "
    "Pracujesz sceptycznie: nie przytakujesz, tylko weryfikujesz wymagania i wyłapujesz ryzyka formalne. "
    "Nigdy się nie domyślaj — jeśli czegoś nie wiesz lub brakuje informacji, zaznacz to wyraźnie. "
    "Gdy przywołujesz wymaganie lub ryzyko — odwołuj się do konkretnego miejsca w dokumentach "
    "(nazwa dokumentu, rozdział/paragraf/punkt/załącznik). "
    "Firma jest software house'em (JDG, tworzenie oprogramowania na zamówienie, wdrożenia open source). "
    "Jeśli zamówienie dotyczy dostawy licencji gotowego oprogramowania lub wymaga statusu "
    "autoryzowanego partnera producenta — traktuj to jako niespełnienie warunku. "
    "W przypadku niejednoznacznych zapisów nie zakładaj interpretacji na korzyść firmy. "
    "Odpowiadaj po polsku. Zwracaj WYŁĄCZNIE valid JSON bez dodatkowego tekstu."
)


def _safe_result(result: Any) -> dict:
    """Extract dict from Claude result, handling string/markdown fallback."""
    if isinstance(result, dict):
        # Handle case where previous _safe_result wrapped in {"raw": ...}
        if "raw" in result and len(result) == 1:
            from app.services.claude_service import _extract_json
            inner = result["raw"]
            extracted = _extract_json(inner) if isinstance(inner, str) else None
            if isinstance(extracted, dict):
                return extracted
        return result
    from app.services.claude_service import _extract_json
    if isinstance(result, str):
        extracted = _extract_json(result)
        if isinstance(extracted, dict):
            return extracted
    logger.warning(f"[Analysis] _safe_result nie sparsował wyniku: {str(result)[:200]}")
    return {"raw": result}


# --- Step implementations ---

async def run_step0(
    tender: Tender,
    profile: CompanyProfile,
    fix_context: str | None = None,
) -> dict:
    """Step 0: Eligibility check — warunki udziału w postępowaniu."""
    company_json = _build_company_context(profile)
    attachments = _get_attachment_files(tender)

    prompt = f"""Analizujesz polski przetarg pod kątem spełniania warunków udziału w postępowaniu.

## Profil firmy:
{company_json}

## Treść przetargu:
{tender.tender_text or "(brak tekstu — analizuj na podstawie załączników)"}
"""
    if fix_context:
        prompt += f"\n## Podjęte działania naprawcze przez firmę:\n{fix_context}\n"

    prompt += """
Sprawdź czy firma spełnia WSZYSTKIE warunki udziału w postępowaniu.
Sprawdź: uprawnienia/koncesje/licencje, doświadczenie (realizacje, min. wartości, liczba projektów),
personel (role, certyfikaty, lata doświadczenia), sytuacja ekonomiczna/finansowa (OC, przychody),
brak podstaw wykluczenia (Pzp), inne warunki szczególne (lokalizacja, czas reakcji, ISO, itp.).

TWARDA REGUŁA: Jeśli choć jeden warunek nie jest spełniony i nie da się go realnie naprawić
(np. wymaga konsorcjum, podwykonawcy, uzupełnienia certyfikatów, polisy OC, innej referencji) —
zaznacz to jednoznacznie. Sztuczne obejścia i naginanie profilu firmy = niespełnienie warunku.

Dla każdego niespełnionego warunku podaj REALNE opcje naprawy:
- konsorcjum z inną firmą
- podwykonawca z wymaganymi uprawnieniami
- uzupełnienie personelu / certyfikatów
- uzyskanie polisy OC
- inna referencja z portfolio
Jeśli żadna opcja nie jest realna — napisz "brak realnych opcji naprawy".

Odpowiedz TYLKO jako JSON (bez markdown, bez ```):
{
  "eligible": true lub false,
  "conditions": [
    {
      "name": "nazwa warunku po polsku",
      "description": "co jest wymagane wg dokumentacji",
      "met": true lub false,
      "reason": "dlaczego spełniony/niespełniony — odwołaj się do konkretnego miejsca w dokumentach (SWZ pkt X.Y, OPZ rozdz. Z)",
      "fixable": true lub false,
      "fix_options": ["opcja naprawcza 1 — realna i konkretna", "opcja 2"]
    }
  ],
  "summary": "krótkie podsumowanie oceny (2-3 zdania po polsku)",
  "scope_description": "co trzeba zrealizować w ramach zamówienia (3-5 zdań po polsku, zrozumiałe dla nietechnicznej osoby)",
  "estimated_budget": "budżet z dokumentacji, lub szacunek z uzasadnieniem, lub 'nieokreślony'"
}"""

    return _safe_result(await call_claude(prompt, context_files=attachments, system_prompt=SYSTEM_PROMPT))


async def run_step1(tender: Tender, profile: CompanyProfile) -> dict:
    """Step 1: Scope & Requirements Analysis — dekompozycja zakresu."""
    company_json = _build_company_context(profile)
    attachments = _get_attachment_files(tender)

    prompt = f"""Na podstawie dokumentacji przetargowej (SWZ, OPZ, załączniki) dokonaj SZCZEGÓŁOWEJ dekompozycji zakresu zamówienia.

## Profil firmy:
{company_json}

## Treść przetargu:
{tender.tender_text or "(brak tekstu — analizuj na podstawie załączników)"}

Twoim zadaniem jest wyciągnięcie WSZYSTKICH wymagań — zarówno funkcjonalnych jak i niefunkcjonalnych.
Podziel wymagania na konkretne, implementowalne elementy. Każde wymaganie musi mieć kryteria akceptacji.

Dla każdego wymagania oceń priorytet:
- "must_have" — wymaganie obowiązkowe z SWZ/OPZ, brak = odrzucenie oferty
- "should_have" — wymaganie sugerowane/pożądane, daje dodatkowe punkty
- "nice_to_have" — wymaganie dodatkowe, może wyróżnić ofertę

Odwołuj się do konkretnych miejsc w dokumentach (np. "OPZ pkt 3.2.1", "SWZ rozdz. VII").

Odpowiedz TYLKO jako JSON (bez markdown, bez ```):
{{
  "scope_summary": "ogólny opis co trzeba zrobić — 3-5 zdań po polsku, zrozumiałe dla nietechnicznej osoby",
  "functional_requirements": [
    {{
      "id": "FR-001",
      "name": "krótka nazwa wymagania",
      "description": "szczegółowy opis co system musi robić",
      "priority": "must_have",
      "acceptance_criteria": ["kryterium akceptacji 1", "kryterium 2"],
      "source_reference": "gdzie w dokumentacji (np. 'OPZ pkt 3.2.1')"
    }}
  ],
  "non_functional_requirements": [
    {{
      "name": "nazwa (np. wydajność, dostępność, bezpieczeństwo, RODO)",
      "description": "szczegółowy opis wymagania",
      "metric": "mierzalna wartość (np. 'czas odpowiedzi < 2s', '99.5% SLA')",
      "source_reference": "odniesienie do dokumentacji"
    }}
  ],
  "deliverables": [
    {{
      "name": "nazwa produktu do dostarczenia",
      "description": "co dokładnie trzeba dostarczyć",
      "format": "forma dostarczenia (np. 'kod źródłowy', 'dokumentacja PDF', 'szkolenie')",
      "deadline": "termin dostarczenia lub null"
    }}
  ],
  "out_of_scope": ["rzeczy które NIE wchodzą w zakres ale mogą być mylące"],
  "assumptions": ["założenia przyjęte przy analizie — rzeczy niejasne w SWZ"],
  "open_questions": ["pytania które TRZEBA zadać zamawiającemu przed złożeniem oferty — konkretne, z odwołaniem do dokumentów"],
  "summary": "podsumowanie zakresu — 2-3 zdania"
}}"""

    return _safe_result(await call_claude(prompt, context_files=attachments, system_prompt=SYSTEM_PROMPT))


async def run_step2(tender: Tender, profile: CompanyProfile, prev_results: dict) -> dict:
    """Step 2: Technical Solution & Open Source — propozycja rozwiązania technicznego."""
    company_json = _build_company_context(profile)
    attachments = _get_attachment_files(tender)

    prompt = f"""Na podstawie wymagań z analizy zakresu zaproponuj rozwiązanie techniczne dla tego zamówienia.

## Profil firmy:
{company_json}

## Treść przetargu:
{tender.tender_text or "(brak tekstu — analizuj na podstawie załączników)"}

## Wymagania (z kroku 1):
{json.dumps(prev_results.get("step1", {{}}), ensure_ascii=False, indent=2)}

KLUCZOWE ZADANIE: Sprawdź czy istniejące rozwiązania open source mogą pokryć wymagania.
Rozważ w szczególności:
- Moodle (e-learning, LMS, szkolenia)
- WordPress (CMS, strony www, portale informacyjne)
- Symfony / Laravel (framework PHP do aplikacji webowych na zamówienie)
- Django / FastAPI (framework Python do aplikacji webowych)
- Drupal (CMS dla instytucji publicznych)
- Nextcloud (zarządzanie dokumentami, współpraca)
- Odoo (ERP, CRM, zarządzanie)
- Redmine / GitLab (zarządzanie projektami)
- Keycloak (SSO, zarządzanie tożsamościami)
- Inne popularne rozwiązania open source pasujące do wymagań

Dla każdego rozpatrywanego rozwiązania podaj:
- Jaki procent wymagań pokrywa "z pudełka"
- Co trzeba dostosować/dopisać
- Czy licencja pozwala na użycie w zamówieniu publicznym

Odpowiedz TYLKO jako JSON (bez markdown, bez ```):
{{
  "recommended_architecture": "opis proponowanej architektury — 3-5 zdań, dlaczego taki wybór",
  "open_source_analysis": [
    {{
      "name": "nazwa rozwiązania (np. Moodle 4.x)",
      "category": "LMS|CMS|Framework|ERP|inne",
      "fits": true,
      "coverage_pct": 75,
      "pros": ["zaleta 1", "zaleta 2"],
      "cons": ["wada 1", "wada 2"],
      "customization_needed": "opis co trzeba dostosować/dopisać",
      "license": "GPL-3.0",
      "license_compatible": true
    }}
  ],
  "proposed_stack": [
    {{
      "layer": "frontend|backend|database|infrastructure|tools|integration",
      "technology": "nazwa technologii",
      "version": "rekomendowana wersja",
      "rationale": "dlaczego ta technologia",
      "license": "typ licencji",
      "cost": "darmowe|kwota"
    }}
  ],
  "integration_points": [
    {{
      "name": "nazwa integracji (np. ePUAP, system zamawiającego, API)",
      "description": "co trzeba zintegrować",
      "technology": "API REST / SOAP / inne",
      "complexity": "low|medium|high"
    }}
  ],
  "hosting_recommendation": "rekomendowany hosting (cloud/on-premise/hybrid) i dlaczego",
  "summary": "podsumowanie rekomendacji — 2-3 zdania"
}}"""

    return _safe_result(await call_claude(prompt, context_files=attachments, system_prompt=SYSTEM_PROMPT))


async def run_step3(tender: Tender, profile: CompanyProfile, prev_results: dict) -> dict:
    """Step 3: Effort & Cost Estimation — wycena i koszty."""
    company_json = _build_company_context(profile)
    attachments = _get_attachment_files(tender)

    prompt = f"""Na podstawie wymagań i proponowanego rozwiązania technicznego przygotuj KOMPLETNĄ estymację kosztów.

## Profil firmy:
{company_json}

## Treść przetargu:
{tender.tender_text or "(brak tekstu — analizuj na podstawie załączników)"}

## Wymagania (krok 1) i rozwiązanie techniczne (krok 2):
{json.dumps(prev_results, ensure_ascii=False, indent=2)}

ZADANIE:
1. Rozbij pracę na pakiety prac odpowiadające wymaganiom funkcjonalnym.
2. Dla każdego pakietu podaj listę konkretnych zadań.
3. Oszacuj roboczogodziny × {profile.hourly_rate_pln} PLN netto (stawka firmy).
4. Dodaj narzut QA/testy: +{profile.qa_buffer_pct}%.
5. Dodaj bufor bezpieczeństwa: +{profile.risk_buffer_pct}%.
6. Wypisz pozycje do wyceny z formularza ofertowego (pricing_items).
7. Wypisz kryteria oceny ofert i JAK KONKRETNIE zdobyć max punktów.
8. Wypisz WSZYSTKIE terminy z dokumentacji (realizacja, SLA, gwarancja, rękojmia).
9. Wypisz wymagany personel i dopasuj kandydatów z zespołu firmy.

Odpowiedz TYLKO jako JSON (bez markdown, bez ```):
{{
  "work_packages": [
    {{
      "name": "nazwa pakietu prac",
      "description": "opis",
      "tasks": ["zadanie 1", "zadanie 2", "zadanie 3"],
      "hours": 40,
      "cost_net_pln": 8000
    }}
  ],
  "pricing_items": [
    {{
      "name": "nazwa pozycji z formularza ofertowego",
      "description": "opis",
      "unit": "szt|godz|msc|ryczalt|komplet",
      "quantity": 1,
      "unit_price_net": 8000,
      "total_net": 8000,
      "notes": "uwagi"
    }}
  ],
  "evaluation_criteria": [
    {{
      "name": "nazwa kryterium",
      "weight_pct": 60,
      "scoring_method": "jak liczone punkty — wzór",
      "how_to_maximize": "konkretne zalecenie jak zdobyć max",
      "our_strategy": "co dokładnie proponujemy w tym kryterium"
    }}
  ],
  "deadlines": [
    {{
      "name": "nazwa terminu",
      "date": "data lub okres",
      "type": "submission|execution|warranty|other",
      "notes": "uwagi"
    }}
  ],
  "required_personnel": [
    {{
      "role": "nazwa roli",
      "min_experience_years": 5,
      "required_certifications": ["certyfikat"],
      "min_count": 1,
      "our_candidate": "imię i nazwisko z profilu firmy lub 'brak w zespole — wymaga uzupełnienia'",
      "notes": "uwagi"
    }}
  ],
  "subtotal_hours": 200,
  "subtotal_net_pln": 40000,
  "qa_buffer_pct": {profile.qa_buffer_pct},
  "qa_buffer_pln": 8000,
  "risk_buffer_pct": {profile.risk_buffer_pct},
  "risk_buffer_pln": 8000,
  "additional_costs": [
    {{
      "name": "nazwa kosztu (serwery, licencje, certyfikaty, dojazdy)",
      "description": "opis",
      "cost_net_pln": 500,
      "recurring": "jednorazowy|miesięczny|roczny"
    }}
  ],
  "total_net_pln": 56000,
  "total_gross_pln": 68880,
  "suggested_offer_price_net": 56000,
  "price_justification": "uzasadnienie proponowanej ceny — 2-3 zdania",
  "summary": "podsumowanie wyceny 2-3 zdania"
}}"""

    return _safe_result(await call_claude(prompt, context_files=attachments, system_prompt=SYSTEM_PROMPT))


async def run_step4(tender: Tender, profile: CompanyProfile, prev_results: dict) -> dict:
    """Step 4: Risk Analysis — analiza ryzyk."""
    company_json = _build_company_context(profile)
    attachments = _get_attachment_files(tender)

    prompt = f"""Przeprowadź DOGŁĘBNĄ analizę ryzyk dla tego przetargu.

## Profil firmy:
{company_json}

## Treść przetargu:
{tender.tender_text or "(brak tekstu — analizuj na podstawie załączników)"}

## Wyniki poprzednich kroków (zakres, technologia, wycena):
{json.dumps(prev_results, ensure_ascii=False, indent=2)}

Zidentyfikuj ryzyka w kategoriach:
1. FORMALNE: odrzucenie oferty, brak dokumentów, błędy formalne
2. TECHNICZNE: zła architektura, brak kompetencji, integracje, wydajność
3. FINANSOWE: zaniżona wycena, kary umowne, ukryte koszty, serwis, licencje
4. PRAWNE: niekorzystne zapisy umowy, odpowiedzialność, RODO, IP, licencje
5. TERMINOWE: nierealne terminy, opóźnienia, zależności od zamawiającego
6. PERSONALNE: brak kadry, rotacja, kompetencje

Dla KAŻDEGO ryzyka oceń:
- prawdopodobieństwo (1-5)
- wpływ (1-5)
- wynik = prawdopodobieństwo × wpływ

Sprawdź też:
- Próg unijny 143 000 EUR netto — zaznacz jeśli może mieć znaczenie
- Zapisy umowy — pułapki (kary, odpowiedzialność, IP, gwarancja bez limitu)
- Czy wycena pokrywa WSZYSTKIE wymagane elementy

Odpowiedz TYLKO jako JSON (bez markdown, bez ```):
{{
  "risks": [
    {{
      "name": "nazwa ryzyka",
      "severity": "high|medium|low",
      "category": "formal|technical|financial|legal|timeline|personnel",
      "probability": 3,
      "impact": 4,
      "risk_score": 12,
      "description": "opis ryzyka — odwołaj się do konkretnych zapisów w dokumentach",
      "mitigation": "zalecane działanie zapobiegawcze — KONKRETNE, nie ogólnikowe",
      "impact_description": "co się stanie jeśli ryzyko się zmaterializuje",
      "owner": "kto powinien zarządzać (PM, prawnik, technik, finanse)"
    }}
  ],
  "critical_warnings": ["rzeczy które mogą NATYCHMIAST spowodować odrzucenie oferty"],
  "contract_red_flags": ["niebezpieczne zapisy w projekcie umowy — cytat + dlaczego groźne"],
  "go_no_go_recommendation": "GO|GO z zastrzeżeniami|NO-GO",
  "recommendation_rationale": "uzasadnienie rekomendacji — 2-3 zdania",
  "summary": "podsumowanie ryzyk — 2-3 zdania"
}}"""

    return _safe_result(await call_claude(prompt, context_files=attachments, system_prompt=SYSTEM_PROMPT))


async def run_step5(tender: Tender, profile: CompanyProfile, prev_results: dict) -> dict:
    """Step 5: Document Preparation Guide — dokumenty ofertowe z gotowym tekstem."""
    company_json = _build_company_context(profile)
    attachments = _get_attachment_files(tender)

    prompt = f"""Na podstawie WSZYSTKICH wyników analizy przygotuj KOMPLETNY przewodnik po dokumentach ofertowych.

## Profil firmy:
{company_json}

## Treść przetargu:
{tender.tender_text or "(brak tekstu — analizuj na podstawie załączników)"}

## Wyniki wszystkich kroków analizy:
{json.dumps(prev_results, ensure_ascii=False, indent=2)}

ZADANIE:
1. Wymień WSZYSTKIE dokumenty wymagane w ofercie (formularze, oświadczenia, wykazy, referencje, pełnomocnictwa).
2. Dla KAŻDEGO dokumentu podaj:
   - Dokładną instrukcję krok po kroku co i jak wypełnić
   - GOTOWY TEKST do skopiowania i wklejenia — używaj PRAWDZIWYCH danych z profilu firmy!
   - Ostrzeżenia co może spowodować odrzucenie
3. Uwzględnij dane firmy: nazwa, NIP, adres, osoba kontaktowa, numer konta bankowego.
4. Uwzględnij dane z wyceny: ceny, stawki, godziny z kroku 3.
5. Uwzględnij dane personelu: imiona, nazwiska, doświadczenie z profilu firmy.
6. Uwzględnij wadium jeśli wymagane.
7. Przygotuj checklistę — co sprawdzić przed złożeniem oferty.

WAŻNE: Tekst sugerowany musi być GOTOWY DO UŻYCIA — NIE pisz "[wstaw tu...]",
tylko użyj prawdziwych danych z profilu firmy. Użytkownik skopiuje tekst i wklei do DOCX.

Odpowiedz TYLKO jako JSON (bez markdown, bez ```):
{{
  "document_guides": [
    {{
      "document_name": "nazwa dokumentu / formularza",
      "document_type": "formularz|oswiadczenie|wykaz|referencja|oferta|pelnomocnictwo|inne",
      "is_required": true,
      "requires_signature": true,
      "instruction": "szczegółowa instrukcja krok po kroku — numerowana lista",
      "suggested_text": "GOTOWY tekst do skopiowania — z wypełnionymi danymi firmy, cenami z wyceny, personelem",
      "warnings": "na co uważać, co może spowodować odrzucenie",
      "deadline": "termin złożenia lub null"
    }}
  ],
  "wadium": {{
    "required": true,
    "amount": "kwota",
    "forms": ["przelew", "gwarancja bankowa"],
    "deadline": "termin wniesienia",
    "bank_account": "konto zamawiającego",
    "our_action": "co dokładnie musimy zrobić żeby wnieść wadium",
    "notes": "dodatkowe warunki"
  }},
  "submission_checklist": [
    "Formularz ofertowy wypełniony i podpisany kwalifikowanym podpisem elektronicznym",
    "Oświadczenie o niepodleganiu wykluczeniu podpisane",
    "Wykaz usług z referencjami",
    "element N do sprawdzenia"
  ],
  "general_notes": "ogólne uwagi dotyczące składania oferty"
}}"""

    return _safe_result(await call_claude(prompt, context_files=attachments, system_prompt=SYSTEM_PROMPT))


async def run_step6(
    tender: Tender,
    profile: CompanyProfile,
    prev_results: dict,
    uploaded_files: list[dict],
) -> dict:
    """Step 6: Document Verification — weryfikacja przygotowanych dokumentów."""
    company_json = _build_company_context(profile)
    attachments = _get_attachment_files(tender)

    files_text = ""
    for f in uploaded_files:
        files_text += f"\n\n--- DOKUMENT UŻYTKOWNIKA: {f['filename']} ---\n{f['content']}\n"

    prompt = f"""Zweryfikuj dokumenty ofertowe przygotowane przez firmę pod kątem zgodności z wymaganiami przetargu.

## Profil firmy:
{company_json}

## Treść przetargu (SWZ/OPZ):
{tender.tender_text or "(brak tekstu — analizuj na podstawie załączników)"}

## Wyniki analizy (wymagane dokumenty, wycena, personel):
{json.dumps(prev_results, ensure_ascii=False, indent=2)}

## Dokumenty przesłane przez firmę do weryfikacji:
{files_text}

ZADANIE — bądź KRYTYCZNY i DOKŁADNY. Każdy błąd formalny = ryzyko odrzucenia oferty.
Lepiej zgłosić za dużo uwag niż za mało.

Dla KAŻDEGO przesłanego dokumentu sprawdź:
1. Czy zawiera WSZYSTKIE wymagane elementy wg SWZ
2. Czy dane firmy (nazwa, NIP, adres) są poprawne i spójne między dokumentami
3. Czy kwoty/ceny są spójne między formularzem ofertowym a wyceną
4. Czy brakuje podpisów, dat, pieczęci (zaznacz gdzie)
5. Czy tekst nie zawiera błędów merytorycznych lub literówek w kluczowych miejscach
6. Czy oferta jest zgodna z projektem umowy
7. Czy nie brakuje żadnego wymaganego dokumentu w zestawie

Odpowiedz TYLKO jako JSON (bez markdown, bez ```):
{{
  "overall_status": "ok|issues_found",
  "documents_checked": [
    {{
      "filename": "nazwa pliku",
      "document_type": "rozpoznany typ dokumentu",
      "status": "ok|warning|error",
      "issues": [
        {{
          "severity": "error|warning|info",
          "description": "opis problemu — KONKRETNY, z cytatem z dokumentu jeśli możliwe",
          "location": "gdzie w dokumencie (nr strony, sekcja, wiersz)",
          "fix_suggestion": "co dokładnie zmienić — gotowa treść do wklejenia jeśli możliwe",
          "risk": "co się stanie jeśli nie naprawione (np. 'odrzucenie oferty')"
        }}
      ],
      "completeness_pct": 90,
      "missing_elements": ["brakujący element 1", "brakujący element 2"]
    }}
  ],
  "missing_documents": ["dokumenty wymagane w SWZ ale NIE przesłane do weryfikacji"],
  "cross_document_issues": [
    {{
      "description": "niespójność między dokumentami (np. różne kwoty, daty, dane)",
      "documents_involved": ["dokument 1", "dokument 2"],
      "fix_suggestion": "jak naprawić"
    }}
  ],
  "summary": "podsumowanie weryfikacji — czy oferta jest gotowa do złożenia, 2-3 zdania"
}}"""

    return _safe_result(await call_claude(prompt, context_files=attachments, system_prompt=SYSTEM_PROMPT))


# --- Background task runner ---

async def _run_analysis_step(analysis_id: int, step: int) -> None:
    """Run a single analysis step in background, updating DB and emitting SSE events."""
    logger.info(f"[Analysis {analysis_id}] _run_analysis_step START: krok {step}")
    async with async_session() as db:
        analysis = await db.get(Analysis, analysis_id)
        if not analysis:
            logger.error(f"[Analysis {analysis_id}] Nie znaleziono analizy w DB!")
            return

        tender = await db.get(Tender, analysis.tender_id)
        if not tender:
            logger.error(f"[Analysis {analysis_id}] Nie znaleziono przetargu tender_id={analysis.tender_id}!")
            return

        result = await db.execute(
            select(CompanyProfile).options(
                selectinload(CompanyProfile.team_members),
                selectinload(CompanyProfile.portfolio_projects),
            ).where(CompanyProfile.user_id == 1)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            # Auto-create empty profile so analysis can proceed
            profile = CompanyProfile(user_id=1)
            db.add(profile)
            await db.commit()
            await db.refresh(profile, ["team_members", "portfolio_projects"])
            logger.info(f"[Analysis {analysis_id}] Auto-utworzono pusty profil firmy")

        # Step descriptions for progress reporting
        _STEP_DESCRIPTIONS = {
            0: {
                "label": "Warunki udziału",
                "phases": [
                    "Czytam dokumenty przetargowe...",
                    "Sprawdzam wymagania formalne (koncesje, uprawnienia)...",
                    "Weryfikuję doświadczenie firmy vs wymagania...",
                    "Analizuję warunki kadrowe i finansowe...",
                    "Oceniam spełnienie warunków...",
                ],
            },
            1: {
                "label": "Zakres i wymagania",
                "phases": [
                    "Analizuję SWZ i OPZ...",
                    "Wyodrębniam wymagania funkcjonalne...",
                    "Identyfikuję wymagania niefunkcjonalne...",
                    "Klasyfikuję priorytety wymagań...",
                ],
            },
            2: {
                "label": "Rozwiązanie techniczne",
                "phases": [
                    "Szukam pasujących rozwiązań open source...",
                    "Projektuję architekturę techniczną...",
                    "Oceniam pokrycie wymagań przez technologie...",
                ],
            },
            3: {
                "label": "Wycena i koszty",
                "phases": [
                    "Szacuję pracochłonność...",
                    "Kalkuluję koszty zespołu i infrastruktury...",
                    "Przygotowuję kosztorys...",
                ],
            },
            4: {
                "label": "Analiza ryzyk",
                "phases": [
                    "Identyfikuję ryzyka techniczne i formalne...",
                    "Oceniam prawdopodobieństwo i wpływ...",
                    "Przygotowuję rekomendację GO/NO-GO...",
                ],
            },
            5: {
                "label": "Dokumenty ofertowe",
                "phases": [
                    "Generuję szablony dokumentów...",
                    "Przygotowuję instrukcje wypełniania...",
                    "Tworzę teksty do formularzy...",
                ],
            },
        }

        step_info = _STEP_DESCRIPTIONS.get(step, {"label": f"Krok {step}", "phases": ["Przetwarzam..."]})
        att_files = _get_attachment_files(tender)
        att_count = len(att_files)

        await _emit(analysis_id, "step_started", {"step": step})
        await _emit(analysis_id, "progress", {
            "step": step,
            "label": step_info["label"],
            "phase": step_info["phases"][0],
            "percent": 0,
            "attachment_count": att_count,
        })
        logger.info(f"[Analysis {analysis_id}] Rozpoczynam krok {step}, tender_id={analysis.tender_id}, załączników={att_count}")

        # Helper to emit progress phases during step execution
        async def _emit_phase(phase_idx: int) -> None:
            phases = step_info["phases"]
            idx = min(phase_idx, len(phases) - 1)
            pct = int((phase_idx / max(len(phases), 1)) * 80)  # 0-80%, last 20% = saving
            await _emit(analysis_id, "progress", {
                "step": step,
                "label": step_info["label"],
                "phase": phases[idx],
                "percent": pct,
                "attachment_count": att_count,
            })

        try:
            if step == 0:
                fix_context = None
                if analysis.step0_fix_actions:
                    fix_context = json.dumps(analysis.step0_fix_actions, ensure_ascii=False)
                await _emit_phase(1)
                step_result = await run_step0(tender, profile, fix_context)
                await _emit_phase(4)
                logger.info(f"[Analysis {analysis_id}] Krok 0 wynik: eligible={step_result.get('eligible')}")
                analysis.step0_result = step_result
                eligible = step_result.get("eligible", False) if isinstance(step_result, dict) else False
                analysis.step0_eligible = eligible
                analysis.status = "waiting_user"

            elif step == 1:
                await _emit_phase(1)
                step_result = await run_step1(tender, profile)
                await _emit_phase(3)
                logger.info(f"[Analysis {analysis_id}] Krok 1 zakończony")
                analysis.step1_result = step_result

            elif step == 2:
                prev = {"step1": analysis.step1_result}
                await _emit_phase(1)
                step_result = await run_step2(tender, profile, prev)
                await _emit_phase(2)
                logger.info(f"[Analysis {analysis_id}] Krok 2 zakończony")
                analysis.step2_result = step_result

            elif step == 3:
                prev = {"step1": analysis.step1_result, "step2": analysis.step2_result}
                await _emit_phase(1)
                step_result = await run_step3(tender, profile, prev)
                await _emit_phase(2)
                logger.info(f"[Analysis {analysis_id}] Krok 3 zakończony")
                analysis.step3_result = step_result

            elif step == 4:
                prev = {
                    "step1": analysis.step1_result,
                    "step2": analysis.step2_result,
                    "step3": analysis.step3_result,
                }
                await _emit_phase(1)
                step_result = await run_step4(tender, profile, prev)
                await _emit_phase(2)
                logger.info(f"[Analysis {analysis_id}] Krok 4 zakończony")
                analysis.step4_result = step_result

            elif step == 5:
                prev = {
                    "step1": analysis.step1_result,
                    "step2": analysis.step2_result,
                    "step3": analysis.step3_result,
                    "step4": analysis.step4_result,
                }
                await _emit_phase(1)
                step_result = await run_step5(tender, profile, prev)
                await _emit_phase(2)
                logger.info(f"[Analysis {analysis_id}] Krok 5 zakończony")
                analysis.step5_result = step_result

                # Save document guides to DB
                guides = step_result.get("document_guides", []) if isinstance(step_result, dict) else []
                for i, guide in enumerate(guides):
                    doc = AnalysisDocument(
                        analysis_id=analysis.id,
                        document_name=guide.get("document_name", f"Dokument {i+1}"),
                        instruction=guide.get("instruction", ""),
                        suggested_text=guide.get("suggested_text", ""),
                        order_index=i,
                    )
                    db.add(doc)

                analysis.status = "completed"
                tender.status = "completed"

            # For steps 1-4, don't set waiting_user — they auto-continue
            analysis.current_step = step
            await db.commit()
            logger.info(f"[Analysis {analysis_id}] Krok {step} zapisany, status={analysis.status}")
            await _emit(analysis_id, "progress", {
                "step": step,
                "label": step_info["label"],
                "phase": "Gotowe!",
                "percent": 100,
                "attachment_count": att_count,
            })
            await _emit(analysis_id, "step_completed", {"step": step, "status": analysis.status})

        except Exception as e:
            logger.exception(f"[Analysis {analysis_id}] Krok {step} BŁĄD: {e}")
            analysis.status = "failed"
            analysis.error_message = str(e)[:1000]
            await db.commit()
            await _emit(analysis_id, "error", {"step": step, "message": str(e)[:500]})


# Keep strong references to background tasks so they don't get GC'd
_background_tasks: set[asyncio.Task] = set()
# Track tasks by analysis_id for cancellation
_analysis_tasks: dict[int, asyncio.Task] = {}


async def cancel_analysis(analysis_id: int) -> None:
    """Cancel a running analysis task and set status back to waiting_user."""
    task = _analysis_tasks.get(analysis_id)
    if task and not task.done():
        task.cancel()
        logger.info(f"[Analysis {analysis_id}] Task anulowany przez użytkownika")

    # Set status back to waiting_user regardless
    async with async_session() as db:
        analysis = await db.get(Analysis, analysis_id)
        if analysis and analysis.status == "running":
            analysis.status = "waiting_user"
            await db.commit()
            logger.info(f"[Analysis {analysis_id}] Status zmieniony na waiting_user")


async def launch_step(analysis_id: int, step: int) -> None:
    """Launch an analysis step as a background asyncio task."""
    from app.services.concurrency import acquire, release

    logger.info(f"[Analysis {analysis_id}] Uruchamiam task dla kroku {step}")

    async def _wrapped():
        await acquire()
        try:
            await _run_analysis_step(analysis_id, step)
        except asyncio.CancelledError:
            logger.info(f"[Analysis {analysis_id}] Task kroku {step} został anulowany")
        except Exception:
            logger.exception(f"[Analysis {analysis_id}] Nieobsłużony wyjątek w task kroku {step}")
        finally:
            release()
            _analysis_tasks.pop(analysis_id, None)

    # Cancel any existing task for this analysis
    old_task = _analysis_tasks.get(analysis_id)
    if old_task and not old_task.done():
        old_task.cancel()

    task = asyncio.create_task(_wrapped())
    _background_tasks.add(task)
    _analysis_tasks[analysis_id] = task
    task.add_done_callback(_background_tasks.discard)


async def launch_remaining_steps(analysis_id: int, from_step: int) -> None:
    """Run steps sequentially from from_step through 5. Step 6 is user-triggered separately."""
    from app.services.concurrency import acquire, release

    async def _run_sequential():
        await acquire()
        try:
            for step in range(from_step, 6):
                async with async_session() as db:
                    analysis = await db.get(Analysis, analysis_id)
                    if not analysis or analysis.status == "failed":
                        return
                    analysis.status = "running"
                    analysis.current_step = step
                    await db.commit()

                await _run_analysis_step(analysis_id, step)

                async with async_session() as db:
                    analysis = await db.get(Analysis, analysis_id)
                    if not analysis or analysis.status in ("failed", "waiting_user"):
                        return
        except Exception:
            logger.exception(f"[Analysis {analysis_id}] Nieobsłużony wyjątek w launch_remaining_steps")
        finally:
            release()

    task = asyncio.create_task(_run_sequential())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def run_verification(analysis_id: int, uploaded_files: list[dict]) -> None:
    """Run step 6 verification on uploaded documents (separate from main pipeline)."""
    logger.info(f"[Analysis {analysis_id}] Uruchamiam weryfikację dokumentów ({len(uploaded_files)} plików)")

    async def _run():
        try:
            async with async_session() as db:
                analysis = await db.get(Analysis, analysis_id)
                if not analysis:
                    return

                tender = await db.get(Tender, analysis.tender_id)
                if not tender:
                    return

                result_q = await db.execute(
                    select(CompanyProfile).options(
                        selectinload(CompanyProfile.team_members),
                        selectinload(CompanyProfile.portfolio_projects),
                    ).where(CompanyProfile.user_id == 1)
                )
                profile = result_q.scalar_one_or_none()
                if not profile:
                    analysis.status = "failed"
                    analysis.error_message = "Brak profilu firmy."
                    await db.commit()
                    await _emit(analysis_id, "error", {"message": analysis.error_message})
                    return

                await _emit(analysis_id, "step_started", {"step": 6})

                prev = {
                    "step1": analysis.step1_result,
                    "step3": analysis.step3_result,
                    "step5": analysis.step5_result,
                }

                step_result = await run_step6(tender, profile, prev, uploaded_files)
                analysis.step6_result = step_result
                analysis.current_step = 6
                analysis.status = "completed"
                await db.commit()

                logger.info(f"[Analysis {analysis_id}] Weryfikacja zakończona: {step_result.get('overall_status')}")
                await _emit(analysis_id, "step_completed", {"step": 6, "status": "completed"})

        except Exception as e:
            logger.exception(f"[Analysis {analysis_id}] Błąd weryfikacji: {e}")
            async with async_session() as db:
                analysis = await db.get(Analysis, analysis_id)
                if analysis:
                    analysis.status = "completed"  # Don't block — verification is optional
                    analysis.error_message = f"Weryfikacja nieudana: {str(e)[:500]}"
                    await db.commit()
            await _emit(analysis_id, "error", {"step": 6, "message": str(e)[:500]})

    task = asyncio.create_task(_run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
