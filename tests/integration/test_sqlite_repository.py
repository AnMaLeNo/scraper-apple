"""Tests de contrat d'infrastructure — SqliteRepository.

Instancie un adaptateur SqliteRepository contre une BDD éphémère en RAM
pour valider que les opérations SQL remplissent le contrat défini par
ProductRepositoryPort.
"""

from __future__ import annotations

import uuid

from mac_scraper.adapters.sqlite_repository import SqliteRepository
from mac_scraper.domain.models import Product

# ── Fixtures ──────────────────────────────────────────────────────────────────

PRODUCT_A = Product(
    part_number="FQKX2FN/A",
    title="MacBook Air 13 pouces",
    price=1029.00,
    url="https://www.apple.com/fr/shop/product/FQKX2FN/A",
)

PRODUCT_B = Product(
    part_number="FQ7Y2FN/A",
    title="MacBook Pro 16 pouces",
    price=3499.00,
    url="https://www.apple.com/fr/shop/product/FQ7Y2FN/A",
)


def _make_repo() -> SqliteRepository:
    """Crée un repository pointant vers une BDD en mémoire isolée par test."""
    db_name = uuid.uuid4().hex
    repo = SqliteRepository(db_path=f"file:{db_name}?mode=memory&cache=shared")
    repo.init()
    return repo


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestSqliteRepositoryInit:
    """Validation de l'initialisation du schéma."""

    def test_init_creates_table(self) -> None:
        repo = _make_repo()
        assert repo.get_all_part_numbers() == set()

    def test_init_idempotent(self) -> None:
        repo = _make_repo()
        repo.init()
        assert repo.get_all_part_numbers() == set()


class TestSqliteRepositoryUpsert:
    """Validation des opérations d'upsertion."""

    def test_insert_new_product(self) -> None:
        repo = _make_repo()
        repo.upsert_product(PRODUCT_A, is_new=True, back_in_stock=False)

        assert "FQKX2FN/A" in repo.get_all_part_numbers()
        assert "FQKX2FN/A" in repo.get_in_stock_part_numbers()
        assert "FQKX2FN/A" not in repo.get_out_of_stock_part_numbers()

    def test_insert_multiple_products(self) -> None:
        repo = _make_repo()
        repo.upsert_product(PRODUCT_A, is_new=True, back_in_stock=False)
        repo.upsert_product(PRODUCT_B, is_new=True, back_in_stock=False)

        all_pns = repo.get_all_part_numbers()
        assert len(all_pns) == 2
        assert "FQKX2FN/A" in all_pns
        assert "FQ7Y2FN/A" in all_pns

    def test_update_existing_product(self) -> None:
        repo = _make_repo()
        repo.upsert_product(PRODUCT_A, is_new=True, back_in_stock=False)

        updated = Product(
            part_number="FQKX2FN/A",
            title="MacBook Air 13 pouces — Mis à jour",
            price=999.00,
            url="https://www.apple.com/fr/shop/product/FQKX2FN/A",
        )
        repo.upsert_product(updated, is_new=False, back_in_stock=False)

        assert len(repo.get_all_part_numbers()) == 1
        assert "FQKX2FN/A" in repo.get_in_stock_part_numbers()


class TestSqliteRepositoryMarkOutOfStock:
    """Validation du marquage hors stock."""

    def test_mark_single_out_of_stock(self) -> None:
        repo = _make_repo()
        repo.upsert_product(PRODUCT_A, is_new=True, back_in_stock=False)
        repo.upsert_product(PRODUCT_B, is_new=True, back_in_stock=False)

        repo.mark_out_of_stock({"FQKX2FN/A"})

        assert "FQKX2FN/A" in repo.get_out_of_stock_part_numbers()
        assert "FQKX2FN/A" not in repo.get_in_stock_part_numbers()
        assert "FQ7Y2FN/A" in repo.get_in_stock_part_numbers()

    def test_mark_multiple_out_of_stock(self) -> None:
        repo = _make_repo()
        repo.upsert_product(PRODUCT_A, is_new=True, back_in_stock=False)
        repo.upsert_product(PRODUCT_B, is_new=True, back_in_stock=False)

        repo.mark_out_of_stock({"FQKX2FN/A", "FQ7Y2FN/A"})

        assert repo.get_in_stock_part_numbers() == set()
        assert len(repo.get_out_of_stock_part_numbers()) == 2

    def test_mark_empty_set_is_noop(self) -> None:
        repo = _make_repo()
        repo.upsert_product(PRODUCT_A, is_new=True, back_in_stock=False)
        repo.mark_out_of_stock(set())
        assert "FQKX2FN/A" in repo.get_in_stock_part_numbers()


class TestSqliteRepositoryBackInStock:
    """Validation du retour en stock."""

    def test_back_in_stock(self) -> None:
        repo = _make_repo()
        repo.upsert_product(PRODUCT_A, is_new=True, back_in_stock=False)
        repo.mark_out_of_stock({"FQKX2FN/A"})

        assert "FQKX2FN/A" in repo.get_out_of_stock_part_numbers()

        repo.upsert_product(PRODUCT_A, is_new=False, back_in_stock=True)

        assert "FQKX2FN/A" in repo.get_in_stock_part_numbers()
        assert "FQKX2FN/A" not in repo.get_out_of_stock_part_numbers()
