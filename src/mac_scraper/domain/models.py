"""Entités du domaine métier."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Product:
    """Représente un produit Apple reconditionné.

    Objet-valeur immuable utilisé comme monnaie d'échange entre toutes les
    couches de l'application. Aucune dépendance vers l'infrastructure.
    """

    part_number: str
    title: str
    price: float | None
    url: str
