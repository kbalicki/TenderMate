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
from app.scrapers.ezamowienia import scrape_tender as scrape_ezamowienia
from app.scrapers.logintrade import scrape_tender as scrape_logintrade

logger = logging.getLogger(__name__)

_PUBLIC_AUTHORITY_KEYWORDS = [
    "urząd", "urzad", "gmina", "starostwo", "powiat", "województwo", "wojewodztwo",
    "ministerstwo", "ministerstwa", "szpital", "kliniczny", "uniwersytet",
    "politechnika", "szkoła", "szkola", "akademia", "instytut",
    "centrum", "agencja", "fundusz", "inspektorat", "komenda",
    "prokuratura", "sąd", "sad", "biblioteka", "muzeum", "teatr",
    "zarząd", "zarzad", "wody polskie", "lasy państwowe", "lasy panstwowe",
    "wojskow", "policj", "straż", "straz", "miejsk", "powiatow",
    "gminny", "gminna", "państwow", "panstwow", "publiczn",
    "samorząd", "samorzad", "stowarzyszenie", "fundacja",
]

_PUBLIC_PORTALS = ["ezamowienia.gov.pl", "bazakonkurencyjnosci"]


def _detect_authority_type(authority_name: str | None, url: str | None) -> str | None:
    """Heuristic: detect if contracting authority is public or private."""
    url_lower = (url or "").lower()
    for portal in _PUBLIC_PORTALS:
        if portal in url_lower:
            return "public"
    if not authority_name:
        return None
    name_lower = authority_name.lower()
    for kw in _PUBLIC_AUTHORITY_KEYWORDS:
        if kw in name_lower:
            return "public"
    return "private"


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


def _extract_filename_from_cd(content_disposition: str) -> str | None:
    """Extract filename from Content-Disposition, preferring filename* (RFC 5987)."""
    if not content_disposition:
        return None
    # Try filename*=utf-8''... first (proper encoding)
    match = re.search(r"filename\*\s*=\s*(?:UTF-8|utf-8)''(.+?)(?:$|;)", content_disposition)
    if match:
        return urllib.parse.unquote(match.group(1).strip().strip('"'))
    # Fallback to plain filename="..."
    match = re.search(r'filename\s*=\s*"?([^";]+)"?', content_disposition)
    if match:
        return match.group(1).strip()
    return None


def _decode_zip_filename(member: 'zipfile.ZipInfo') -> str:
    """Decode ZIP member filename handling Polish encoding (cp852/cp437)."""
    raw = member.filename
    # If flag_bits bit 11 is set, filename is UTF-8
    if member.flag_bits & 0x800:
        return Path(raw).name
    # Try cp852 (DOS Polish), then cp437 (DOS default)
    try:
        return Path(raw.encode('cp437').decode('cp852')).name
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return Path(raw).name


def _extract_zip_files(downloaded_files: list[Path], att_dir: Path, max_depth: int = 3) -> list[Path]:
    """Extract files from ZIP archives among downloaded attachments.

    Handles nested ZIPs recursively up to max_depth levels.
    """
    import zipfile

    extracted: list[Path] = []
    zips_to_process = [f for f in downloaded_files if f.suffix.lower() == '.zip']

    depth = 0
    while zips_to_process and depth < max_depth:
        depth += 1
        next_round_zips: list[Path] = []

        for zip_path in zips_to_process:
            if not zip_path.exists() or not zipfile.is_zipfile(zip_path):
                continue

            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    for member in zf.infolist():
                        if member.is_dir():
                            continue
                        # Skip hidden/system files
                        basename = _decode_zip_filename(member)
                        if basename.startswith('.') or basename.startswith('__'):
                            continue

                        safe_name = _sanitize_filename(basename)
                        target = att_dir / safe_name
                        # Avoid overwriting
                        if target.exists():
                            stem, suffix = target.stem, target.suffix
                            for n in range(1, 100):
                                target = att_dir / f"{stem}_{n}{suffix}"
                                if not target.exists():
                                    break

                        target.write_bytes(zf.read(member.filename))
                        extracted.append(target)
                        logger.info(
                            f"[Scraper] ZIP extract (depth={depth}): "
                            f"{zip_path.name} → {safe_name} ({member.file_size} B)"
                        )

                        # Queue nested ZIPs for next round
                        if target.suffix.lower() == '.zip':
                            next_round_zips.append(target)

                # Remove the ZIP file itself — contents are now extracted
                if zip_path in downloaded_files:
                    downloaded_files.remove(zip_path)
                zip_path.unlink()
                logger.info(f"[Scraper] Usunięto archiwum ZIP: {zip_path.name}")
            except Exception as e:
                logger.warning(f"[Scraper] Błąd ekstrakcji ZIP {zip_path.name}: {e}")

        zips_to_process = next_round_zips

    return extracted


async def _download_attachment(
    client: httpx.AsyncClient,
    att: dict,
    att_dir: Path,
    cookies: dict | None = None,
) -> Path | None:
    """Download a single attachment file."""
    url = att.get("url", "")
    name = att.get("name", "")
    pre_downloaded = att.get("_content")  # pre-downloaded bytes (e.g. BZP PDF)

    if not url and not pre_downloaded:
        return None

    try:
        if pre_downloaded:
            content = pre_downloaded
            filename = _sanitize_filename(name) if name else "attachment"
        else:
            # Build cookie header from scraped cookies (dict: {name: value})
            headers = {}
            if cookies:
                cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
                headers["Cookie"] = cookie_header

            resp = await client.get(url, headers=headers, follow_redirects=True, timeout=120.0)
            if resp.status_code >= 400:
                logger.warning(f"[Scraper] HTTP {resp.status_code} pobierając {name or url[-50:]}")
                return None
            content = resp.content

            # Try to get proper filename from Content-Disposition header
            cd = resp.headers.get("content-disposition", "")
            cd_filename = _extract_filename_from_cd(cd)
            if cd_filename:
                filename = _sanitize_filename(cd_filename)
            elif name:
                filename = _sanitize_filename(name)
            else:
                filename = _sanitize_filename(
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

        file_path.write_bytes(content)
        logger.info(f"[Scraper] Pobrano: {filename} ({len(content)} B)")
        return file_path
    except Exception as e:
        logger.warning(f"[Scraper] Błąd pobierania {name or url[-50:]}: {e}")
        return None


def _clean_scraped_text(text: str) -> str:
    """Remove common web scraping artifacts from tender text."""
    if not text:
        return text

    # Lines to remove entirely (navigation, UI artifacts, cookie banners)
    junk_patterns = [
        r'^print$',
        r'^Pobierz plik PDF.*$',
        r'^Generowanie pliku PDF.*$',
        r'^Strona g[łl][óo]wna.*$',
        r'^Zaloguj si[ęe].*$',
        r'^Wyloguj.*$',
        r'^Rejestracja.*$',
        r'^Menu\s*$',
        r'^Szukaj\s*$',
        r'^Wyszukaj\s*$',
        r'^Cookies?.*polityk[aą].*$',
        r'^Ta strona wykorzystuje.*ciasteczk.*$',
        r'^Akceptuj[ęe]?\s*$',
        r'^Odrzuć\s*$',
        r'^Zamknij\s*$',
        r'^Drukuj\s*$',
        r'^Udost[ęe]pnij\s*$',
        r'^Wersja do druku\s*$',
        r'^Przejd[źz] do tre[śs]ci.*$',
        r'^Skip to content.*$',
        r'^Powrót do listy.*$',
        r'^Nawigacja\s*$',
        r'^Breadcrumb.*$',
        r'^Toggle navigation\s*$',
        r'^\s*\|\s*$',
        r'^©.*$',
        r'^Copyright.*$',
        r'^Wszelkie prawa zastrzeżone.*$',
        r'^Powered by.*$',
        r'^\s*Loading\.{0,3}\s*$',
        r'^Ładowanie\.{0,3}\s*$',
    ]

    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            # Keep single blank lines, collapse multiple
            if cleaned and cleaned[-1] == '':
                continue
            cleaned.append('')
            continue
        skip = False
        for pat in junk_patterns:
            if re.match(pat, stripped, re.IGNORECASE):
                skip = True
                break
        if not skip:
            cleaned.append(line)

    result = '\n'.join(cleaned).strip()
    # Collapse 3+ consecutive blank lines to 2
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result


async def _generate_ai_summary(tender_id: int) -> None:
    """Generate a short AI summary of the tender in background."""
    try:
        from app.services.claude_service import call_claude

        async with async_session() as db:
            tender = await db.get(Tender, tender_id)
            if not tender or not tender.tender_text:
                return

            # Use first 5000 chars + title for summary
            text_excerpt = tender.tender_text[:5000]
            prompt = (
                f"Na podstawie poniższego opisu przetargu napisz ZWIĘZŁE podsumowanie w 1-2 zdaniach po polsku. "
                f"Opisz KONKRETNIE co trzeba zrobić/dostarczyć — samo meritum projektu, np. "
                f"'Stworzenie aplikacji mobilnej do zarządzania flotą pojazdów z integracją GPS i systemem raportowania.' "
                f"NIE pisz kto jest zamawiającym, NIE pisz o terminach, NIE zaczynaj od 'Przedmiotem zamówienia jest...'. "
                f"Pisz wprost, jakbyś opowiadał komuś w jednym zdaniu o czym jest ten projekt. "
                f"Odpowiedz SAMYM TEKSTEM, bez JSON.\n\n"
                f"Tytuł: {tender.title or 'brak'}\n\n"
                f"{text_excerpt}"
            )

            result = await call_claude(prompt)
            summary = result if isinstance(result, str) else str(result)
            # Strip any JSON wrapping if Claude returned it anyway
            summary = summary.strip().strip('"').strip()
            if len(summary) > 1000:
                summary = summary[:1000]

        async with async_session() as db:
            tender = await db.get(Tender, tender_id)
            if tender:
                tender.ai_summary = summary
                await db.commit()
                logger.info(f"[Scraper] AI summary wygenerowane dla tender_id={tender_id}: {summary[:100]}...")

    except Exception as e:
        logger.warning(f"[Scraper] Nie udało się wygenerować AI summary dla tender_id={tender_id}: {e}")


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

    # Use dedicated scraper for known portals, fallback to generic microservice
    is_ezamowienia = "ezamowienia.gov.pl" in url.lower()
    is_logintrade = "logintrade.net" in url.lower()

    try:
        if is_ezamowienia:
            logger.info(f"[Scraper] Używam dedykowanego scrapera ezamowienia.gov.pl")
            data = await scrape_ezamowienia(url)
            cookies = {}
        elif is_logintrade:
            logger.info(f"[Scraper] Używam dedykowanego scrapera logintrade.net")
            data = await scrape_logintrade(url)
            cookies = {}
        else:
            async with httpx.AsyncClient() as client:
                logger.info(f"[Scraper] Wywołuję mikroserwis: {url[:100]}")
                resp = await client.post(
                    settings.scraper_url,
                    json={"url": url},
                    timeout=180.0,
                )
                resp.raise_for_status()
                data = resp.json()
                cookies = data.get("cookies", {})
    except Exception as e:
        logger.exception(f"[Scraper] Błąd scrapingu dla tender_id={tender_id}: {e}")
        async with async_session() as db:
            tender = await db.get(Tender, tender_id)
            if tender:
                tender.status = "scrape_failed"
                tender.error_message = f"Błąd scrapingu: {e}"
                await db.commit()
        return

    scraped_title = data.get("title", "")
    scraped_text = data.get("text", "")
    attachments = data.get("attachments", [])

    logger.info(
        f"[Scraper] Mikroserwis OK: tytuł='{scraped_title[:80]}', "
        f"tekst={len(scraped_text)} zn., załączników={len(attachments)}"
    )

    # Clean old attachments before re-downloading (rescrape case)
    async with async_session() as db:
        old_atts = await db.execute(
            select(TenderAttachment).where(TenderAttachment.tender_id == tender_id)
        )
        old_atts_list = old_atts.scalars().all()
        if old_atts_list:
            logger.info(f"[Scraper] Usuwam {len(old_atts_list)} starych załączników z DB")
            for old_att in old_atts_list:
                # Delete file from disk
                old_file = att_dir / old_att.filename
                if old_file.exists():
                    old_file.unlink()
                    logger.debug(f"[Scraper] Usunięto plik: {old_file.name}")
                await db.delete(old_att)
            await db.commit()

    # Download attachments
    downloaded_files: list[Path] = []
    if attachments:
        async with httpx.AsyncClient() as client:
            for att in attachments:
                path = await _download_attachment(client, att, att_dir, cookies)
                if path:
                    downloaded_files.append(path)

    logger.info(f"[Scraper] Pobrano {len(downloaded_files)}/{len(attachments)} załączników")

    # Extract ZIP archives and add contained files
    extracted_files = _extract_zip_files(downloaded_files, att_dir)
    if extracted_files:
        downloaded_files.extend(extracted_files)
        logger.info(f"[Scraper] Wyodrębniono {len(extracted_files)} plików z archiwów ZIP")

    # Collect warnings about missing data
    scrape_warnings: list[str] = []
    if not scraped_text.strip():
        scrape_warnings.append("Nie udało się pobrać treści ogłoszenia (pusty tekst)")
    if attachments and len(downloaded_files) < len(attachments):
        failed_count = len(attachments) - len(downloaded_files)
        scrape_warnings.append(f"Nie pobrano {failed_count}/{len(attachments)} załączników")

    # Extract metadata — use structured data from dedicated scrapers or regex fallback
    ez_metadata = data.get("metadata", {})

    authority = ez_metadata.get("authority", "")
    if not authority:
        # Baza Konkurencyjności: "Dane adresowe ogłoszeniodawcy Firma Sp. z o.o. Ulica 123 00-000 Miasto NIP: ..."
        bk_match = re.search(
            r'Dane adresowe og[łl]oszeniodawcy\s+(.+?)(?:\s+\d{2}-\d{3}\s|\s+NIP:)',
            scraped_text,
        )
        if bk_match:
            # Extract company name — strip address part (street with number at end)
            raw = bk_match.group(1).strip()
            # Remove trailing street address (e.g. "ul. Cieplaka 1C" or "Jana Pawła II 35")
            addr_match = re.search(r'\s+(?:ul\.|al\.|pl\.)?\s*[A-ZŻŹĆĄŚĘŁÓŃ][a-ząćęłńóśźż]+(?:\s+[A-ZŻŹĆĄŚĘŁÓŃ][\w]*)*\s+\d+\w*$', raw)
            if addr_match:
                authority = raw[:addr_match.start()].strip()
            else:
                # Also try stripping just "ul. ..." suffix
                authority = re.sub(r'\s+ul\..*$', '', raw).strip() or raw

        if not authority:
            for pattern in [
                r'(?:Zamawiaj[ąa]cy|Nazwa zamawiaj[ąa]cego|Dane zamawiaj[ąa]cego)[:\s]+([^\n]{5,150})',
                r'(?:Beneficjent)[:\s]+([^\n]{5,150})',
            ]:
                match = re.search(pattern, scraped_text)
                if match:
                    candidate = match.group(1).strip().rstrip(',.')
                    # Filter out garbage — must start with an uppercase letter and be >2 words
                    if candidate and candidate[0].isupper() and len(candidate.split()) >= 2:
                        authority = candidate
                        break

    ref_number = ez_metadata.get("ref_number", "")
    if not ref_number:
        for pattern in [
            r'(?:Numer post[ęe]powania|Numer og[łl]oszenia|Nr referencyjny|Znak sprawy)[:\s]*([\w/\-\.]+)',
        ]:
            match = re.search(pattern, scraped_text)
            if match:
                ref_number = match.group(1).strip()
                break

    deadline = ez_metadata.get("deadline", "")
    if not deadline:
        for pattern in [
            r'(?:Termin sk[łl]adania wniosk[óo]w / ofert|Termin sk[łl]adania ofert|'
            r'Termin z[łl]o[żz]enia ofert)[:\s]*'
            r'(\d{1,2}[\.\-/]\d{1,2}[\.\-/]\d{2,4}(?:\s+\d{1,2}:\d{2})?)',
            # Baza Konkurencyjności: "Termin składania ofert 2026-02-24"
            r'(?:Termin sk[łl]adania ofert)\s+'
            r'(\d{4}-\d{2}-\d{2})',
        ]:
            match = re.search(pattern, scraped_text)
            if match:
                deadline = match.group(1).strip()
                break

    # For dedicated scrapers (ezamowienia, logintrade), trust their title directly
    tender_title = scraped_title if (is_ezamowienia or is_logintrade) else ""
    if not tender_title:
        for pattern in [
            r'(?:Nazwa post[ęe]powania|Nazwa zam[óo]wienia)[:\s]*([^\n]{5,250})',
            # Baza Konkurencyjności: "Zapytanie ofertowe nr ... na ..."
            r'(Zapytanie ofertowe\s+nr\s+[^\n]{5,200})',
            r'(?:Przedmiot(?:em)?\s+zam[óo]wienia)(?:\s+jest)?[:\s]+([^\n]{5,250})',
        ]:
            match = re.search(pattern, scraped_text)
            if match:
                tender_title = match.group(1).strip()
                break
    if not tender_title:
        tender_title = scraped_title

    # Clean common portal prefixes from title
    for prefix in [
        "Baza Konkurencyjności - szczegóły ogłoszenia",
        "Platforma Zakupowa -",
        "Platforma e-Zamówienia -",
    ]:
        if tender_title and tender_title.startswith(prefix):
            tender_title = tender_title[len(prefix):].strip()
            break

    # Clean common suffixes from title
    for suffix in [
        "Generowanie pliku PDF może potrwać kilka sekund.",
    ]:
        if tender_title and tender_title.endswith(suffix):
            tender_title = tender_title[:-len(suffix)].strip().rstrip('.')

    # Update tender in DB
    async with async_session() as db:
        tender = await db.get(Tender, tender_id)
        if not tender:
            return

        tender.portal_name = detect_portal(url)
        tender.title = tender_title or tender.title
        tender.contracting_authority = authority or None
        tender.authority_type = _detect_authority_type(authority, url)
        tender.reference_number = ref_number or None
        tender.tender_text = _clean_scraped_text(scraped_text)

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
        tender.error_message = "; ".join(scrape_warnings) if scrape_warnings else None
        await db.commit()

        logger.info(
            f"[Scraper] Scraping zakończony tender_id={tender_id}: "
            f"tytuł='{tender.title}', załączników={len(downloaded_files)}"
        )

    # Generate AI summary in background (non-blocking)
    task = asyncio.create_task(_generate_ai_summary(tender_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def launch_scraping(tender_id: int) -> None:
    """Launch scraping as a background asyncio task."""
    from app.services.concurrency import acquire, release

    logger.info(f"[Scraper] Uruchamiam task scrapingu dla tender_id={tender_id}")

    async def _wrapped():
        await acquire()
        try:
            await _run_scraping(tender_id)
        except Exception:
            logger.exception(f"[Scraper] Nieobsłużony wyjątek w scrapingu tender_id={tender_id}")
        finally:
            release()

    task = asyncio.create_task(_wrapped())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
