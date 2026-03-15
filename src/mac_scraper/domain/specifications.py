"""
Filtrage des notifications — Specification Pattern.

Ce module implémente un arbre d'évaluation conditionnelle pour filtrer
les produits avant notification. Couche domaine pure — aucune I/O.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from fnmatch import fnmatch

from mac_scraper.domain.models import Product

# ────────────────────────────────────────────────────────────────────────────────
#  SPECIFICATION PATTERN — Interface abstraite
# ────────────────────────────────────────────────────────────────────────────────


class NotificationSpecification(ABC):
    """Interface abstraite déclarant la méthode de validation booléenne."""

    @abstractmethod
    def is_satisfied_by(self, product: Product) -> bool:
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

    def is_satisfied_by(self, product: Product) -> bool:
        if product.price is None:
            return False
        return product.price <= self.max_price

    def __repr__(self) -> str:
        return f"MaxPriceSpec(max_price={self.max_price})"


class TitleContainsSpec(NotificationSpecification):
    """Valide si le titre contient la sous-chaîne recherchée."""

    def __init__(self, substring: str, *, case_sensitive: bool = False) -> None:
        self.substring = substring
        self.case_sensitive = case_sensitive

    def is_satisfied_by(self, product: Product) -> bool:
        title = product.title
        if self.case_sensitive:
            return self.substring in title
        return self.substring.lower() in title.lower()

    def __repr__(self) -> str:
        return f"TitleContainsSpec(substring={self.substring!r}, case_sensitive={self.case_sensitive})"


class PartNumberSpec(NotificationSpecification):
    """Valide si le part_number correspond à l'un des motifs (glob / fnmatch)."""

    def __init__(self, patterns: list[str]) -> None:
        self.patterns = patterns

    def is_satisfied_by(self, product: Product) -> bool:
        return any(fnmatch(product.part_number, pattern) for pattern in self.patterns)

    def __repr__(self) -> str:
        return f"PartNumberSpec(patterns={self.patterns!r})"


# ────────────────────────────────────────────────────────────────────────────────
#  COMPOSITE — Opérateurs logiques
# ────────────────────────────────────────────────────────────────────────────────


class AndSpec(NotificationSpecification):
    """Agrégation ET : toutes les sous-spécifications doivent être satisfaites."""

    def __init__(self, *specs: NotificationSpecification) -> None:
        self.specs = specs

    def is_satisfied_by(self, product: Product) -> bool:
        return all(spec.is_satisfied_by(product) for spec in self.specs)

    def __repr__(self) -> str:
        return f"AndSpec({', '.join(repr(s) for s in self.specs)})"


class OrSpec(NotificationSpecification):
    """Agrégation OU : au moins une sous-spécification doit être satisfaite."""

    def __init__(self, *specs: NotificationSpecification) -> None:
        self.specs = specs

    def is_satisfied_by(self, product: Product) -> bool:
        return any(spec.is_satisfied_by(product) for spec in self.specs)

    def __repr__(self) -> str:
        return f"OrSpec({', '.join(repr(s) for s in self.specs)})"


class NotSpec(NotificationSpecification):
    """Inverse la valeur d'une spécification."""

    def __init__(self, spec: NotificationSpecification) -> None:
        self.spec = spec

    def is_satisfied_by(self, product: Product) -> bool:
        return not self.spec.is_satisfied_by(product)

    def __repr__(self) -> str:
        return f"NotSpec({self.spec!r})"


# ────────────────────────────────────────────────────────────────────────────────
#  DÉSÉRIALISATION — Construction de l'arbre depuis un dict JSON
# ────────────────────────────────────────────────────────────────────────────────

# Registre des types de spécification (extensible sans modifier le code existant)
_SPEC_BUILDERS: dict[str, type[NotificationSpecification]] = {
    "max_price": MaxPriceSpec,
    "title_contains": TitleContainsSpec,
    "part_number": PartNumberSpec,
}


def build_spec_from_config(config: dict[str, object]) -> NotificationSpecification:
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
        operator = str(config["operator"]).lower()
        rules_raw = config.get("rules", [])
        if not isinstance(rules_raw, list):
            raise ValueError("'rules' doit être une liste")
        rules: list[dict[str, object]] = rules_raw

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

    spec_type_str = str(spec_type)
    if spec_type_str not in _SPEC_BUILDERS:
        raise ValueError(
            f"Type de spécification inconnu : {spec_type_str!r}. "
            f"Types disponibles : {list(_SPEC_BUILDERS.keys())}"
        )

    value = config.get("value")
    if value is None:
        raise ValueError(f"Clé 'value' manquante pour le type {spec_type_str!r}")

    if spec_type_str == "max_price":
        return MaxPriceSpec(float(value))  # type: ignore[arg-type]
    if spec_type_str == "title_contains":
        case_sensitive = bool(config.get("case_sensitive", False))
        return TitleContainsSpec(str(value), case_sensitive=case_sensitive)
    if spec_type_str == "part_number":
        patterns = value if isinstance(value, list) else [value]
        return PartNumberSpec([str(p) for p in patterns])

    # Fallback (ne devrait pas arriver grâce à la vérification ci-dessus)
    raise ValueError(f"Type non géré : {spec_type_str!r}")  # pragma: no cover
