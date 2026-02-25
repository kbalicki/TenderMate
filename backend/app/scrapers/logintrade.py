"""Dedicated scraper for logintrade.net procurement portals.

Supports two URL formats:
- zapytania_email: {company}.logintrade.net/zapytania_email,{id},{hash}.html
- portal: {company}.logintrade.net/portal,szczegolyZapytaniaOfertowe,{hash}.html
"""

import logging
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _base_url(url: str) -> str:
    """Extract base URL (scheme + host) from a full URL."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _clean_text(text: str) -> str:
    """Collapse whitespace and strip."""
    return re.sub(r'\s+', ' ', text).strip()


def _detect_format(url: str) -> str:
    """Detect which logintrade URL format we're dealing with."""
    if "zapytania_email" in url:
        return "zapytania_email"
    if "szczegolyZapytaniaOfertowe" in url or "portal," in url:
        return "portal"
    return "unknown"


def _parse_zapytania_email(soup: BeautifulSoup, base: str) -> dict:
    """Parse the zapytania_email page format.

    HTML structure (observed):
    - <h1>: "ZAPYTANIE OFERTOWE NR ...", section headers (Treść, Produkty, etc.)
    - <h2>: Company name (authority)
    - <h3>: Address, NIP, contact person, email
    """
    title = ""
    authority = ""
    deadline = ""
    ref_number = ""
    text_parts: list[str] = []

    # Title — <h1> containing "ZAPYTANIE OFERTOWE" or similar
    for h1 in soup.find_all("h1"):
        h1_text = _clean_text(h1.get_text())
        if "zapytanie" in h1_text.lower() and ("nr" in h1_text.lower() or "ofertowe" in h1_text.lower()):
            title = h1_text
            break

    # If no ZAPYTANIE title, try "Tytuł zapytania" section content
    if not title:
        for h1 in soup.find_all("h1"):
            if "tytuł zapytania" in _clean_text(h1.get_text()).lower():
                # The title content is in siblings after this h1
                for sib in h1.find_next_siblings():
                    if sib.name and sib.name.startswith("h"):
                        break
                    sib_text = _clean_text(sib.get_text())
                    if sib_text:
                        title = sib_text
                        break
                break

    # Authority — <h2> tag (company name)
    h2_tag = soup.find("h2")
    if h2_tag:
        authority = _clean_text(h2_tag.get_text())

    # Authority details — <h3> tags: address, NIP, contact
    h3_tags = soup.find_all("h3")
    authority_parts = []
    if authority:
        authority_parts.append(authority)
    for h3 in h3_tags:
        h3_text = _clean_text(h3.get_text())
        if h3_text:
            authority_parts.append(h3_text)
    if authority_parts:
        text_parts.append("Zamawiający:")
        text_parts.extend(f"  {p}" for p in authority_parts)
        text_parts.append("")

    # Deadline — look for "Termin składania ofert"
    page_text = soup.get_text()
    for pattern in [
        r'Termin sk[łl]adania ofert[^0-9]*(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2})',
        r'Termin sk[łl]adania ofert[^0-9]*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})',
    ]:
        deadline_match = re.search(pattern, page_text)
        if deadline_match:
            deadline = deadline_match.group(1)
            break

    # Reference number — from title
    if title:
        ref_match = re.search(r'(?:NR|Nr|nr)[.\s]+([A-Z0-9][\w/\-\.]+)', title)
        if ref_match:
            ref_number = ref_match.group(1)

    # Content sections — <h1> tags mark sections: Tytuł, Treść, Produkty, Dodatkowe warunki
    section_keywords = ["tytuł zapytania", "treść zapytania", "dodatkowe warunki"]
    for h1 in soup.find_all("h1"):
        h1_text = _clean_text(h1.get_text())
        h1_lower = h1_text.lower()
        if any(kw in h1_lower for kw in section_keywords):
            text_parts.append(f"\n{h1_text}")
            for sibling in h1.find_next_siblings():
                if sibling.name == "h1":
                    break
                sib_text = _clean_text(sibling.get_text())
                if sib_text:
                    text_parts.append(sib_text)
            text_parts.append("")

    # Products table
    for table in soup.find_all("table"):
        headers = [_clean_text(th.get_text()) for th in table.find_all("th")]
        if any("nazwa" in h.lower() for h in headers if h):
            text_parts.append("Produkty / pozycje:")
            for row in table.find_all("tr"):
                cells = [_clean_text(td.get_text()) for td in row.find_all("td")]
                if cells and any(c for c in cells):
                    text_parts.append("  " + " | ".join(c for c in cells if c))
            text_parts.append("")

    # Questions section — "Pytania do postępowania"
    for h1 in soup.find_all("h1"):
        h1_text = _clean_text(h1.get_text())
        if "pytania do" in h1_text.lower():
            text_parts.append(f"\n{h1_text}")
            for sibling in h1.find_next_siblings():
                if sibling.name == "h1":
                    break
                sib_text = _clean_text(sibling.get_text())
                if sib_text:
                    text_parts.append(sib_text)
            text_parts.append("")

    # Attachments
    attachments = _extract_attachments(soup, base)

    # If we didn't get much content, fall back to full page text
    content_text = "\n".join(text_parts)
    if len(content_text.strip()) < 100:
        body = soup.find("body")
        if body:
            content_text = body.get_text(separator="\n")

    return {
        "title": title,
        "text": content_text,
        "attachments": attachments,
        "metadata": {
            "authority": authority,
            "ref_number": ref_number,
            "deadline": deadline,
        },
    }


def _parse_portal(soup: BeautifulSoup, base: str) -> dict:
    """Parse the portal/szczegolyZapytaniaOfertowe page format.

    HTML structure (observed):
    - <div id="title">: tender title
    - <div class="label">: section labels (Zamawiający, Treść zapytania, Załączniki, Kryteria...)
    - <div class="dataFieldsForm infoFields">: content sections
    - Dates as plain text: "Data rozpoczęcia:", "Data zakończenia:"
    """
    title = ""
    authority = ""
    deadline = ""
    ref_number = ""
    text_parts: list[str] = []

    page_text = soup.get_text()

    # Title — <div id="title">
    title_div = soup.find(id="title")
    if title_div:
        title = _clean_text(title_div.get_text())

    if not title:
        # Fallback: <title> tag or h1/h2
        title_tag = soup.find("title")
        if title_tag:
            title = _clean_text(title_tag.get_text())
        if not title:
            for tag in ["h1", "h2"]:
                el = soup.find(tag)
                if el:
                    candidate = _clean_text(el.get_text())
                    if candidate and len(candidate) > 10:
                        title = candidate
                        break

    # Authority — find <div class="label"> "Zamawiający", then the next label div has the name
    label_divs = soup.find_all("div", class_="label")
    for i, div in enumerate(label_divs):
        div_text = _clean_text(div.get_text())
        if div_text.lower() == "zamawiający" and i + 1 < len(label_divs):
            authority = _clean_text(label_divs[i + 1].get_text())
            break

    if not authority:
        # Fallback: regex for company patterns
        authority_match = re.search(
            r'([\w\s\.\-]+(?:S\.A\.|Sp\.\s*z\s*o\.o\.|S\.A|sp\.\s*z\s*o\.o)[^\n]*)',
            page_text,
        )
        if authority_match:
            authority = _clean_text(authority_match.group(1))

    # Deadline — "Data zakończenia: YYYY-MM-DD HH:MM:SS"
    for pattern in [
        r'Data zako[ńn]czenia[:\s]+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)',
        r'Termin sk[łl]adania ofert[^0-9]*(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?)',
    ]:
        deadline_match = re.search(pattern, page_text)
        if deadline_match:
            deadline = deadline_match.group(1)
            break

    # Reference number — from title suffix (e.g. "- Z156/2065/1")
    if title:
        ref_match = re.search(r'[-–]\s*([A-Z0-9]\w*/\d+(?:/\d+)?)\s*$', title)
        if ref_match:
            ref_number = ref_match.group(1)

    # Dates info header
    dates_info = []
    for label in ["Data rozpoczęcia", "Data zakończenia", "Termin zadawania pytań"]:
        match = re.search(
            rf'{label}[^:]*[:\s]+(\d{{4}}-\d{{2}}-\d{{2}}\s+\d{{2}}:\d{{2}}(?::\d{{2}})?)',
            page_text,
        )
        if match:
            dates_info.append(f"{label}: {match.group(1)}")
    if dates_info:
        text_parts.append("\n".join(dates_info))
        text_parts.append("")

    # Content — walk through label divs to extract structured sections
    section_labels = [
        "treść zapytania", "kryteria formalne", "dodatkowe warunki formalne",
        "kryteria oceny oferty", "dodatkowe pytania do oferty",
    ]

    for div in label_divs:
        div_text = _clean_text(div.get_text())
        if div_text.lower() in section_labels:
            text_parts.append(f"\n{div_text}")
            # Collect content from next siblings until next label div
            for sib in div.find_next_siblings():
                if sib.get("class") and "label" in sib.get("class", []):
                    sib_text = _clean_text(sib.get_text()).lower()
                    if sib_text in section_labels or sib_text in ["załączniki", "waluta:", "zamawiający"]:
                        break
                sib_text = sib.get_text(separator="\n").strip()
                if sib_text:
                    text_parts.append(sib_text)
            text_parts.append("")

    # If structured extraction failed, use dataFieldsForm
    if len("\n".join(text_parts).strip()) < 100:
        content_div = soup.find("div", class_="dataFieldsForm")
        if content_div:
            text_parts = [content_div.get_text(separator="\n").strip()]

    # Authority info for text
    if authority:
        text_parts.insert(0, f"Zamawiający: {authority}\n")

    # Attachments
    attachments = _extract_attachments(soup, base)

    return {
        "title": title,
        "text": "\n".join(text_parts),
        "attachments": attachments,
        "metadata": {
            "authority": authority,
            "ref_number": ref_number,
            "deadline": deadline,
        },
    }


def _extract_attachments(soup: BeautifulSoup, base: str) -> list[dict]:
    """Extract attachment download links from the page."""
    attachments = []
    seen_urls = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        link_text = _clean_text(a_tag.get_text())

        is_document_service = "DocumentService" in href and "getAttachment" in href
        has_file_ext = bool(re.search(r'\.(pdf|xlsx?|docx?|zip|rar|7z|csv|pptx?)(\?|$)', href, re.I))

        if is_document_service or has_file_ext:
            full_url = urljoin(base + "/", href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            name = link_text or href.split("/")[-1].split("?")[0]
            # Clean up name — remove size info like "(203.16 KB)"
            name = re.sub(r'\s*\(\d+[\.,]?\d*\s*[KMG]B\)\s*$', '', name, flags=re.I)
            name = name.strip()

            if name:
                attachments.append({"url": full_url, "name": name})

    return attachments


async def scrape_tender(url: str) -> dict:
    """Main entry point: scrape a tender from logintrade.net.

    Returns a dict compatible with scraper_service expectations:
    {
        "title": str,
        "text": str,
        "attachments": [{"url": str, "name": str}],
        "metadata": {
            "authority": str,
            "ref_number": str,
            "deadline": str,
        },
    }
    """
    logger.info(f"[logintrade] Scraping: {url}")
    base = _base_url(url)
    fmt = _detect_format(url)
    logger.info(f"[logintrade] Detected format: {fmt}, base: {base}")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, timeout=30.0)
        resp.raise_for_status()
        html = resp.text

    soup = BeautifulSoup(html, "html.parser")

    if fmt == "zapytania_email":
        result = _parse_zapytania_email(soup, base)
    elif fmt == "portal":
        result = _parse_portal(soup, base)
    else:
        # Unknown format — try portal parser first, fall back to email
        result = _parse_portal(soup, base)
        if not result.get("title") and not result.get("text"):
            result = _parse_zapytania_email(soup, base)

    title = result.get("title", "")
    attachments = result.get("attachments", [])
    logger.info(
        f"[logintrade] Scraped: title='{title[:80]}', "
        f"attachments={len(attachments)}, "
        f"text_len={len(result.get('text', ''))}"
    )

    return result
