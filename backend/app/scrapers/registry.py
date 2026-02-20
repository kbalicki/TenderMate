import re

from app.scrapers.base import BaseScraper

# Import scrapers as they are implemented
# from app.scrapers.bazakonkurencyjnosci import BazaKonkurencyjnosciScraper

_SCRAPERS: list[type[BaseScraper]] = [
    # BazaKonkurencyjnosciScraper,
    # Add more as implemented
]


def get_scraper_for_url(url: str) -> BaseScraper | None:
    for scraper_cls in _SCRAPERS:
        for pattern in scraper_cls.URL_PATTERNS:
            if re.search(pattern, url):
                return scraper_cls()
    return None


def detect_portal(url: str) -> str | None:
    scraper = get_scraper_for_url(url)
    return scraper.PORTAL_NAME if scraper else None


# Quick URL validation: check if URL belongs to any known portal domain
KNOWN_DOMAINS = [
    "bazakonkurencyjnosci.funduszeeuropejskie.gov.pl",
    "oneplace.marketplanet.pl",
    "platformazakupowa.pl",
    "platformaofertowa.pl",
    "platforma.eb2b.com.pl",
    "e-propublico.pl",
    "ted.europa.eu",
    "platformazakupowa.logintrade.pl",
    "ezamowienia.gov.pl",
]


def is_known_portal(url: str) -> bool:
    return any(domain in url for domain in KNOWN_DOMAINS)
