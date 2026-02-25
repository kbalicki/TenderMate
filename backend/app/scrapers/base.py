"""Portal detection utilities for scraper module.

The actual scraping is delegated to the external microservice
(scraper.tools.k4.pl). This module retains portal detection utilities.
"""

# Known Polish procurement portal domains for URL validation
KNOWN_DOMAINS = [
    "bazakonkurencyjnosci.funduszeeuropejskie.gov.pl",
    "oneplace.marketplanet.pl",
    "platformazakupowa.pl",
    "platformaofertowa.pl",
    "platforma.eb2b.com.pl",
    "e-propublico.pl",
    "ted.europa.eu",
    "logintrade.net",
    "platformazakupowa.logintrade.pl",
    "ezamowienia.gov.pl",
    "swpp2.gkpge.pl",
    "josephine.proebiz.com",
    "zakupy.arp.pl",
]


def detect_portal(url: str) -> str | None:
    """Try to identify the portal name from a URL."""
    url_lower = url.lower()
    portal_names = {
        "bazakonkurencyjnosci": "Baza Konkurencyjności",
        "ezamowienia.gov.pl": "e-Zamówienia",
        "platformazakupowa.pl": "platformazakupowa.pl",
        "platformaofertowa.pl": "Platforma Ofertowa",
        "eb2b.com.pl": "eB2B",
        "e-propublico.pl": "e-ProPublico",
        "ted.europa.eu": "TED Europa",
        "logintrade": "Logintrade",
        "marketplanet": "Marketplanet OnePlace",
        "swpp2.gkpge.pl": "System Zakupowy GK PGE",
        "josephine.proebiz": "Josephine",
        "zakupy.arp.pl": "ARP Zakupy",
    }
    for domain_part, name in portal_names.items():
        if domain_part in url_lower:
            return name
    return None


def is_known_portal(url: str) -> bool:
    """Quick check if URL belongs to any known procurement portal."""
    return any(domain in url.lower() for domain in KNOWN_DOMAINS)
