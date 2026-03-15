"""Configuration centralisée via variables d'environnement."""

import os
import sys
import logging

# ─── URLs à scraper ───────────────────────────────────────────────────────────
# Chemins relatifs séparés par des virgules. Vide = page principale /refurbished/mac
SCRAPE_PATHS: list[str] = [
    p.strip() for p in os.getenv("SCRAPE_PATHS", "").split(",") if p.strip()
]

# ─── Intervalle de vérification ───────────────────────────────────────────────
CHECK_INTERVAL_SECONDS: int = int(os.getenv("CHECK_INTERVAL_SECONDS", "900"))

# ─── ntfy.sh ──────────────────────────────────────────────────────────────────
NTFY_TOPIC: str = os.getenv("NTFY_TOPIC", "")
NTFY_URL: str = os.getenv("NTFY_URL", "https://ntfy.sh").rstrip("/")

if not NTFY_TOPIC:
    print("ERREUR FATALE : La variable d'environnement NTFY_TOPIC est requise.", file=sys.stderr)
    sys.exit(1)

# ─── Base de données ──────────────────────────────────────────────────────────
DB_PATH: str = os.getenv("DB_PATH", "/data/inventory.db")

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mac-scraper")

# ─── Seuil d'alerte de défaillance ───────────────────────────────────────────
MAX_CONSECUTIVE_FAILURES: int = int(os.getenv("MAX_CONSECUTIVE_FAILURES", "3"))

# ─── Jitter (fluctuation aléatoire sur l'intervalle) ─────────────────────────
JITTER_SECONDS: int = int(os.getenv("JITTER_SECONDS", "120"))

# ─── Base URL Apple ───────────────────────────────────────────────────────────
APPLE_BASE_URL: str = "https://www.apple.com/fr/shop/refurbished/mac"
APPLE_PRODUCT_BASE_URL: str = "https://www.apple.com"

# ─── Filtrage des notifications ───────────────────────────────────────────────
FILTER_RULES_PATH: str = os.getenv("FILTER_RULES_PATH", "filter_rules.json")
