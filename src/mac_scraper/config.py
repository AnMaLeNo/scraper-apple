"""Configuration centralisée — Validation structurelle Pydantic.

Utilise pydantic-settings pour charger et valider les variables
d'environnement au démarrage. Lève ValidationError si une variable
requise est absente ou invalide.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings

from mac_scraper.domain.specifications import (
    NotificationSpecification,
    build_spec_from_config,
)

logger = logging.getLogger("mac-scraper")


class Settings(BaseSettings):
    """Configuration de l'application, validée au démarrage."""

    # ── Requis ────────────────────────────────────────────────────────────
    ntfy_topic: str

    # ── Optionnel ─────────────────────────────────────────────────────────
    ntfy_url: str = "https://ntfy.sh"
    db_path: str = "/data/inventory.db"
    check_interval_seconds: int = 900
    jitter_seconds: int = 120
    max_consecutive_failures: int = 3
    scrape_paths: list[str] = []
    filter_rules_path: str = "filter_rules.json"
    log_level: str = "INFO"

    # ── URLs Apple ────────────────────────────────────────────────────────
    apple_base_url: str = "https://www.apple.com/fr/shop/refurbished/mac"
    apple_product_base_url: str = "https://www.apple.com"

    @field_validator("ntfy_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def _uppercase_log_level(cls, v: str) -> str:
        return v.upper()

    @field_validator("scrape_paths", mode="before")
    @classmethod
    def _parse_scrape_paths(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        if isinstance(v, list):
            return v
        return []


def load_routing_table(path: str) -> dict[str, NotificationSpecification]:
    """Charge la table de routage multicanal depuis un fichier JSON.

    Le fichier doit contenir un dictionnaire {topic → arbre_spec}.

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

    config: object = json.loads(raw)

    if not isinstance(config, dict) or not config:
        logger.info("Table de routage vide (%s) — aucun canal actif", path)
        return {}

    routing_table: dict[str, NotificationSpecification] = {}
    for topic, spec_config in config.items():
        routing_table[topic] = build_spec_from_config(spec_config)
        logger.info("  Canal [%s] → %s", topic, routing_table[topic])

    logger.info("Table de routage chargée : %d canal(aux)", len(routing_table))
    return routing_table
