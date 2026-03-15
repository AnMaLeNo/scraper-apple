"""Tests unitaires pour le Specification Pattern + routage multicanal."""

from __future__ import annotations

import json
from pathlib import Path

from mac_scraper.domain.models import Product
from mac_scraper.domain.specifications import (
    AndSpec,
    MaxPriceSpec,
    NotSpec,
    OrSpec,
    PartNumberSpec,
    TitleContainsSpec,
    build_spec_from_config,
)
from mac_scraper.config import load_routing_table

# ── Constantes (instances Product pour tests sans fixtures) ──────────────────

CHEAP_MACBOOK_AIR = Product(
    part_number="FQKX2FN/A",
    title="MacBook Air 13 pouces reconditionné avec puce Apple M2",
    price=1029.00,
    url="https://www.apple.com/fr/shop/product/FQKX2FN/A",
)

EXPENSIVE_MACBOOK_PRO = Product(
    part_number="FQ7Y2FN/A",
    title="MacBook Pro 16 pouces reconditionné avec puce Apple M3 Max",
    price=3499.00,
    url="https://www.apple.com/fr/shop/product/FQ7Y2FN/A",
)

IMAC = Product(
    part_number="FMXN3FN/A",
    title="iMac 24 pouces reconditionné avec puce Apple M3",
    price=1349.00,
    url="https://www.apple.com/fr/shop/product/FMXN3FN/A",
)

PRODUCT_NO_PRICE = Product(
    part_number="FZZZ0FN/A",
    title="MacBook Air avec prix inconnu",
    price=None,
    url="",
)


# ── MaxPriceSpec ──────────────────────────────────────────────────────────────


class TestMaxPriceSpec:
    def test_satisfied(self) -> None:
        spec = MaxPriceSpec(2000)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_not_satisfied(self) -> None:
        spec = MaxPriceSpec(2000)
        assert spec.is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is False

    def test_boundary_equal(self) -> None:
        spec = MaxPriceSpec(1029.00)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_none_price_rejected(self) -> None:
        spec = MaxPriceSpec(5000)
        assert spec.is_satisfied_by(PRODUCT_NO_PRICE) is False


# ── TitleContainsSpec ─────────────────────────────────────────────────────────


class TestTitleContainsSpec:
    def test_case_insensitive_match(self) -> None:
        spec = TitleContainsSpec("macbook air")
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_no_match(self) -> None:
        spec = TitleContainsSpec("Mac Studio")
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is False

    def test_case_sensitive_no_match(self) -> None:
        spec = TitleContainsSpec("macbook air", case_sensitive=True)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is False

    def test_case_sensitive_match(self) -> None:
        spec = TitleContainsSpec("MacBook Air", case_sensitive=True)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True


# ── PartNumberSpec ────────────────────────────────────────────────────────────


class TestPartNumberSpec:
    def test_exact_match(self) -> None:
        spec = PartNumberSpec(["FQKX2FN/A"])
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_glob_match(self) -> None:
        spec = PartNumberSpec(["FQKX*"])
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_no_match(self) -> None:
        spec = PartNumberSpec(["ZZZZ*"])
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is False

    def test_multiple_patterns(self) -> None:
        spec = PartNumberSpec(["ZZZZ*", "FQKX*"])
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True


# ── Composite (AND / OR / NOT) ────────────────────────────────────────────────


class TestCompositeSpecs:
    def test_and_both_satisfied(self) -> None:
        spec = AndSpec(MaxPriceSpec(2000), TitleContainsSpec("MacBook Air"))
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_and_one_fails(self) -> None:
        spec = AndSpec(MaxPriceSpec(500), TitleContainsSpec("MacBook Air"))
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is False

    def test_or_one_satisfied(self) -> None:
        spec = OrSpec(MaxPriceSpec(500), TitleContainsSpec("MacBook Air"))
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_or_none_satisfied(self) -> None:
        spec = OrSpec(MaxPriceSpec(500), TitleContainsSpec("Mac Studio"))
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is False

    def test_not_inverts(self) -> None:
        spec = NotSpec(MaxPriceSpec(2000))
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is False
        assert spec.is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is True

    def test_operator_and(self) -> None:
        spec = MaxPriceSpec(2000) & TitleContainsSpec("MacBook Air")
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True
        assert spec.is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is False

    def test_operator_or(self) -> None:
        spec = MaxPriceSpec(500) | TitleContainsSpec("MacBook Air")
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_operator_not(self) -> None:
        spec = ~MaxPriceSpec(2000)
        assert spec.is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is True


# ── build_spec_from_config ────────────────────────────────────────────────────


class TestBuildSpecFromConfig:
    def test_simple_max_price(self) -> None:
        config: dict[str, object] = {"type": "max_price", "value": 2000}
        spec = build_spec_from_config(config)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True
        assert spec.is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is False

    def test_nested_tree(self) -> None:
        config: dict[str, object] = {
            "operator": "and",
            "rules": [
                {"type": "max_price", "value": 2000},
                {
                    "operator": "or",
                    "rules": [
                        {"type": "title_contains", "value": "MacBook Pro"},
                        {"type": "title_contains", "value": "MacBook Air"},
                    ],
                },
            ],
        }
        spec = build_spec_from_config(config)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True
        assert spec.is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is False
        assert spec.is_satisfied_by(IMAC) is False

    def test_not_operator(self) -> None:
        config: dict[str, object] = {
            "operator": "not",
            "rules": [{"type": "title_contains", "value": "iMac"}],
        }
        spec = build_spec_from_config(config)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True
        assert spec.is_satisfied_by(IMAC) is False

    def test_part_number_list(self) -> None:
        config: dict[str, object] = {"type": "part_number", "value": ["FQKX*", "FQ7*"]}
        spec = build_spec_from_config(config)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True
        assert spec.is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is True
        assert spec.is_satisfied_by(IMAC) is False


# ── load_routing_table (table de routage multicanal) ─────────────────────────


class TestLoadRoutingTable:
    def test_empty_object_returns_empty_dict(self, tmp_path: Path) -> None:
        f = tmp_path / "rules.json"
        f.write_text("{}")
        assert load_routing_table(str(f)) == {}

    def test_empty_file_returns_empty_dict(self, tmp_path: Path) -> None:
        f = tmp_path / "rules.json"
        f.write_text("")
        assert load_routing_table(str(f)) == {}

    def test_missing_file_returns_empty_dict(self, tmp_path: Path) -> None:
        assert load_routing_table(str(tmp_path / "nope.json")) == {}

    def test_multichannel_rules(self, tmp_path: Path) -> None:
        config = {
            "topic_budget": {"type": "max_price", "value": 1200},
            "topic_pro": {"type": "title_contains", "value": "MacBook Pro"},
        }
        f = tmp_path / "rules.json"
        f.write_text(json.dumps(config))
        table = load_routing_table(str(f))
        assert len(table) == 2
        assert "topic_budget" in table
        assert "topic_pro" in table
        assert table["topic_budget"].is_satisfied_by(CHEAP_MACBOOK_AIR) is True
        assert table["topic_budget"].is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is False
        assert table["topic_pro"].is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is True
        assert table["topic_pro"].is_satisfied_by(IMAC) is False
