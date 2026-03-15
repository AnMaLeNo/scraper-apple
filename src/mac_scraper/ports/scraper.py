"""Port abstrait — Scraping de l'inventaire produit."""

from __future__ import annotations

from abc import ABC, abstractmethod

from mac_scraper.domain.models import Product


class ScraperPort(ABC):
    """Interface abstraite pour récupérer l'inventaire distant."""

    @abstractmethod
    def scrape_all(self) -> list[Product]:
        """Scrape toutes les pages configurées et déduplique par part_number.

        Raises:
            ScrapingError: en cas d'échec réseau ou de parsing.
        """
