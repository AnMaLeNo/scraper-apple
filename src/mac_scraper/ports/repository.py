"""Port abstrait — Persistance des produits."""

from __future__ import annotations

from abc import ABC, abstractmethod

from mac_scraper.domain.models import Product


class ProductRepositoryPort(ABC):
    """Interface abstraite pour l'accès aux données persistantes.

    Les implémentations concrètes sont responsables du Data Mapping :
    les structures internes de la couche de persistance (tuples, Row, etc.)
    doivent être converties en entités ``Product`` avant de traverser
    cette frontière.

    Raises:
        RepositoryOperationError: en cas d'échec d'une opération CRUD.
    """

    @abstractmethod
    def init(self) -> None:
        """Initialise le schéma de persistance (création de tables, etc.)."""

    @abstractmethod
    def get_all_part_numbers(self) -> set[str]:
        """Retourne tous les part_numbers connus (en stock ou non)."""

    @abstractmethod
    def get_in_stock_part_numbers(self) -> set[str]:
        """Retourne les part_numbers actuellement marqués en stock."""

    @abstractmethod
    def get_out_of_stock_part_numbers(self) -> set[str]:
        """Retourne les part_numbers marqués hors stock."""

    @abstractmethod
    def upsert_product(
        self,
        product: Product,
        *,
        is_new: bool,
        back_in_stock: bool,
    ) -> None:
        """Insère ou met à jour un produit.

        Args:
            product: l'entité domaine à persister.
            is_new: True si le produit est totalement inconnu (INSERT).
            back_in_stock: True si le produit revient en stock (UPDATE).
        """

    @abstractmethod
    def mark_out_of_stock(self, part_numbers: set[str]) -> None:
        """Marque les part_numbers donnés comme hors stock."""
