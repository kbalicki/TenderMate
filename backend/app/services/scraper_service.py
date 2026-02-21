"""Scrapes tender pages via external microservice and downloads attachments."""

import asyncio
import logging
import re
import urllib.parse
from pathlib import Path

import httpx
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.tender import Tender
from app.models.tender_attachment import TenderAttachment
from app.scrapers.base import detect_portal

logger = logging.getLogger(__name__)

# Keep strong references to background tasks
_background_tasks: set[asyncio.Task] = set()


def _sanitize_filename(name: str, max_len: int = 200) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = re.sub(r'_+', '_', name).strip('. _')
    if len(name) > max_len:
        parts = name.rsplit('.', 1)
        if len(parts) == 2 and len(parts[1]) <= 10:
            name = parts[0][: max_len - len(parts[1]) - 1] + '.' + parts[1]
        else:
            name = name[:max_len]
    return name or "attachment"


def _guess_mime(filename: str) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "zip": "application/zip",
        "7z": "application/x-7z-compressed",
        "rar": "application/x-rar-compressed",
        "txt": "text/plain",
        "csv": "text/csv",
    }.get(ext)


async def _download_attachment(
    client: httpx.AsyncClient,
    att: dict,
    att_dir: Path,
    cookies: dict | None = None,
) -> Path | None:
    """Download a single attachment file."""
    url = att.get("url", "")
    name = att.get("name", "")
    if not url:
        return None

    filename = _sanitize_filename(name) if name else _sanitize_filename(
        urllib.parse.unquote(url.split("/")[-1].split("?")[0]) or "attachment"
    )

    file_path = att_dir / filename
    # Avoid overwriting
    if file_path.exists():
        stem, suffix = file_path.stem, file_path.suffix
        for n in range(1, 100):
            file_path = att_dir / f"{stem}_{n}{suffix}"
            if not file_path.exists():
                break

    try:
        # Build cookie header from scraped cookies (dict: {name: value})
        headers = {}
        if cookies:
            cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
            headers["Cookie"] = cookie_header

        resp = await client.get(url, headers=headers, follow_redirects=True, timeout=120.0)
        if resp.status_code >= 400:
            logger.warning(f"[Scraper] HTTP {resp.status_code} pobierając {filename}")
            return None

        file_path.write_bytes(resp.content)
        logger.info(f"[Scraper] Pobrano: {filename} ({len(resp.content)} B)")
        return file_path
    except Exception as e:
        logger.warning(f"[Scraper] Błąd pobierania {filename}: {e}")
        return None


async def _run_scraping(tender_id: int) -> None:
    """Background task: call scraper microservice, download attachments, update DB."""
    logger.info(f"[Scraper] Rozpoczynam scraping dla tender_id={tender_id}")

    async with async_session() as db:
        tender = await db.get(Tender, tender_id)
        if not tender:
            logger.error(f"[Scraper] Nie znaleziono tender_id={tender_id}")
            return

        url = tender.source_url
        if not url:
            tender.status = "scrape_failed"
            await db.commit()
            return

        data_dir = Path(tender.data_dir) if tender.data_dir else settings.data_dir / "tenders" / str(tender_id)
        data_dir.mkdir(parents=True, exist_ok=True)
        att_dir = data_dir / "attachments"
        att_dir.mkdir(exist_ok=True)

        if not tender.data_dir:
            tender.data_dir = str(data_dir)

        tender.status = "scraping"
        await db.commit()

    # Call scraper microservice
    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"[Scraper] Wywołuję mikroserwis: {url[:100]}")
            resp = await client.post(
                settings.scraper_url,
                json={"url": url},
                timeout=180.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.exception(f"[Scraper] Błąd mikroserwisu dla tender_id={tender_id}: {e}")
        async with async_session() as db:
            tender = await db.get(Tender, tender_id)
            if tender:
                tender.status = "scrape_failed"
                await db.commit()
        return

    scraped_title = data.get("title", "")
    scraped_text = data.get("text", "")
    attachments = data.get("attachments", [])
    cookies = data.get("cookies", [])

    logger.info(
        f"[Scraper] Mikroserwis OK: tytuł='{scraped_title[:80]}', "
        f"tekst={len(scraped_text)} zn., załączników={len(attachments)}"
    )

    # Download attachments
    downloaded_files: list[Path] = []
    if attachments:
        async with httpx.AsyncClient() as client:
            for att in attachments:
                path = await _download_attachment(client, att, att_dir, cookies)
                if path:
                    downloaded_files.append(path)

    logger.info(f"[Scraper] Pobrano {len(downloaded_files)}/{len(attachments)} załączników")

    # Extract metadata from text using regex
    authority = ""
    for pattern in [
        r'(?:Zamawiaj[ąa]cy|Nazwa zamawiaj[ąa]cego|Dane zamawiaj[ąa]cego)\s*([^\n]{5,150})',
        r'(?:Beneficjent)[:\s]*([^\n]{5,150})',
    ]:
        match = re.search(pattern, scraped_text)
        if match:
            authority = match.group(1).strip().rstrip(',.')
            break

    ref_number = ""
    for pattern in [
        r'(?:Numer post[ęe]powania|Numer og[łl]oszenia|Nr referencyjny|Znak sprawy)[:\s]*([\w/\-\.]+)',
    ]:
        match = re.search(pattern, scraped_text)
        if match:
            ref_number = match.group(1).strip()
            break

    deadline = ""
    for pattern in [
        r'(?:Termin sk[łl]adania wniosk[óo]w / ofert|Termin sk[łl]adania ofert|'
        r'Termin z[łl]o[żz]enia ofert)[:\s]*'
        r'(\d{1,2}[\.\-/]\d{1,2}[\.\-/]\d{2,4}(?:\s+\d{1,2}:\d{2})?)',
    ]:
        match = re.search(pattern, scraped_text)
        if match:
            deadline = match.group(1).strip()
            break

    tender_title = ""
    for pattern in [
        r'(?:Nazwa post[ęe]powania|Nazwa zam[óo]wienia)[:\s]*([^\n]{5,250})',
    ]:
        match = re.search(pattern, scraped_text)
        if match:
            tender_title = match.group(1).strip()
            break
    if not tender_title:
        tender_title = scraped_title

    # Update tender in DB
    async with async_session() as db:
        tender = await db.get(Tender, tender_id)
        if not tender:
            return

        tender.portal_name = detect_portal(url)
        tender.title = tender_title or tender.title
        tender.contracting_authority = authority or None
        tender.reference_number = ref_number or None
        tender.tender_text = scraped_text

        if deadline:
            from dateutil import parser as dateparser
            try:
                tender.submission_deadline = dateparser.parse(deadline, dayfirst=True)
            except Exception:
                logger.warning(f"[Scraper] Nie sparsowano daty: {deadline}")

        # Register downloaded files as attachments
        for f in downloaded_files:
            existing = await db.execute(
                select(TenderAttachment).where(
                    TenderAttachment.tender_id == tender_id,
                    TenderAttachment.filename == f.name,
                )
            )
            if existing.scalar_one_or_none():
                continue

            db.add(TenderAttachment(
                tender_id=tender_id,
                filename=f.name,
                original_url=next(
                    (a["url"] for a in attachments if _sanitize_filename(a.get("name", "")) == f.name),
                    None,
                ),
                file_path=str(f.relative_to(Path(tender.data_dir))),
                file_size_bytes=f.stat().st_size,
                mime_type=_guess_mime(f.name),
            ))

        tender.status = "scraped"
        await db.commit()

        logger.info(
            f"[Scraper] Scraping zakończony tender_id={tender_id}: "
            f"tytuł='{tender.title}', załączników={len(downloaded_files)}"
        )


async def launch_scraping(tender_id: int) -> None:
    """Launch scraping as a background asyncio task."""
    logger.info(f"[Scraper] Uruchamiam task scrapingu dla tender_id={tender_id}")

    async def _wrapped():
        try:
            await _run_scraping(tender_id)
        except Exception:
            logger.exception(f"[Scraper] Nieobsłużony wyjątek w scrapingu tender_id={tender_id}")

    task = asyncio.create_task(_wrapped())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
