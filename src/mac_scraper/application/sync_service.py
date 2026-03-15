"""Service applicatif — Cas d'utilisation de synchronisation d'inventaire.

Orchestre les ports (ScraperPort, ProductRepositoryPort, NotifierPort)
pour implémenter le Use Case principal : scrape → sync → route → notify.

Ce module relève de la couche Application (et non du Domaine) car il
coordonne des flux entre plusieurs ports et contient de la logique
d'orchestration — pas des invariants métier.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from mac_scraper.domain.models import Product
from mac_scraper.domain.specifications import NotificationSpecification
from mac_scraper.ports.notifier import NotifierPort
from mac_scraper.ports.repository import ProductRepositoryPort
from mac_scraper.ports.scraper import ScraperPort

logger = logging.getLogger("mac-scraper")


class SyncService:
    """Cas d'utilisation : synchronisation de l'inventaire Apple."""

    def __init__(
        self,
        *,
        repository: ProductRepositoryPort,
        scraper: ScraperPort,
        notifier: NotifierPort,
    ) -> None:
        self._repo = repository
        self._scraper = scraper
        self._notifier = notifier

    def run_check(
        self,
        *,
        is_first_run: bool,
        routing_table: Mapping[str, NotificationSpecification],
    ) -> None:
        """Exécute un cycle complet : scrape → sync → routage → notification."""
        products = self._scraper.scrape_all()

        if not products:
            logger.warning("Aucun produit trouvé — page vide ou erreur silencieuse")
            return

        new_products, back_in_stock = self._sync_products(products)

        if is_first_run:
            logger.info(
                "Premier remplissage : %d produit(s) enregistré(s) (pas de notification)",
                len(products),
            )
            return

        # ── Routage multicanal (Content-Based Routing + Pub-Sub) ─────────
        all_to_route = new_products + back_in_stock
        if not all_to_route:
            logger.info("Aucun changement détecté")
            return

        logger.info(
            "%d nouveau(x), %d retour(s) en stock → routage multicanal",
            len(new_products),
            len(back_in_stock),
        )

        routed = self._route_products(all_to_route, routing_table)
        self._notifier.notify_products(routed)

    # ── Synchronisation (calcul des diffs via le port repository) ─────────

    def _sync_products(
        self,
        scraped: list[Product],
    ) -> tuple[list[Product], list[Product]]:
        """Synchronise les produits scrapés avec le repository.

        Returns:
            (new_products, back_in_stock_products)
        """
        scraped_pns = {p.part_number for p in scraped}
        known_all = self._repo.get_all_part_numbers()
        in_stock = self._repo.get_in_stock_part_numbers()
        out_of_stock = self._repo.get_out_of_stock_part_numbers()

        new_products: list[Product] = []
        back_in_stock: list[Product] = []

        for product in scraped:
            pn = product.part_number

            if pn not in known_all:
                # ── Produit totalement inconnu → INSERT
                self._repo.upsert_product(
                    product, is_new=True, back_in_stock=False
                )
                new_products.append(product)

            elif pn in out_of_stock:
                # ── Retour en stock → UPDATE + notification
                self._repo.upsert_product(
                    product, is_new=False, back_in_stock=True
                )
                back_in_stock.append(product)

            else:
                # ── Toujours en stock → simple mise à jour
                self._repo.upsert_product(
                    product, is_new=False, back_in_stock=False
                )

        # ── Produits en base marqués en stock mais absents du scrape → hors stock
        disappeared = in_stock - scraped_pns
        if disappeared:
            self._repo.mark_out_of_stock(disappeared)
            logger.info("  → %d produit(s) sorti(s) du stock", len(disappeared))

        return new_products, back_in_stock

    # ── Routage multicanal ────────────────────────────────────────────────

    @staticmethod
    def _route_products(
        products: list[Product],
        routing_table: Mapping[str, NotificationSpecification],
    ) -> dict[str, list[Product]]:
        """Multiplexe les produits vers les canaux de la table de routage.

        Un produit peut apparaître dans 0, 1 ou N vecteurs de sortie.
        L'évaluation est purement fonctionnelle.
        """
        if not routing_table:
            return {}

        routed: dict[str, list[Product]] = {topic: [] for topic in routing_table}

        for product in products:
            for topic, spec in routing_table.items():
                if spec.is_satisfied_by(product):
                    routed[topic].append(product)

        # Purger les canaux vides
        routed = {topic: prods for topic, prods in routed.items() if prods}

        if routed:
            for topic, prods in routed.items():
                logger.info("  Routage [%s] : %d produit(s)", topic, len(prods))
        else:
            logger.info("  Routage : aucun produit ne correspond à un canal")

        return routed
