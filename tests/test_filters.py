"""Tests unitaires pour le module de filtrage (Specification Pattern + Routage Multicanal)."""

import json
from pathlib import Path

from filters import (
    AndSpec,
    MaxPriceSpec,
    NotSpec,
    OrSpec,
    PartNumberSpec,
    TitleContainsSpec,
    build_spec_from_config,
    load_filter_rules,
    route_products,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

CHEAP_MACBOOK_AIR = {
    "part_number": "FQKX2FN/A",
    "title": "MacBook Air 13 pouces reconditionné avec puce Apple M2",
    "price": 1029.00,
    "url": "https://www.apple.com/fr/shop/product/FQKX2FN/A",
}

EXPENSIVE_MACBOOK_PRO = {
    "part_number": "FQ7Y2FN/A",
    "title": "MacBook Pro 16 pouces reconditionné avec puce Apple M3 Max",
    "price": 3499.00,
    "url": "https://www.apple.com/fr/shop/product/FQ7Y2FN/A",
}

IMAC = {
    "part_number": "FMXN3FN/A",
    "title": "iMac 24 pouces reconditionné avec puce Apple M3",
    "price": 1349.00,
    "url": "https://www.apple.com/fr/shop/product/FMXN3FN/A",
}

PRODUCT_NO_PRICE = {
    "part_number": "FZZZ0FN/A",
    "title": "MacBook Air avec prix inconnu",
    "price": None,
    "url": "",
}

ALL_PRODUCTS = [CHEAP_MACBOOK_AIR, EXPENSIVE_MACBOOK_PRO, IMAC, PRODUCT_NO_PRICE]


# ── MaxPriceSpec ──────────────────────────────────────────────────────────────


class TestMaxPriceSpec:
    def test_satisfied(self):
        spec = MaxPriceSpec(2000)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_not_satisfied(self):
        spec = MaxPriceSpec(2000)
        assert spec.is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is False

    def test_boundary_equal(self):
        spec = MaxPriceSpec(1029.00)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_none_price_rejected(self):
        spec = MaxPriceSpec(5000)
        assert spec.is_satisfied_by(PRODUCT_NO_PRICE) is False


# ── TitleContainsSpec ─────────────────────────────────────────────────────────


class TestTitleContainsSpec:
    def test_case_insensitive_match(self):
        spec = TitleContainsSpec("macbook air")
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_no_match(self):
        spec = TitleContainsSpec("Mac Studio")
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is False

    def test_case_sensitive_no_match(self):
        spec = TitleContainsSpec("macbook air", case_sensitive=True)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is False

    def test_case_sensitive_match(self):
        spec = TitleContainsSpec("MacBook Air", case_sensitive=True)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True


# ── PartNumberSpec ────────────────────────────────────────────────────────────


class TestPartNumberSpec:
    def test_exact_match(self):
        spec = PartNumberSpec(["FQKX2FN/A"])
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_glob_match(self):
        spec = PartNumberSpec(["FQKX*"])
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_no_match(self):
        spec = PartNumberSpec(["ZZZZ*"])
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is False

    def test_multiple_patterns(self):
        spec = PartNumberSpec(["ZZZZ*", "FQKX*"])
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True


# ── Composite (AND / OR / NOT) ────────────────────────────────────────────────


class TestCompositeSpecs:
    def test_and_both_satisfied(self):
        spec = AndSpec(MaxPriceSpec(2000), TitleContainsSpec("MacBook Air"))
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_and_one_fails(self):
        spec = AndSpec(MaxPriceSpec(500), TitleContainsSpec("MacBook Air"))
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is False

    def test_or_one_satisfied(self):
        spec = OrSpec(MaxPriceSpec(500), TitleContainsSpec("MacBook Air"))
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_or_none_satisfied(self):
        spec = OrSpec(MaxPriceSpec(500), TitleContainsSpec("Mac Studio"))
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is False

    def test_not_inverts(self):
        spec = NotSpec(MaxPriceSpec(2000))
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is False
        assert spec.is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is True

    def test_operator_and(self):
        """Teste la surcharge __and__."""
        spec = MaxPriceSpec(2000) & TitleContainsSpec("MacBook Air")
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True
        assert spec.is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is False

    def test_operator_or(self):
        """Teste la surcharge __or__."""
        spec = MaxPriceSpec(500) | TitleContainsSpec("MacBook Air")
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True

    def test_operator_not(self):
        """Teste la surcharge __invert__."""
        spec = ~MaxPriceSpec(2000)
        assert spec.is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is True


# ── build_spec_from_config ────────────────────────────────────────────────────


class TestBuildSpecFromConfig:
    def test_simple_max_price(self):
        config = {"type": "max_price", "value": 2000}
        spec = build_spec_from_config(config)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True
        assert spec.is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is False

    def test_nested_tree(self):
        config = {
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

    def test_not_operator(self):
        config = {
            "operator": "not",
            "rules": [{"type": "title_contains", "value": "iMac"}],
        }
        spec = build_spec_from_config(config)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True
        assert spec.is_satisfied_by(IMAC) is False

    def test_part_number_list(self):
        config = {"type": "part_number", "value": ["FQKX*", "FQ7*"]}
        spec = build_spec_from_config(config)
        assert spec.is_satisfied_by(CHEAP_MACBOOK_AIR) is True
        assert spec.is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is True
        assert spec.is_satisfied_by(IMAC) is False


# ── load_filter_rules (table de routage multicanal) ──────────────────────────


class TestLoadFilterRules:
    def test_empty_object_returns_empty_dict(self, tmp_path: Path):
        f = tmp_path / "rules.json"
        f.write_text("{}")
        assert load_filter_rules(str(f)) == {}

    def test_empty_file_returns_empty_dict(self, tmp_path: Path):
        f = tmp_path / "rules.json"
        f.write_text("")
        assert load_filter_rules(str(f)) == {}

    def test_missing_file_returns_empty_dict(self, tmp_path: Path):
        assert load_filter_rules(str(tmp_path / "nope.json")) == {}

    def test_multichannel_rules(self, tmp_path: Path):
        config = {
            "topic_budget": {"type": "max_price", "value": 1200},
            "topic_pro": {"type": "title_contains", "value": "MacBook Pro"},
        }
        f = tmp_path / "rules.json"
        f.write_text(json.dumps(config))
        table = load_filter_rules(str(f))
        assert len(table) == 2
        assert "topic_budget" in table
        assert "topic_pro" in table
        # Vérifier les specs instanciées
        assert table["topic_budget"].is_satisfied_by(CHEAP_MACBOOK_AIR) is True
        assert table["topic_budget"].is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is False
        assert table["topic_pro"].is_satisfied_by(EXPENSIVE_MACBOOK_PRO) is True
        assert table["topic_pro"].is_satisfied_by(IMAC) is False


# ── route_products (routeur multicanal) ──────────────────────────────────────


class TestRouteProducts:
    def test_empty_routing_table(self):
        result = route_products(ALL_PRODUCTS, {})
        assert result == {}

    def test_empty_products(self):
        table = {"topic_a": MaxPriceSpec(2000)}
        result = route_products([], table)
        assert result == {}

    def test_single_channel(self):
        table = {"topic_budget": MaxPriceSpec(1500)}
        result = route_products(ALL_PRODUCTS, table)
        assert "topic_budget" in result
        assert CHEAP_MACBOOK_AIR in result["topic_budget"]
        assert IMAC in result["topic_budget"]
        assert EXPENSIVE_MACBOOK_PRO not in result["topic_budget"]

    def test_multi_channel_multiplexing(self):
        """Un produit peut apparaître dans plusieurs canaux."""
        table = {
            "topic_budget": MaxPriceSpec(1500),
            "topic_air": TitleContainsSpec("MacBook Air"),
        }
        result = route_products(ALL_PRODUCTS, table)
        # MacBook Air cheap → dans les deux canaux
        assert CHEAP_MACBOOK_AIR in result["topic_budget"]
        assert CHEAP_MACBOOK_AIR in result["topic_air"]
        # iMac → uniquement budget
        assert IMAC in result["topic_budget"]
        assert IMAC not in result.get("topic_air", [])
        # Pro cher → dans aucun canal
        assert EXPENSIVE_MACBOOK_PRO not in result.get("topic_budget", [])

    def test_no_match_returns_empty(self):
        table = {"topic_studio": TitleContainsSpec("Mac Studio")}
        result = route_products(ALL_PRODUCTS, table)
        assert result == {}

    def test_idempotence(self):
        """L'évaluation ne doit pas muter les dicts produit."""
        import copy
        products_copy = copy.deepcopy(ALL_PRODUCTS)
        table = {"t1": MaxPriceSpec(1500), "t2": TitleContainsSpec("MacBook")}
        route_products(ALL_PRODUCTS, table)
        assert ALL_PRODUCTS == products_copy
