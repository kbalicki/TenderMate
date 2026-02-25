"""Dedicated scraper for bazakonkurencyjnosci.funduszeeuropejskie.gov.pl.

Uses the public JSON API at /api/announcements/{id} to fetch tender details,
evaluation criteria, attachments, and structured metadata.
"""

import logging
import re

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://bazakonkurencyjnosci.funduszeeuropejskie.gov.pl"


def _extract_id(url: str) -> str | None:
    """Extract announcement ID from URL like /ogloszenia/265934."""
    match = re.search(r'/ogloszenia/(\d+)', url)
    return match.group(1) if match else None


async def scrape_tender(url: str) -> dict:
    """Scrape a tender from Baza Konkurencyjności via JSON API.

    Returns dict compatible with scraper_service expectations:
    {
        "title": str,
        "text": str,
        "attachments": [{"name": str, "url": str}, ...],
        "metadata": {"authority": str, "ref_number": str, "deadline": str},
    }
    """
    ann_id = _extract_id(url)
    if not ann_id:
        raise ValueError(f"Nie można wyciągnąć ID ogłoszenia z URL: {url}")

    api_url = f"{BASE_URL}/api/announcements/{ann_id}"
    logger.info(f"[BK] Pobieram dane z API: {api_url}")

    async with httpx.AsyncClient() as client:
        resp = await client.get(api_url, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "OK":
        raise ValueError(f"API zwróciło błąd: {data.get('message', 'unknown')}")

    ad = data["data"]["advertisement"]

    # --- Title ---
    title = ad.get("title", "")

    # --- Authority ---
    advertiser = ad.get("advertiser_address_details", {})
    authority = advertiser.get("name", "")

    # --- Reference number ---
    nested_ad = ad.get("advertisement", {})
    ref_number = nested_ad.get("number", "")

    # --- Deadline ---
    deadline = ad.get("submission_deadline", "")

    # --- Build full text ---
    text_parts: list[str] = []

    text_parts.append(f"TYTUŁ: {title}")
    text_parts.append(f"ZAMAWIAJĄCY: {authority}")
    if ref_number:
        text_parts.append(f"NUMER OGŁOSZENIA: {ref_number}")
    text_parts.append(f"DATA PUBLIKACJI: {ad.get('publication_date', '')}")
    text_parts.append(f"TERMIN SKŁADANIA OFERT: {deadline}")

    status = ad.get("status", {})
    if isinstance(status, dict):
        text_parts.append(f"STATUS: {status.get('name', '')}")

    # Address
    addr = advertiser.get("address", {})
    if addr:
        address_str = (
            f"{addr.get('street', '')} {addr.get('number_description', '')}, "
            f"{addr.get('postcode', '')} {addr.get('locality', '')}"
        ).strip(", ")
        nip = advertiser.get("identification_number", "")
        text_parts.append(f"ADRES: {address_str}")
        if nip:
            text_parts.append(f"NIP: {nip}")

    # Contact persons
    contacts = ad.get("contact_persons", [])
    if contacts:
        text_parts.append("")
        text_parts.append("OSOBY DO KONTAKTU:")
        for c in contacts:
            name = f"{c.get('forename', '')} {c.get('surname', '')}".strip()
            email = c.get("email", "")
            phone = c.get("phone_number", "")
            parts = [name]
            if email:
                parts.append(f"e-mail: {email}")
            if phone:
                parts.append(f"tel: {phone}")
            text_parts.append(f"  - {', '.join(parts)}")

    # Supplementary orders
    suppl = ad.get("supplementary_orders", "")
    if suppl:
        text_parts.append("")
        text_parts.append(f"ZAMÓWIENIA UZUPEŁNIAJĄCE: {suppl}")

    # Contract change terms
    terms = ad.get("terms_of_contract_change", "")
    if terms:
        text_parts.append("")
        text_parts.append(f"WARUNKI ZMIANY UMOWY: {terms}")

    # Partial offers
    partial = ad.get("partial_offer_allowed")
    if partial is not None:
        text_parts.append(
            f"OFERTY CZĘŚCIOWE: {'Tak' if partial else 'Nie'}"
        )

    # Orders (main content)
    orders = ad.get("orders", [])
    for i, order in enumerate(orders, 1):
        text_parts.append("")
        order_title = order.get("title", "")
        if order_title:
            text_parts.append(f"=== CZĘŚĆ {i}: {order_title} ===")

        # Estimated value
        est_val = order.get("estimated_value")
        if est_val:
            text_parts.append(f"SZACUNKOWA WARTOŚĆ: {est_val}")

        # Variants
        is_variant = order.get("is_variant")
        if is_variant is not None:
            text_parts.append(
                f"WARIANTY: {'Dopuszczalne' if is_variant else 'Niedopuszczalne'}"
            )

        # Order items (description of what's being procured)
        for item in order.get("order_items", []):
            desc = item.get("description", "")
            if desc:
                text_parts.append("")
                text_parts.append("OPIS PRZEDMIOTU ZAMÓWIENIA:")
                text_parts.append(desc)

        # Evaluation criteria
        criteria = order.get("evaluation_criteria", [])
        if criteria:
            text_parts.append("")
            text_parts.append("KRYTERIA OCENY OFERT:")
            for ec in criteria:
                is_price = ec.get("price_criterion", False)
                desc = ec.get("description", "")
                label = "KRYTERIUM CENOWE" if is_price else "KRYTERIUM"
                text_parts.append(f"  {label}: {desc}")

    text = "\n".join(text_parts)

    # --- Attachments ---
    attachments: list[dict] = []
    for att in ad.get("attachments", []):
        file_info = att.get("file", {})
        uri = file_info.get("uri", "")
        name = att.get("name", "") or file_info.get("name", "attachment")
        if uri:
            attachments.append({
                "name": name,
                "url": f"{BASE_URL}{uri}",
            })

    logger.info(
        f"[BK] Pobrano ogłoszenie {ann_id}: tytuł='{title[:80]}', "
        f"załączników={len(attachments)}, tekst={len(text)} zn."
    )

    return {
        "title": title,
        "text": text,
        "attachments": attachments,
        "metadata": {
            "authority": authority,
            "ref_number": ref_number,
            "deadline": deadline,
        },
    }
