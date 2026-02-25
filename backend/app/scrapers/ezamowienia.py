"""Dedicated scraper for ezamowienia.gov.pl using their public API."""

import logging
import re

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://ezamowienia.gov.pl"
SEARCH_TENDER_URL = f"{BASE_URL}/mp-readmodels/api/Search/GetTender"
SEARCH_DOCUMENTS_URL = f"{BASE_URL}/mp-readmodels/api/Search/GetTenderDocuments"
DOWNLOAD_DOCUMENT_URL = f"{BASE_URL}/mp-readmodels/api/Tender/DownloadDocument"
BZP_SEARCH_URL = f"{BASE_URL}/mo-board/api/v1/Board/Search"
BZP_NOTICE_PDF_URL = f"{BASE_URL}/mo-board/api/v1/Board/GetNoticePdfById"


def extract_ocds_id(url: str) -> str | None:
    """Extract OCDS identifier from an ezamowienia.gov.pl URL."""
    match = re.search(r'(ocds-148610-[0-9a-f\-]+)', url)
    return match.group(1) if match else None


async def get_tender_details(client: httpx.AsyncClient, ocds_id: str) -> dict | None:
    """Fetch tender details from the public search API."""
    try:
        resp = await client.get(
            SEARCH_TENDER_URL,
            params={"id": ocds_id},
            timeout=30.0,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"[ezamowienia] GetTender status={resp.status_code}")
    except Exception as e:
        logger.warning(f"[ezamowienia] GetTender error: {e}")
    return None


async def get_tender_documents(client: httpx.AsyncClient, ocds_id: str) -> list[dict]:
    """Fetch list of tender documents from the public search API."""
    try:
        resp = await client.get(
            SEARCH_DOCUMENTS_URL,
            params={"tenderId": ocds_id},
            timeout=30.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
            logger.warning(f"[ezamowienia] GetTenderDocuments unexpected format: {type(data)}")
        else:
            logger.warning(f"[ezamowienia] GetTenderDocuments status={resp.status_code}")
    except Exception as e:
        logger.warning(f"[ezamowienia] GetTenderDocuments error: {e}")
    return []


async def download_document(
    client: httpx.AsyncClient, ocds_id: str, doc_object_id: str
) -> tuple[bytes, str] | None:
    """Download a single document. Returns (content_bytes, filename) or None."""
    url = f"{DOWNLOAD_DOCUMENT_URL}/{ocds_id}/{doc_object_id}"
    try:
        resp = await client.get(url, timeout=120.0, follow_redirects=True)
        if resp.status_code == 200:
            # Try to get filename from Content-Disposition header
            cd = resp.headers.get("content-disposition", "")
            filename = ""
            if "filename=" in cd:
                match = re.search(r'filename[*]?=["\']?(?:UTF-8\'\')?([^"\';\r\n]+)', cd)
                if match:
                    filename = match.group(1).strip()
            return resp.content, filename
        logger.warning(f"[ezamowienia] DownloadDocument {doc_object_id} status={resp.status_code}")
    except Exception as e:
        logger.warning(f"[ezamowienia] DownloadDocument {doc_object_id} error: {e}")
    return None


async def search_bzp_notice(client: httpx.AsyncClient, notice_number: str) -> dict | None:
    """Search for a BZP notice by number."""
    try:
        resp = await client.get(
            BZP_SEARCH_URL,
            params={"noticeNumber": notice_number},
            timeout=30.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                return data[0]
    except Exception as e:
        logger.warning(f"[ezamowienia] BZP search error: {e}")
    return None


def _extract_deadline(tender_data: dict) -> str:
    """Extract submission deadline from terms array."""
    for term in tender_data.get("terms", []):
        if term.get("termType") == "SubmissionOffersDate" and term.get("term"):
            return term["term"]
    return ""


def extract_text_from_tender(tender_data: dict) -> str:
    """Extract readable text from tender API response."""
    parts = []

    title = tender_data.get("title", "") or tender_data.get("orderObject", "")
    if title:
        parts.append(f"Nazwa zamówienia: {title}")

    if tender_data.get("organizationName"):
        parts.append(f"Zamawiający: {tender_data['organizationName']}")
        if tender_data.get("organizationCity"):
            parts[-1] += f", {tender_data['organizationCity']}"
        if tender_data.get("organizationProvince"):
            parts[-1] += f" ({tender_data['organizationProvince']})"

    ref = tender_data.get("referenceNumber", "")
    if ref:
        parts.append(f"Numer postępowania: {ref}")

    if tender_data.get("bzpNumber"):
        parts.append(f"Numer ogłoszenia BZP: {tender_data['bzpNumber']}")

    if tender_data.get("tenderType"):
        parts.append(f"Typ zamówienia: {tender_data['tenderType']}")

    if tender_data.get("isTenderAmountBelowEU") is not None:
        below = "poniżej" if tender_data["isTenderAmountBelowEU"] else "powyżej"
        parts.append(f"Próg unijny: {below} progu")

    if tender_data.get("stage"):
        parts.append(f"Etap: {tender_data['stage']}")

    deadline = _extract_deadline(tender_data)
    if deadline:
        parts.append(f"Termin składania ofert: {deadline}")

    open_date = ""
    for term in tender_data.get("terms", []):
        if term.get("termType") == "OpenOffersDate" and term.get("term"):
            open_date = term["term"]
    if open_date:
        parts.append(f"Termin otwarcia ofert: {open_date}")

    if tender_data.get("noticeConcerns"):
        parts.append(f"Dotyczy: {tender_data['noticeConcerns']}")

    # Lots
    lots = tender_data.get("lots", [])
    if lots:
        parts.append(f"\nCzęści zamówienia ({len(lots)}):")
        for lot in lots:
            parts.append(f"  - {lot.get('name', lot.get('objectId', '?'))}")

    if tender_data.get("isPartial"):
        parts.append("Zamówienie częściowe: TAK")

    # Document names
    docs = tender_data.get("tenderDocuments", [])
    if docs:
        parts.append("\nDokumenty przetargowe:")
        for doc in docs:
            att = doc.get("attachment", {})
            name = doc.get("name", att.get("fileName", "?"))
            fname = att.get("fileName", "")
            size = att.get("fileSize", 0)
            state = doc.get("tenderDocumentState", "")
            line = f"  - {name}"
            if fname and fname != name:
                line += f" ({fname})"
            if size:
                line += f" [{size:,} B]"
            if state:
                line += f" [{state}]"
            parts.append(line)

    return "\n".join(parts)


async def scrape_tender(url: str) -> dict:
    """Main entry point: scrape a tender from ezamowienia.gov.pl.

    Returns a dict compatible with scraper_service expectations:
    {
        "title": str,
        "text": str,
        "attachments": [{"url": str, "name": str, "object_id": str}],
        "metadata": {
            "authority": str,
            "ref_number": str,
            "deadline": str,
            "ocds_id": str,
        },
    }
    """
    ocds_id = extract_ocds_id(url)
    if not ocds_id:
        logger.error(f"[ezamowienia] Cannot extract OCDS ID from URL: {url}")
        return {"title": "", "text": "", "attachments": [], "metadata": {}}

    logger.info(f"[ezamowienia] Scraping tender OCDS ID: {ocds_id}")

    async with httpx.AsyncClient() as client:
        # 1. Get tender details
        tender_data = await get_tender_details(client, ocds_id)

        title = ""
        text = ""
        metadata = {"ocds_id": ocds_id}

        if tender_data:
            title = tender_data.get("title", "") or tender_data.get("orderObject", "")
            text = extract_text_from_tender(tender_data)
            metadata["authority"] = tender_data.get("organizationName", "")
            metadata["ref_number"] = tender_data.get("referenceNumber", "")
            metadata["deadline"] = _extract_deadline(tender_data)
            metadata["bzp_number"] = tender_data.get("bzpNumber", "")
            logger.info(f"[ezamowienia] Tender details OK: '{title[:80]}'")
        else:
            logger.warning(f"[ezamowienia] No tender details for {ocds_id}")

        # 2. Get document list
        documents = await get_tender_documents(client, ocds_id)
        logger.info(f"[ezamowienia] Found {len(documents)} documents")

        # Build attachment list with download URLs
        attachments = []
        for doc in documents:
            # Documents from GetTenderDocuments may have different structures
            obj_id = doc.get("objectId", "")
            filename = doc.get("fileName", "") or doc.get("name", "")

            # Some responses have nested attachment
            att_info = doc.get("attachment", {})
            if not filename and att_info:
                filename = att_info.get("fileName", "")
            if not obj_id and att_info:
                obj_id = att_info.get("uniqueAttachmentIdentifier", "")

            if not obj_id:
                continue

            download_url = f"{DOWNLOAD_DOCUMENT_URL}/{ocds_id}/{obj_id}"
            attachments.append({
                "url": download_url,
                "name": filename or obj_id,
                "object_id": obj_id,
            })
            logger.info(f"[ezamowienia] Document: {filename} (id={obj_id})")

        # If GetTenderDocuments returned nothing, try extracting from tender details
        if not attachments and tender_data:
            tender_docs = tender_data.get("tenderDocuments", [])
            for doc in tender_docs:
                obj_id = doc.get("objectId", "")
                att_info = doc.get("attachment", {})
                filename = att_info.get("fileName", "") or doc.get("name", "")
                state = doc.get("tenderDocumentState", "")

                if not obj_id or state == "Archived":
                    continue

                download_url = f"{DOWNLOAD_DOCUMENT_URL}/{ocds_id}/{obj_id}"
                attachments.append({
                    "url": download_url,
                    "name": filename or obj_id,
                    "object_id": obj_id,
                })
                logger.info(f"[ezamowienia] Document (from tender): {filename} (id={obj_id})")

    return {
        "title": title,
        "text": text,
        "attachments": attachments,
        "metadata": metadata,
    }
