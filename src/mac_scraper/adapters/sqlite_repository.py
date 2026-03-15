"""Adaptateur infrastructure — Persistance SQLite.

Implémente ProductRepositoryPort. Responsable du Data Mapping :
les sqlite3.Row sont convertis en entités Product avant de traverser
la frontière du port. L'infrastructure s'adapte au domaine, jamais l'inverse.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone

from mac_scraper.domain.exceptions import RepositoryOperationError
from mac_scraper.domain.models import Product
from mac_scraper.ports.repository import ProductRepositoryPort

logger = logging.getLogger("mac-scraper")


class SqliteRepository(ProductRepositoryPort):
    """Accès aux données produit via SQLite."""

    def __init__(self, *, db_path: str) -> None:
        self._db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Crée / ouvre la connexion SQLite."""
        try:
            is_uri = self._db_path.startswith("file:")
            if not is_uri:
                os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
            conn = sqlite3.connect(self._db_path, uri=is_uri)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            raise RepositoryOperationError(
                f"Impossible d'ouvrir la base de données {self._db_path}: {e}"
            ) from e

    def init(self) -> None:
        """Crée la table products si elle n'existe pas."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS products (
                        part_number TEXT PRIMARY KEY,
                        title       TEXT,
                        price       REAL,
                        url         TEXT,
                        in_stock    INTEGER NOT NULL DEFAULT 1,
                        first_seen  TEXT NOT NULL,
                        last_seen   TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
        except sqlite3.Error as e:
            raise RepositoryOperationError(
                f"Échec de l'initialisation du schéma: {e}"
            ) from e

    def get_all_part_numbers(self) -> set[str]:
        """Retourne tous les part_numbers connus."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute("SELECT part_number FROM products").fetchall()
            return {row["part_number"] for row in rows}
        except sqlite3.Error as e:
            raise RepositoryOperationError(
                f"Échec de la lecture des part_numbers: {e}"
            ) from e

    def get_in_stock_part_numbers(self) -> set[str]:
        """Retourne les part_numbers actuellement en stock."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT part_number FROM products WHERE in_stock = 1"
                ).fetchall()
            return {row["part_number"] for row in rows}
        except sqlite3.Error as e:
            raise RepositoryOperationError(
                f"Échec de la lecture des produits en stock: {e}"
            ) from e

    def get_out_of_stock_part_numbers(self) -> set[str]:
        """Retourne les part_numbers hors stock."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT part_number FROM products WHERE in_stock = 0"
                ).fetchall()
            return {row["part_number"] for row in rows}
        except sqlite3.Error as e:
            raise RepositoryOperationError(
                f"Échec de la lecture des produits hors stock: {e}"
            ) from e

    def upsert_product(
        self,
        product: Product,
        *,
        is_new: bool,
        back_in_stock: bool,
    ) -> None:
        """Insère ou met à jour un produit.

        Data Mapping : l'entité Product est décomposée en paramètres SQL.
        """
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_connection() as conn:
                if is_new:
                    conn.execute(
                        """
                        INSERT INTO products
                            (part_number, title, price, url, in_stock, first_seen, last_seen)
                        VALUES (?, ?, ?, ?, 1, ?, ?)
                        """,
                        (
                            product.part_number,
                            product.title,
                            product.price,
                            product.url,
                            now,
                            now,
                        ),
                    )
                elif back_in_stock:
                    conn.execute(
                        """
                        UPDATE products
                        SET title=?, price=?, url=?, in_stock=1, last_seen=?
                        WHERE part_number=?
                        """,
                        (
                            product.title,
                            product.price,
                            product.url,
                            now,
                            product.part_number,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE products
                        SET title=?, price=?, url=?, last_seen=?
                        WHERE part_number=?
                        """,
                        (
                            product.title,
                            product.price,
                            product.url,
                            now,
                            product.part_number,
                        ),
                    )
                conn.commit()
        except sqlite3.Error as e:
            raise RepositoryOperationError(
                f"Échec de l'upsert pour {product.part_number}: {e}"
            ) from e

    def mark_out_of_stock(self, part_numbers: set[str]) -> None:
        """Marque les part_numbers donnés comme hors stock."""
        if not part_numbers:
            return
        try:
            with self._get_connection() as conn:
                placeholders = ",".join("?" for _ in part_numbers)
                conn.execute(
                    f"UPDATE products SET in_stock = 0 WHERE part_number IN ({placeholders})",
                    list(part_numbers),
                )
                conn.commit()
        except sqlite3.Error as e:
            raise RepositoryOperationError(
                f"Échec du marquage hors stock: {e}"
            ) from e
