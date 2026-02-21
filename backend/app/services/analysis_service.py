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
        },
        ensure_ascii=False,
        indent=2,
    )


def _get_attachment_files(tender: Tender) -> list[Path]:
    """Get all attachment file paths for a tender."""
    if not tender.data_dir:
        return []
    att_dir = Path(tender.data_dir) / "attachments"
    if not att_dir.exists():
        return []
    return [f for f in att_dir.iterdir() if f.is_file()]


SYSTEM_PROMPT = (
    "Jesteś krytycznym asystentem do analizy przetargów publicznych w Polsce. "
    "Pracujesz sceptycznie: nie przytakujesz, tylko weryfikujesz wymagania i wyłapujesz ryzyka formalne. "
    "Nigdy się nie domyślaj — jeśli czegoś nie wiesz lub brakuje informacji, zaznacz to wyraźnie. "
    "Jeśli firma jest software house'em (JDG, tworzenie oprogramowania na zamówienie) a zamówienie dotyczy "
    "dostawy licencji gotowego oprogramowania lub wymaga statusu autoryzowanego partnera producenta — "
    "traktuj to jako niespełnienie warunku. "
    "Odpowiadaj po polsku. Zwracaj WYŁĄCZNIE valid JSON bez dodatkowego tekstu."
)


# --- Step implementations ---

async def run_step0(
    tender: Tender,
    profile: CompanyProfile,
    fix_context: str | None = None,
) -> dict:
    """Step 0: Eligibility check."""
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

Odpowiedz TYLKO jako JSON (bez markdown, bez ```):
{
  "eligible": true lub false,
  "conditions": [
    {
      "name": "nazwa warunku po polsku",
      "description": "co jest wymagane wg dokumentacji",
      "met": true lub false,
      "reason": "dlaczego spełniony/niespełniony — odwołaj się do dokumentów",
      "fixable": true lub false,
      "fix_options": ["opcja naprawcza 1", "opcja 2"]
    }
  ],
  "summary": "krótkie podsumowanie oceny (2-3 zdania po polsku)",
  "scope_description": "co trzeba zrealizować w ramach zamówienia (2-3 zdania po polsku)",
  "estimated_budget": "budżet z dokumentacji lub szacunek lub 'nieokreślony'"
}"""

    result = await call_claude(prompt, context_files=attachments, system_prompt=SYSTEM_PROMPT)
    if isinstance(result, dict):
        return result
    # Try to extract JSON from string response
    from app.services.claude_service import _extract_json
    extracted = _extract_json(result) if isinstance(result, str) else None
    return extracted if isinstance(extracted, dict) else {"raw": result}


async def run_step1(tender: Tender, profile: CompanyProfile) -> dict:
    """Step 1: Required documents list."""
    company_json = _build_company_context(profile)
    attachments = _get_attachment_files(tender)

    prompt = f"""Na podstawie dokumentacji przetargowej wymień WSZYSTKIE wymagane dokumenty, formularze, oświadczenia i załączniki do oferty.

## Profil firmy:
{company_json}

## Treść przetargu:
{tender.tender_text or "(brak tekstu — analizuj na podstawie załączników)"}

Wypisz KOMPLETNĄ listę. Dla każdego dokumentu podaj: nazwę, czy wymaga wypełnienia/podpisu, termin złożenia, szczególne wymagania.

Odpowiedz TYLKO jako JSON (bez markdown):
{{
  "documents": [
    {{
      "name": "nazwa dokumentu",
      "type": "formularz" | "oswiadczenie" | "wykaz" | "referencja" | "polisa" | "pelnomonictwo" | "inne",
      "description": "co musi zawierać",
      "requires_signature": true/false,
      "requires_stamp": true/false,
      "deadline": "termin lub null",
      "notes": "dodatkowe uwagi"
    }}
  ],
  "wadium": {{
    "required": true/false,
    "amount": "kwota lub null",
    "forms": ["forma wniesienia"],
    "deadline": "termin",
    "bank_account": "konto jeśli podane",
    "notes": "dodatkowe warunki"
  }},
  "summary": "podsumowanie 1-2 zdania"
}}"""

    result = await call_claude(prompt, context_files=attachments, system_prompt=SYSTEM_PROMPT)
    if isinstance(result, dict):
        return result
    # Try to extract JSON from string response
    from app.services.claude_service import _extract_json
    extracted = _extract_json(result) if isinstance(result, str) else None
    return extracted if isinstance(extracted, dict) else {"raw": result}


async def run_step2(tender: Tender, profile: CompanyProfile) -> dict:
    """Step 2: Pricing items, criteria, deadlines, personnel."""
    company_json = _build_company_context(profile)
    attachments = _get_attachment_files(tender)

    prompt = f"""Na podstawie dokumentacji przetargowej wypisz WSZYSTKIE informacje potrzebne do przygotowania oferty.

## Profil firmy:
{company_json}

## Treść przetargu:
{tender.tender_text or "(brak tekstu — analizuj na podstawie załączników)"}

Odpowiedz TYLKO jako JSON (bez markdown):
{{
  "pricing_items": [
    {{
      "name": "nazwa pozycji do wyceny",
      "description": "opis",
      "unit": "jednostka (szt/godz/msc/ryczalt)",
      "quantity": "ilość lub null",
      "notes": "uwagi"
    }}
  ],
  "evaluation_criteria": [
    {{
      "name": "nazwa kryterium",
      "weight_pct": 60,
      "scoring_method": "jak liczone punkty",
      "how_to_maximize": "jak zdobyć max punktów"
    }}
  ],
  "deadlines": [
    {{
      "name": "nazwa terminu",
      "date": "data lub okres",
      "notes": "uwagi"
    }}
  ],
  "required_personnel": [
    {{
      "role": "nazwa roli",
      "min_experience_years": 5,
      "required_certifications": ["certyfikat"],
      "min_count": 1,
      "notes": "uwagi"
    }}
  ],
  "sla_requirements": [
    {{
      "name": "wymaganie SLA",
      "value": "wartość",
      "penalty": "kara za niedotrzymanie"
    }}
  ],
  "summary": "podsumowanie 2-3 zdania"
}}"""

    result = await call_claude(prompt, context_files=attachments, system_prompt=SYSTEM_PROMPT)
    if isinstance(result, dict):
        return result
    # Try to extract JSON from string response
    from app.services.claude_service import _extract_json
    extracted = _extract_json(result) if isinstance(result, str) else None
    return extracted if isinstance(extracted, dict) else {"raw": result}


async def run_step3(tender: Tender, profile: CompanyProfile, prev_results: dict) -> dict:
    """Step 3: Risk analysis."""
    company_json = _build_company_context(profile)
    attachments = _get_attachment_files(tender)

    prompt = f"""Przeprowadź analizę ryzyk dla tego przetargu. Uwzględnij wyniki poprzednich kroków analizy.

## Profil firmy:
{company_json}

## Treść przetargu:
{tender.tender_text or "(brak tekstu — analizuj na podstawie załączników)"}

## Wyniki poprzednich kroków:
{json.dumps(prev_results, ensure_ascii=False, indent=2)}

Zidentyfikuj ryzyka:
- odrzucenia oferty (formalnie/technicznie)
- utraty punktów (kryteria, parametry, terminy, doświadczenie)
- błędnej interpretacji SWZ/OPZ/umowy
- błędnej wyceny (pominięte elementy, serwis, licencje, koszty infrastruktury)
- niezgodności oferty z projektem umowy
- braku wymaganych dokumentów
- progu unijnego: 143 000 EUR netto (zaznacz jeśli może mieć znaczenie)

Odpowiedz TYLKO jako JSON (bez markdown):
{{
  "risks": [
    {{
      "name": "nazwa ryzyka",
      "severity": "high" | "medium" | "low",
      "category": "formal" | "technical" | "financial" | "legal" | "timeline",
      "description": "opis ryzyka — odwołaj się do konkretnych zapisów w dokumentach",
      "mitigation": "zalecane działanie zapobiegawcze",
      "impact": "co się stanie jeśli ryzyko się zmaterializuje"
    }}
  ],
  "critical_warnings": ["lista rzeczy które mogą natychmiast spowodować odrzucenie oferty"],
  "summary": "podsumowanie 2-3 zdania"
}}"""

    result = await call_claude(prompt, context_files=attachments, system_prompt=SYSTEM_PROMPT)
    if isinstance(result, dict):
        return result
    # Try to extract JSON from string response
    from app.services.claude_service import _extract_json
    extracted = _extract_json(result) if isinstance(result, str) else None
    return extracted if isinstance(extracted, dict) else {"raw": result}


async def run_step4(tender: Tender, profile: CompanyProfile, prev_results: dict) -> dict:
    """Step 4: Cost estimation."""
    company_json = _build_company_context(profile)
    attachments = _get_attachment_files(tender)

    prompt = f"""Przygotuj estymację kosztów realizacji tego zamówienia.

## Profil firmy:
{company_json}

## Treść przetargu:
{tender.tender_text or "(brak tekstu — analizuj na podstawie załączników)"}

## Wyniki poprzednich kroków (pozycje do wyceny, kryteria, personel):
{json.dumps(prev_results, ensure_ascii=False, indent=2)}

Zasady wyceny:
1. Zaproponuj realistyczny stack technologiczny (preferuj open source).
2. Oszacuj roboczogodziny × {profile.hourly_rate_pln} PLN netto (stawka firmy).
3. Dodaj narzut QA/testy: +{profile.qa_buffer_pct}%.
4. Dodaj bufor bezpieczeństwa: +{profile.risk_buffer_pct}%.
5. Wypisz koszty dodatkowe: serwery, certyfikaty, licencje, utrzymanie.

Odpowiedz TYLKO jako JSON (bez markdown):
{{
  "proposed_stack": ["technologia 1", "technologia 2"],
  "work_packages": [
    {{
      "name": "nazwa pakietu prac",
      "description": "opis",
      "hours": 40,
      "cost_net_pln": 8000
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
      "name": "nazwa kosztu",
      "description": "opis",
      "cost_net_pln": 500,
      "recurring": "jednorazowy" | "miesięczny" | "roczny"
    }}
  ],
  "total_net_pln": 56000,
  "total_gross_pln": 68880,
  "summary": "podsumowanie wyceny 2-3 zdania"
}}"""

    result = await call_claude(prompt, context_files=attachments, system_prompt=SYSTEM_PROMPT)
    if isinstance(result, dict):
        return result
    # Try to extract JSON from string response
    from app.services.claude_service import _extract_json
    extracted = _extract_json(result) if isinstance(result, str) else None
    return extracted if isinstance(extracted, dict) else {"raw": result}


async def run_step5(tender: Tender, profile: CompanyProfile, prev_results: dict) -> list[dict]:
    """Step 5: Document guidance — what to write in each document."""
    company_json = _build_company_context(profile)
    attachments = _get_attachment_files(tender)

    prompt = f"""Na podstawie wyników analizy przygotuj szczegółowe wytyczne do wypełnienia każdego wymaganego dokumentu ofertowego.

## Profil firmy:
{company_json}

## Treść przetargu:
{tender.tender_text or "(brak tekstu — analizuj na podstawie załączników)"}

## Wyniki analizy (wymagane dokumenty, wycena, kryteria):
{json.dumps(prev_results, ensure_ascii=False, indent=2)}

Dla KAŻDEGO wymaganego dokumentu podaj:
- dokładną instrukcję co i jak wypełnić
- gotowy tekst do skopiowania (tam gdzie to możliwe)
- dane firmy do wstawienia

Odpowiedz TYLKO jako JSON (bez markdown):
{{
  "document_guides": [
    {{
      "document_name": "nazwa dokumentu / formularza",
      "instruction": "szczegółowa instrukcja co wypełnić, krok po kroku",
      "suggested_text": "gotowy tekst do skopiowania i wklejenia (używaj danych firmy z profilu)",
      "warnings": "na co uważać, co może spowodować odrzucenie"
    }}
  ],
  "general_notes": "ogólne uwagi dotyczące składania oferty"
}}"""

    result = await call_claude(prompt, context_files=attachments, system_prompt=SYSTEM_PROMPT)
    if isinstance(result, dict) and "document_guides" in result:
        return result["document_guides"]
    return [{"document_name": "Wynik analizy", "instruction": "", "suggested_text": json.dumps(result, ensure_ascii=False, indent=2), "warnings": ""}]


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
            analysis.status = "failed"
            analysis.error_message = "Brak profilu firmy — uzupełnij dane w zakładce Profil firmy."
            await db.commit()
            await _emit(analysis_id, "error", {"message": analysis.error_message})
            return

        await _emit(analysis_id, "step_started", {"step": step})
        logger.info(f"[Analysis {analysis_id}] Rozpoczynam krok {step}, tender_id={analysis.tender_id}")

        try:
            if step == 0:
                fix_context = None
                if analysis.step0_fix_actions:
                    fix_context = json.dumps(analysis.step0_fix_actions, ensure_ascii=False)
                step_result = await run_step0(tender, profile, fix_context)
                logger.info(f"[Analysis {analysis_id}] Krok 0 wynik: typ={type(step_result).__name__}, "
                            f"klucze={list(step_result.keys()) if isinstance(step_result, dict) else 'N/A'}")
                analysis.step0_result = step_result
                eligible = step_result.get("eligible", False) if isinstance(step_result, dict) else False
                analysis.step0_eligible = eligible
                analysis.status = "waiting_user"
                logger.info(f"[Analysis {analysis_id}] Krok 0 zakończony: eligible={eligible}, status=waiting_user")

            elif step == 1:
                step_result = await run_step1(tender, profile)
                logger.info(f"[Analysis {analysis_id}] Krok 1 zakończony, klucze={list(step_result.keys()) if isinstance(step_result, dict) else 'N/A'}")
                analysis.step1_result = step_result
                analysis.status = "waiting_user"

            elif step == 2:
                step_result = await run_step2(tender, profile)
                logger.info(f"[Analysis {analysis_id}] Krok 2 zakończony, klucze={list(step_result.keys()) if isinstance(step_result, dict) else 'N/A'}")
                analysis.step2_result = step_result
                analysis.status = "waiting_user"

            elif step == 3:
                prev = {"step1": analysis.step1_result, "step2": analysis.step2_result}
                step_result = await run_step3(tender, profile, prev)
                logger.info(f"[Analysis {analysis_id}] Krok 3 zakończony, klucze={list(step_result.keys()) if isinstance(step_result, dict) else 'N/A'}")
                analysis.step3_result = step_result
                analysis.status = "waiting_user"

            elif step == 4:
                prev = {"step2": analysis.step2_result, "step3": analysis.step3_result}
                step_result = await run_step4(tender, profile, prev)
                logger.info(f"[Analysis {analysis_id}] Krok 4 zakończony, klucze={list(step_result.keys()) if isinstance(step_result, dict) else 'N/A'}")
                analysis.step4_result = step_result
                analysis.status = "waiting_user"

            elif step == 5:
                prev = {
                    "step1": analysis.step1_result,
                    "step2": analysis.step2_result,
                    "step4": analysis.step4_result,
                }
                doc_guides = await run_step5(tender, profile, prev)
                analysis.step5_result = {"document_guides": doc_guides}

                # Save documents to DB
                for i, guide in enumerate(doc_guides):
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

            analysis.current_step = step
            await db.commit()
            logger.info(f"[Analysis {analysis_id}] Krok {step} zapisany do DB, status={analysis.status}")
            await _emit(analysis_id, "step_completed", {"step": step, "status": analysis.status})

        except Exception as e:
            logger.exception(f"[Analysis {analysis_id}] Krok {step} BŁĄD: {e}")
            analysis.status = "failed"
            analysis.error_message = str(e)[:1000]
            await db.commit()
            await _emit(analysis_id, "error", {"step": step, "message": str(e)[:500]})


# Keep strong references to background tasks so they don't get GC'd
_background_tasks: set[asyncio.Task] = set()


async def launch_step(analysis_id: int, step: int) -> None:
    """Launch an analysis step as a background asyncio task."""
    logger.info(f"[Analysis {analysis_id}] Uruchamiam task dla kroku {step}")

    async def _wrapped():
        try:
            await _run_analysis_step(analysis_id, step)
        except Exception:
            logger.exception(f"[Analysis {analysis_id}] Nieobsłużony wyjątek w task kroku {step}")

    task = asyncio.create_task(_wrapped())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def launch_remaining_steps(analysis_id: int, from_step: int) -> None:
    """Run steps sequentially from from_step through 5."""

    async def _run_sequential():
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

    task = asyncio.create_task(_run_sequential())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
