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


def load_filter_rules(path: str) -> dict[str, NotificationSpecification]:
    """Charge la table de routage multicanal depuis un fichier JSON.

    Le fichier doit contenir un dictionnaire {topic → arbre_spec}.
    Chaque clé est l'identifiant du topic ntfy cible, et la valeur
    est l'arbre de spécification régissant les critères d'admission.

    Returns:
        Table de routage {topic: spec}. Dictionnaire vide si le fichier
        n'existe pas, est vide, ou contient un objet vide {}.
    """
    rules_path = Path(path)

    if not rules_path.exists():
        logger.info("Fichier de routage absent (%s) — aucun canal actif", path)
        return {}

    try:
        raw = rules_path.read_text(encoding="utf-8").strip()
    except OSError as e:
        logger.warning("Impossible de lire %s : %s — aucun canal actif", path, e)
        return {}

    if not raw:
        logger.info("Fichier de routage vide (%s) — aucun canal actif", path)
        return {}

    config = json.loads(raw)

    if not isinstance(config, dict) or not config:
        logger.info("Table de routage vide (%s) — aucun canal actif", path)
        return {}

    routing_table: dict[str, NotificationSpecification] = {}
    for topic, spec_config in config.items():
        routing_table[topic] = build_spec_from_config(spec_config)
        logger.info("  Canal [%s] → %s", topic, routing_table[topic])

    logger.info("Table de routage chargée : %d canal(aux)", len(routing_table))
    return routing_table


# ────────────────────────────────────────────────────────────────────────────────
#  ROUTEUR — Content-Based Routing (Multiplexage Pub-Sub)
# ────────────────────────────────────────────────────────────────────────────────


def route_products(
    products: list[dict],
    routing_table: dict[str, NotificationSpecification],
) -> dict[str, list[dict]]:
    """Multiplexe les produits vers les canaux de la table de routage.

    Pour chaque produit, évalue is_satisfied_by() de chaque canal.
    Un produit peut apparaître dans 0, 1 ou N vecteurs de sortie.
    L'évaluation est purement fonctionnelle : aucune mutation des dicts produit.

    Returns:
        Dictionnaire {topic: [produits acceptés par ce canal]}.
        Seuls les canaux ayant au moins un produit sont inclus.
    """
    if not routing_table:
        return {}

    routed: dict[str, list[dict]] = {topic: [] for topic in routing_table}

    for product in products:
        for topic, spec in routing_table.items():
            if spec.is_satisfied_by(product):
                routed[topic].append(product)

    # Purger les canaux vides et loguer
    routed = {topic: prods for topic, prods in routed.items() if prods}

    if routed:
        for topic, prods in routed.items():
            logger.info("  Routage [%s] : %d produit(s)", topic, len(prods))
    else:
        logger.info("  Routage : aucun produit ne correspond à un canal")

    return routed
