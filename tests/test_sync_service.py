"""Tests unitaires du SyncService avec stubs in-memory.

Aucune connexion TCP, aucun appel disque — exécution 100% en RAM.
"""

from __future__ import annotations

import copy

from mac_scraper.application.sync_service import SyncService
from mac_scraper.domain.models import Product
from mac_scraper.domain.specifications import MaxPriceSpec, TitleContainsSpec
from mac_scraper.ports.notifier import NotifierPort
from mac_scraper.ports.repository import ProductRepositoryPort
from mac_scraper.ports.scraper import ScraperPort


# ── Stubs / Mocks ─────────────────────────────────────────────────────────────


class StubScraper(ScraperPort):
    """Retourne des données prédéfinies."""

    def __init__(self, products: list[Product]) -> None:
        self._products = products

    def scrape_all(self) -> list[Product]:
        return list(self._products)


class InMemoryRepository(ProductRepositoryPort):
    """Repository in-memory implémentant le contrat du port."""

    def __init__(self) -> None:
        self._products: dict[str, tuple[Product, bool]] = {}  # pn → (product, in_stock)

    def init(self) -> None:
        pass  # Rien à initialiser en mémoire

    def get_all_part_numbers(self) -> set[str]:
        return set(self._products.keys())

    def get_in_stock_part_numbers(self) -> set[str]:
        return {pn for pn, (_, in_stock) in self._products.items() if in_stock}

    def get_out_of_stock_part_numbers(self) -> set[str]:
        return {pn for pn, (_, in_stock) in self._products.items() if not in_stock}

    def upsert_product(
        self,
        product: Product,
        *,
        is_new: bool,
        back_in_stock: bool,
    ) -> None:
        self._products[product.part_number] = (product, True)

    def mark_out_of_stock(self, part_numbers: set[str]) -> None:
        for pn in part_numbers:
            if pn in self._products:
                prod, _ = self._products[pn]
                self._products[pn] = (prod, False)

    # ── Helpers pour assertions ───────────────────────────────────────────

    def is_in_stock(self, part_number: str) -> bool:
        return self._products.get(part_number, (None, False))[1]


class SpyNotifier(NotifierPort):
    """Capture les appels de notification pour assertions."""

    def __init__(self) -> None:
        self.product_calls: list[dict[str, list[Product]]] = []
        self.failure_calls: list[tuple[str, int]] = []
        self.lifecycle_calls: list[str] = []

    def notify_products(self, routed: dict[str, list[Product]]) -> None:
        self.product_calls.append(copy.deepcopy(routed))

    def notify_failure(self, error: str, consecutive: int) -> None:
        self.failure_calls.append((error, consecutive))

    def notify_lifecycle(self, event: str) -> None:
        self.lifecycle_calls.append(event)


# ── Fixtures ──────────────────────────────────────────────────────────────────

MACBOOK = Product(
    part_number="FQKX2FN/A",
    title="MacBook Air 13 pouces reconditionné avec puce Apple M2",
    price=1029.00,
    url="https://www.apple.com/fr/shop/product/FQKX2FN/A",
)

MACBOOK_PRO = Product(
    part_number="FQ7Y2FN/A",
    title="MacBook Pro 16 pouces reconditionné avec puce Apple M3 Max",
    price=3499.00,
    url="https://www.apple.com/fr/shop/product/FQ7Y2FN/A",
)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestSyncServiceFirstRun:
    """Premier run — les produits sont enregistrés mais pas de notification."""

    def test_first_run_no_notification(self) -> None:
        repo = InMemoryRepository()
        scraper = StubScraper([MACBOOK, MACBOOK_PRO])
        notifier = SpyNotifier()
        service = SyncService(repository=repo, scraper=scraper, notifier=notifier)

        service.run_check(is_first_run=True, routing_table={})

        assert len(repo.get_all_part_numbers()) == 2
        assert notifier.product_calls == []


class TestSyncServiceNewProducts:
    """Nouveau produit détecté après le premier run."""

    def test_new_product_notified(self) -> None:
        repo = InMemoryRepository()
        scraper = StubScraper([MACBOOK])
        notifier = SpyNotifier()
        service = SyncService(repository=repo, scraper=scraper, notifier=notifier)

        # Premier run : enregistre MACBOOK, pas de notification
        service.run_check(is_first_run=True, routing_table={})

        # Deuxième run : MACBOOK_PRO apparaît
        scraper._products = [MACBOOK, MACBOOK_PRO]
        routing_table = {"topic_all": MaxPriceSpec(99999)}
        service.run_check(is_first_run=False, routing_table=routing_table)

        assert len(notifier.product_calls) == 1
        routed = notifier.product_calls[0]
        assert "topic_all" in routed
        notified_pns = {p.part_number for p in routed["topic_all"]}
        assert "FQ7Y2FN/A" in notified_pns


class TestSyncServiceBackInStock:
    """Un produit sorti puis revenu en stock."""

    def test_back_in_stock_notified(self) -> None:
        repo = InMemoryRepository()
        notifier = SpyNotifier()

        # Run 1 : MACBOOK et MACBOOK_PRO en stock
        scraper = StubScraper([MACBOOK, MACBOOK_PRO])
        service = SyncService(repository=repo, scraper=scraper, notifier=notifier)
        service.run_check(is_first_run=True, routing_table={})

        # Run 2 : MACBOOK_PRO disparaît → marqué hors stock
        scraper._products = [MACBOOK]
        service.run_check(is_first_run=False, routing_table={})
        assert not repo.is_in_stock("FQ7Y2FN/A")

        # Run 3 : MACBOOK_PRO revient → back in stock, notification
        scraper._products = [MACBOOK, MACBOOK_PRO]
        routing_table = {"topic_all": MaxPriceSpec(99999)}
        service.run_check(is_first_run=False, routing_table=routing_table)

        assert repo.is_in_stock("FQ7Y2FN/A")
        assert len(notifier.product_calls) == 1
        routed = notifier.product_calls[0]
        assert "FQ7Y2FN/A" in {p.part_number for p in routed["topic_all"]}


class TestSyncServiceDisappeared:
    """Un produit disparaît du scrape → marqué hors stock."""

    def test_disappeared_marked_out_of_stock(self) -> None:
        repo = InMemoryRepository()
        notifier = SpyNotifier()

        scraper = StubScraper([MACBOOK, MACBOOK_PRO])
        service = SyncService(repository=repo, scraper=scraper, notifier=notifier)
        service.run_check(is_first_run=True, routing_table={})

        # MACBOOK_PRO disparaît
        scraper._products = [MACBOOK]
        service.run_check(is_first_run=False, routing_table={})

        assert repo.is_in_stock("FQKX2FN/A")
        assert not repo.is_in_stock("FQ7Y2FN/A")


class TestSyncServiceRouting:
    """Routage multicanal avec spécifications."""

    def test_multichannel_routing(self) -> None:
        repo = InMemoryRepository()
        notifier = SpyNotifier()

        # Premier run vide
        scraper = StubScraper([])
        service = SyncService(repository=repo, scraper=scraper, notifier=notifier)

        # Deuxième run avec produits
        scraper._products = [MACBOOK, MACBOOK_PRO]
        routing_table = {
            "budget": MaxPriceSpec(1500),
            "pro": TitleContainsSpec("MacBook Pro"),
        }
        service.run_check(is_first_run=False, routing_table=routing_table)

        assert len(notifier.product_calls) == 1
        routed = notifier.product_calls[0]

        # MACBOOK → budget uniquement
        assert MACBOOK in routed.get("budget", [])
        assert MACBOOK not in routed.get("pro", [])

        # MACBOOK_PRO → pro uniquement (prix > 1500)
        assert MACBOOK_PRO in routed.get("pro", [])
        assert MACBOOK_PRO not in routed.get("budget", [])
