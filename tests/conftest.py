"""Fixtures partagées pour les tests."""

from __future__ import annotations

import pytest

from mac_scraper.domain.models import Product


@pytest.fixture()
def cheap_macbook_air() -> Product:
    return Product(
        part_number="FQKX2FN/A",
        title="MacBook Air 13 pouces reconditionné avec puce Apple M2",
        price=1029.00,
        url="https://www.apple.com/fr/shop/product/FQKX2FN/A",
    )


@pytest.fixture()
def expensive_macbook_pro() -> Product:
    return Product(
        part_number="FQ7Y2FN/A",
        title="MacBook Pro 16 pouces reconditionné avec puce Apple M3 Max",
        price=3499.00,
        url="https://www.apple.com/fr/shop/product/FQ7Y2FN/A",
    )


@pytest.fixture()
def imac() -> Product:
    return Product(
        part_number="FMXN3FN/A",
        title="iMac 24 pouces reconditionné avec puce Apple M3",
        price=1349.00,
        url="https://www.apple.com/fr/shop/product/FMXN3FN/A",
    )


@pytest.fixture()
def product_no_price() -> Product:
    return Product(
        part_number="FZZZ0FN/A",
        title="MacBook Air avec prix inconnu",
        price=None,
        url="",
    )


@pytest.fixture()
def all_products(
    cheap_macbook_air: Product,
    expensive_macbook_pro: Product,
    imac: Product,
    product_no_price: Product,
) -> list[Product]:
    return [cheap_macbook_air, expensive_macbook_pro, imac, product_no_price]
