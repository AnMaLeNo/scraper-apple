"""Adaptateur infrastructure — Scraping Apple Refurbished.

Implémente ScraperPort. Responsable du Data Mapping :
les données brutes JSON sont converties en entités Product.
"""

from __future__ import annotations

import json
import logging
import re

import requests

from mac_scraper.domain.exceptions import (
    ScrapingError,
    ScrapingParsingError,
    ScrapingTimeoutError,
)
from mac_scraper.domain.models import Product
from mac_scraper.ports.scraper import ScraperPort

logger = logging.getLogger("mac-scraper")

# ─── User-Agent réaliste ─────────────────────────────────────────────────────
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.5 Safari/605.1.15"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class AppleScraper(ScraperPort):
    """Récupère l'inventaire Apple Reconditionnés via HTTP + JSON embarqué."""

    def __init__(
        self,
        *,
        base_url: str,
        product_base_url: str,
        scrape_paths: list[str],
    ) -> None:
        self._base_url = base_url
        self._product_base_url = product_base_url
        self._scrape_paths = scrape_paths

    def scrape_all(self) -> list[Product]:
        """Scrape toutes les pages configurées et déduplique par part_number."""
        paths = self._scrape_paths if self._scrape_paths else [""]
        seen: set[str] = set()
        all_products: list[Product] = []

        for path in paths:
            products = self._scrape_page(path)
            for p in products:
                if p.part_number not in seen:
                    seen.add(p.part_number)
                    all_products.append(p)

        logger.info("Total unique : %d produit(s)", len(all_products))
        return all_products

    def _scrape_page(self, path: str = "") -> list[Product]:
        """Scrape une page et mappe les données brutes vers des entités Product."""
        url = f"{self._base_url}/{path}".rstrip("/")
        logger.info("Scraping %s", url)

        try:
            resp = requests.get(url, headers=_HTTP_HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.Timeout as e:
            raise ScrapingTimeoutError(f"Timeout lors du scraping de {url}") from e
        except requests.RequestException as e:
            raise ScrapingError(f"Erreur HTTP lors du scraping de {url}: {e}") from e

        # ── Extraction du JSON embarqué ──────────────────────────────────
        match = re.search(
            r"window\.REFURB_GRID_BOOTSTRAP\s*=\s*({.*?});\s*</script>",
            resp.text,
            re.DOTALL,
        )
        if not match:
            raise ScrapingParsingError(
                f"JSON REFURB_GRID_BOOTSTRAP introuvable dans {url}"
            )

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            raise ScrapingParsingError(
                f"JSON invalide dans {url}: {e}"
            ) from e

        tiles: list[dict[str, object]] = data.get("tiles", [])

        # ── Data Mapping : dict brut → Product ──────────────────────────
        products: list[Product] = []
        for tile in tiles:
            part_number = str(tile.get("partNumber", "")).strip()
            if not part_number:
                continue

            title = str(tile.get("title", "")).strip()

            price_info = tile.get("price", {})
            raw_price: float | None = None
            if isinstance(price_info, dict):
                current_price = price_info.get("currentPrice", {})
                if isinstance(current_price, dict):
                    raw_amount = current_price.get("raw_amount")
                    raw_price = float(raw_amount) if raw_amount is not None else None

            url_path = str(tile.get("productDetailsUrl", ""))
            url_path_clean = url_path.split("?")[0] if url_path else ""
            product_url = (
                f"{self._product_base_url}{url_path_clean}" if url_path_clean else ""
            )

            products.append(
                Product(
                    part_number=part_number,
                    title=title,
                    price=raw_price,
                    url=product_url,
                )
            )

        logger.info("  → %d produit(s) trouvé(s)", len(products))
        return products
