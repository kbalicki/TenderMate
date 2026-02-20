from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import Page


@dataclass
class ScrapedTender:
    title: str
    contracting_authority: str | None = None
    reference_number: str | None = None
    submission_deadline: str | None = None  # ISO format
    full_text_markdown: str = ""
    raw_html: str = ""
    attachment_urls: list[str] = field(default_factory=list)


class BaseScraper(ABC):
    """One implementation per supported portal."""

    PORTAL_NAME: str = ""
    URL_PATTERNS: list[str] = []

    @abstractmethod
    async def scrape(self, url: str, page: Page, output_dir: Path) -> ScrapedTender:
        ...

    async def download_attachments(
        self, urls: list[str], output_dir: Path, page: Page
    ) -> list[Path]:
        """Download files to output_dir/attachments/."""
        att_dir = output_dir / "attachments"
        att_dir.mkdir(exist_ok=True)
        downloaded = []

        for url in urls:
            try:
                response = await page.request.get(url)
                # Extract filename from Content-Disposition or URL
                cd = response.headers.get("content-disposition", "")
                if "filename=" in cd:
                    filename = cd.split("filename=")[-1].strip('" ')
                else:
                    filename = url.split("/")[-1].split("?")[0] or "attachment"

                file_path = att_dir / filename
                file_path.write_bytes(await response.body())
                downloaded.append(file_path)
            except Exception:
                continue  # Log and skip failed downloads

        return downloaded
