"""
Filtrage des notifications — Specification Pattern + Content-Based Routing.

Ce module implémente un arbre d'évaluation conditionnelle pour filtrer
les produits avant notification. Les règles sont externalisées dans un
fichier JSON désérialisé au démarrage de l'application.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from fnmatch import fnmatch
from pathlib import Path

logger = logging.getLogger("mac-scraper")

# ────────────────────────────────────────────────────────────────────────────────
#  SPECIFICATION PATTERN — Interface abstraite
# ────────────────────────────────────────────────────────────────────────────────


class NotificationSpecification(ABC):
    """Interface abstraite déclarant la méthode de validation booléenne."""

    @abstractmethod
    def is_satisfied_by(self, product: dict) -> bool:
        """Évalue si le produit satisfait cette spécification."""

    # ── Opérateurs de composition ─────────────────────────────────────────

    def __and__(self, other: NotificationSpecification) -> AndSpec:
        return AndSpec(self, other)

    def __or__(self, other: NotificationSpecification) -> OrSpec:
        return OrSpec(self, other)

    def __invert__(self) -> NotSpec:
        return NotSpec(self)


# ────────────────────────────────────────────────────────────────────────────────
#  SPÉCIFICATIONS CONCRÈTES
# ────────────────────────────────────────────────────────────────────────────────


class MaxPriceSpec(NotificationSpecification):
    """Valide si le prix du produit est inférieur ou égal au seuil."""

    def __init__(self, max_price: float) -> None:
        self.max_price = max_price

    def is_satisfied_by(self, product: dict) -> bool:
        price = product.get("price")
        if price is None:
            return False
        return price <= self.max_price

    def __repr__(self) -> str:
        return f"MaxPriceSpec(max_price={self.max_price})"


class TitleContainsSpec(NotificationSpecification):
    """Valide si le titre contient la sous-chaîne recherchée."""

    def __init__(self, substring: str, *, case_sensitive: bool = False) -> None:
        self.substring = substring
        self.case_sensitive = case_sensitive

    def is_satisfied_by(self, product: dict) -> bool:
        title = product.get("title", "")
        if self.case_sensitive:
            return self.substring in title
        return self.substring.lower() in title.lower()

    def __repr__(self) -> str:
        return f"TitleContainsSpec(substring={self.substring!r}, case_sensitive={self.case_sensitive})"


class PartNumberSpec(NotificationSpecification):
    """Valide si le part_number correspond à l'un des motifs (glob / fnmatch)."""

    def __init__(self, patterns: list[str]) -> None:
        self.patterns = patterns

    def is_satisfied_by(self, product: dict) -> bool:
        pn = product.get("part_number", "")
        return any(fnmatch(pn, pattern) for pattern in self.patterns)

    def __repr__(self) -> str:
        return f"PartNumberSpec(patterns={self.patterns!r})"


# ────────────────────────────────────────────────────────────────────────────────
#  COMPOSITE — Opérateurs logiques
# ────────────────────────────────────────────────────────────────────────────────


class AndSpec(NotificationSpecification):
    """Agrégation ET : toutes les sous-spécifications doivent être satisfaites."""

    def __init__(self, *specs: NotificationSpecification) -> None:
        self.specs = specs

    def is_satisfied_by(self, product: dict) -> bool:
        return all(spec.is_satisfied_by(product) for spec in self.specs)

    def __repr__(self) -> str:
        return f"AndSpec({', '.join(repr(s) for s in self.specs)})"


class OrSpec(NotificationSpecification):
    """Agrégation OU : au moins une sous-spécification doit être satisfaite."""

    def __init__(self, *specs: NotificationSpecification) -> None:
        self.specs = specs

    def is_satisfied_by(self, product: dict) -> bool:
        return any(spec.is_satisfied_by(product) for spec in self.specs)

    def __repr__(self) -> str:
        return f"OrSpec({', '.join(repr(s) for s in self.specs)})"


class NotSpec(NotificationSpecification):
    """Inverse la valeur d'une spécification."""

    def __init__(self, spec: NotificationSpecification) -> None:
        self.spec = spec

    def is_satisfied_by(self, product: dict) -> bool:
        return not self.spec.is_satisfied_by(product)

    def __repr__(self) -> str:
        return f"NotSpec({self.spec!r})"


# ────────────────────────────────────────────────────────────────────────────────
#  DÉSÉRIALISATION — Construction de l'arbre depuis le JSON
# ────────────────────────────────────────────────────────────────────────────────

# Registre des types de spécification (extensible sans modifier le code existant)
_SPEC_BUILDERS: dict[str, type] = {
    "max_price": MaxPriceSpec,
    "title_contains": TitleContainsSpec,
    "part_number": PartNumberSpec,
}


def build_spec_from_config(config: dict) -> NotificationSpecification:
    """Construit récursivement un arbre de spécifications depuis un dict JSON.

    Formats supportés :

    Feuille (règle simple) :
        {"type": "max_price", "value": 2000}
        {"type": "title_contains", "value": "MacBook", "case_sensitive": true}
        {"type": "part_number", "value": ["FQKX*", "FQ7*"]}

    Nœud composite :
        {"operator": "and"|"or"|"not", "rules": [...]}
    """
    # ── Nœud composite ────────────────────────────────────────────────────
    if "operator" in config:
        operator = config["operator"].lower()
        rules = config.get("rules", [])

        if operator == "not":
            if len(rules) != 1:
                raise ValueError("L'opérateur 'not' attend exactement une règle")
            return NotSpec(build_spec_from_config(rules[0]))

        sub_specs = [build_spec_from_config(r) for r in rules]
        if not sub_specs:
            raise ValueError(f"L'opérateur '{operator}' nécessite au moins une règle")

        if operator == "and":
            return AndSpec(*sub_specs)
        if operator == "or":
            return OrSpec(*sub_specs)

        raise ValueError(f"Opérateur inconnu : {operator!r}")

    # ── Feuille (règle simple) ────────────────────────────────────────────
    spec_type = config.get("type")
    if not spec_type:
        raise ValueError(f"Règle invalide (ni 'operator' ni 'type') : {config}")

    if spec_type not in _SPEC_BUILDERS:
        raise ValueError(
            f"Type de spécification inconnu : {spec_type!r}. "
            f"Types disponibles : {list(_SPEC_BUILDERS.keys())}"
        )

    value = config.get("value")
    if value is None:
        raise ValueError(f"Clé 'value' manquante pour le type {spec_type!r}")

    if spec_type == "max_price":
        return MaxPriceSpec(float(value))
    if spec_type == "title_contains":
        case_sensitive = config.get("case_sensitive", False)
        return TitleContainsSpec(str(value), case_sensitive=case_sensitive)
    if spec_type == "part_number":
        patterns = value if isinstance(value, list) else [value]
        return PartNumberSpec([str(p) for p in patterns])

    # Fallback (ne devrait pas arriver grâce à la vérification ci-dessus)
    raise ValueError(f"Type non géré : {spec_type!r}")  # pragma: no cover


def load_filter_rules(path: str) -> NotificationSpecification | None:
    """Charge les règles de filtrage depuis un fichier JSON.

    Returns:
        L'arbre de spécifications, ou None si le fichier n'existe pas,
        est vide, ou contient un objet vide {}.
    """
    rules_path = Path(path)

    if not rules_path.exists():
        logger.info("Fichier de filtrage absent (%s) — aucun filtre actif", path)
        return None

    try:
        raw = rules_path.read_text(encoding="utf-8").strip()
    except OSError as e:
        logger.warning("Impossible de lire %s : %s — aucun filtre actif", path, e)
        return None

    if not raw:
        logger.info("Fichier de filtrage vide (%s) — aucun filtre actif", path)
        return None

    config = json.loads(raw)

    if not config or config == {}:
        logger.info("Règles de filtrage vides (%s) — aucun filtre actif", path)
        return None

    spec = build_spec_from_config(config)
    logger.info("Règles de filtrage chargées : %s", spec)
    return spec


# ────────────────────────────────────────────────────────────────────────────────
#  ROUTEUR — Content-Based Routing
# ────────────────────────────────────────────────────────────────────────────────


def filter_products(
    products: list[dict],
    spec: NotificationSpecification | None,
) -> list[dict]:
    """Filtre les produits selon la spécification (Content-Based Routing).

    Si spec est None, tous les produits sont conservés (pas de filtre actif).
    """
    if spec is None:
        return products

    before = len(products)
    filtered = [p for p in products if spec.is_satisfied_by(p)]
    after = len(filtered)

    if before != after:
        logger.info(
            "Filtrage : %d → %d produit(s) conservé(s) (%d écarté(s))",
            before,
            after,
            before - after,
        )

    return filtered
