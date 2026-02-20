"""Orchestrates multi-step tender analysis workflow using Claude CLI."""

import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import Analysis
from app.models.company_profile import CompanyProfile
from app.models.tender import Tender
from app.services.claude_service import call_claude


def _build_company_context(profile: CompanyProfile) -> str:
    """Serialize company profile for Claude prompt."""
    return json.dumps(
        {
            "company_name": profile.company_name,
            "nip": profile.nip,
            "address": f"{profile.address_street}, {profile.address_postal_code} {profile.address_city}",
            "description": profile.description,
            "technologies": profile.technologies,
            "certifications": profile.certifications,
            "team": [
                {
                    "name": m.full_name,
                    "role": m.role,
                    "experience_years": m.experience_years,
                    "qualifications": m.qualifications,
                }
                for m in profile.team_members
            ],
            "portfolio": [
                {
                    "project": p.project_name,
                    "client": p.client_name,
                    "value_pln": p.contract_value_pln,
                    "year": p.year_completed,
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
    return list(att_dir.iterdir())


async def run_step0(
    analysis: Analysis,
    tender: Tender,
    profile: CompanyProfile,
    fix_context: str | None = None,
) -> dict:
    """Run eligibility check (Step 0)."""
    company_json = _build_company_context(profile)
    attachments = _get_attachment_files(tender)

    prompt = f"""Analizujesz polski przetarg pod kątem spełniania warunków udziału.

## Profil firmy:
{company_json}

## Treść przetargu:
{tender.tender_text or "(brak tekstu)"}
"""
    if fix_context:
        prompt += f"\n## Podjęte działania naprawcze:\n{fix_context}\n"

    prompt += """
Sprawdź czy firma spełnia WSZYSTKIE warunki udziału w postępowaniu.
Sprawdź: uprawnienia, sytuację finansową, zdolność techniczną, kadrę, certyfikaty,
podstawy wykluczenia.

Odpowiedz w formacie JSON:
{
  "eligible": true/false,
  "conditions": [
    {
      "name": "nazwa warunku",
      "description": "co jest wymagane",
      "met": true/false,
      "reason": "dlaczego spełniony/niespełniony",
      "fixable": true/false,
      "fix_options": ["opcja 1", "opcja 2"]
    }
  ],
  "summary": "krótkie podsumowanie",
  "scope_description": "co trzeba zrealizować w ramach zamówienia (2-3 zdania)",
  "estimated_budget": "szacunkowy budżet jeśli znany, inaczej 'nieokreślony'"
}"""

    system = (
        "Jesteś krytycznym asystentem do analizy przetargów w Polsce. "
        "Nie domyślaj się — jeśli czegoś nie wiesz, zaznacz to. "
        "Odpowiadaj po polsku. Zwracaj TYLKO valid JSON."
    )

    result = await call_claude(prompt, context_files=attachments, system_prompt=system)
    return result if isinstance(result, dict) else {"raw": result}


# Steps 1-5 will follow the same pattern — prompt template + call_claude + parse
# Placeholder functions for now:

async def run_step1(analysis: Analysis, tender: Tender, profile: CompanyProfile) -> dict:
    """Step 1: Required documents list."""
    # TODO: Implement with proper prompt
    return {"status": "not_implemented"}


async def run_step2(analysis: Analysis, tender: Tender, profile: CompanyProfile) -> dict:
    """Step 2: Pricing, criteria, deadlines, personnel."""
    return {"status": "not_implemented"}


async def run_step3(analysis: Analysis, tender: Tender, profile: CompanyProfile) -> dict:
    """Step 3: Risk analysis."""
    return {"status": "not_implemented"}


async def run_step4(analysis: Analysis, tender: Tender, profile: CompanyProfile) -> dict:
    """Step 4: Cost estimation."""
    return {"status": "not_implemented"}


async def run_step5(analysis: Analysis, tender: Tender, profile: CompanyProfile) -> dict:
    """Step 5: Document guidance."""
    return {"status": "not_implemented"}
