#!/usr/bin/env python3
"""
Scraper Apple Reconditionnés — Surveille l'inventaire et notifie via ntfy.sh.
"""

import json
import os
import random
import re
import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone

import requests

from config import (
    APPLE_BASE_URL,
    APPLE_PRODUCT_BASE_URL,
    CHECK_INTERVAL_SECONDS,
    DB_PATH,
    MAX_CONSECUTIVE_FAILURES,
    NTFY_TOPIC,
    NTFY_URL,
    SCRAPE_PATHS,
    logger,
)

# ─── User-Agent réaliste ─────────────────────────────────────────────────────
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.5 Safari/605.1.15"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ────────────────────────────────────────────────────────────────────────────────
#  SCRAPING
# ────────────────────────────────────────────────────────────────────────────────

def scrape_page(path: str = "") -> list[dict]:
    """Scrape une page Apple Refurbished et retourne la liste des produits.

    Exploite le JSON embarqué `window.REFURB_GRID_BOOTSTRAP` présent dans le HTML.
    """
    url = f"{APPLE_BASE_URL}/{path}".rstrip("/")
    logger.info("Scraping %s", url)

    resp = requests.get(url, headers=HTTP_HEADERS, timeout=30)
    resp.raise_for_status()

    match = re.search(
        r"window\.REFURB_GRID_BOOTSTRAP\s*=\s*({.*?});\s*</script>",
        resp.text,
        re.DOTALL,
    )
    if not match:
        raise ValueError(f"JSON REFURB_GRID_BOOTSTRAP introuvable dans {url}")

    data = json.loads(match.group(1))
    tiles = data.get("tiles", [])

    products: list[dict] = []
    for tile in tiles:
        part_number = tile.get("partNumber", "").strip()
        if not part_number:
            continue
        title = tile.get("title", "").strip()
        price_info = tile.get("price", {}).get("currentPrice", {})
        price = price_info.get("raw_amount")
        url_path = tile.get("productDetailsUrl", "")
        product_url = (
            f"{APPLE_PRODUCT_BASE_URL}{url_path}" if url_path else ""
        )
        products.append(
            {
                "part_number": part_number,
                "title": title,
                "price": float(price) if price is not None else None,
                "url": product_url,
            }
        )

    logger.info("  → %d produit(s) trouvé(s)", len(products))
    return products


def scrape_all() -> list[dict]:
    """Scrape toutes les pages configurées et déduplique par part_number."""
    paths = SCRAPE_PATHS if SCRAPE_PATHS else [""]
    seen: set[str] = set()
    all_products: list[dict] = []

    for path in paths:
        products = scrape_page(path)
        for p in products:
            if p["part_number"] not in seen:
                seen.add(p["part_number"])
                all_products.append(p)

    logger.info("Total unique : %d produit(s)", len(all_products))
    return all_products


# ────────────────────────────────────────────────────────────────────────────────
#  BASE DE DONNÉES (SQLite)
# ────────────────────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """Crée / ouvre la connexion SQLite. Crée le dossier parent si nécessaire."""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Crée la table products si elle n'existe pas."""
    with get_connection() as conn:
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


def get_in_stock_part_numbers() -> set[str]:
    """Retourne les part_numbers actuellement marqués en stock."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT part_number FROM products WHERE in_stock = 1"
        ).fetchall()
    return {r["part_number"] for r in rows}


def get_all_part_numbers() -> set[str]:
    """Retourne tous les part_numbers connus (en stock ou non)."""
    with get_connection() as conn:
        rows = conn.execute("SELECT part_number FROM products").fetchall()
    return {r["part_number"] for r in rows}


def get_out_of_stock_part_numbers() -> set[str]:
    """Retourne les part_numbers marqués hors stock."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT part_number FROM products WHERE in_stock = 0"
        ).fetchall()
    return {r["part_number"] for r in rows}


def sync_products(scraped: list[dict]) -> tuple[list[dict], list[dict]]:
    """Synchronise les produits scrapés avec la base.

    Returns:
        (new_products, back_in_stock_products) — les listes de produits à notifier.
    """
    now = datetime.now(timezone.utc).isoformat()
    scraped_pns = {p["part_number"] for p in scraped}
    known_all = get_all_part_numbers()
    in_stock = get_in_stock_part_numbers()
    out_of_stock = get_out_of_stock_part_numbers()

    new_products: list[dict] = []
    back_in_stock: list[dict] = []

    with get_connection() as conn:
        for product in scraped:
            pn = product["part_number"]

            if pn not in known_all:
                # ── Produit totalement inconnu → INSERT
                conn.execute(
                    """
                    INSERT INTO products (part_number, title, price, url, in_stock, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (pn, product["title"], product["price"], product["url"], now, now),
                )
                new_products.append(product)

            elif pn in out_of_stock:
                # ── Retour en stock → UPDATE + notification
                conn.execute(
                    """
                    UPDATE products SET title=?, price=?, url=?, in_stock=1, last_seen=?
                    WHERE part_number=?
                    """,
                    (product["title"], product["price"], product["url"], now, pn),
                )
                back_in_stock.append(product)

            else:
                # ── Toujours en stock → simple mise à jour
                conn.execute(
                    """
                    UPDATE products SET title=?, price=?, url=?, last_seen=?
                    WHERE part_number=?
                    """,
                    (product["title"], product["price"], product["url"], now, pn),
                )

        # ── Produits en base marqués en stock mais absents du scrape → hors stock
        disappeared = in_stock - scraped_pns
        if disappeared:
            placeholders = ",".join("?" for _ in disappeared)
            conn.execute(
                f"UPDATE products SET in_stock = 0 WHERE part_number IN ({placeholders})",
                list(disappeared),
            )
            logger.info("  → %d produit(s) sorti(s) du stock", len(disappeared))

        conn.commit()

    return new_products, back_in_stock


# ────────────────────────────────────────────────────────────────────────────────
#  NOTIFICATIONS (ntfy.sh)
# ────────────────────────────────────────────────────────────────────────────────

def notify_new_products(new: list[dict], back: list[dict]) -> None:
    """Envoie des notifications push pour les nouveaux produits / retours en stock."""
    products_to_notify = [
        ("[NEW]", p) for p in new
    ] + [
        ("[RETOUR]", p) for p in back
    ]

    if not products_to_notify:
        return

    # Si plus de 5 produits, envoyer un résumé groupé
    if len(products_to_notify) > 5:
        _send_grouped_notification(products_to_notify)
    else:
        for emoji, product in products_to_notify:
            _send_single_notification(emoji, product)


def _send_single_notification(emoji: str, product: dict) -> None:
    """Envoie une notification individuelle pour un produit."""
    title = f"{emoji} Mac Reconditionne"
    price_str = f"{product['price']:.2f} EUR" if product["price"] else "Prix inconnu"
    message = f"{product['title']}\nPrix : {price_str}"

    headers = {
        "Title": title,
        "Tags": "apple,computer",
        "Priority": "high",
    }
    if product.get("url"):
        headers["Click"] = product["url"]
        headers["Actions"] = f"view, Voir sur Apple, {product['url']}"

    try:
        resp = requests.post(
            f"{NTFY_URL}/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Notification envoyée : %s", product["part_number"])
    except requests.RequestException as e:
        logger.error("Échec notification pour %s : %s", product["part_number"], e)


def _send_grouped_notification(products: list[tuple[str, dict]]) -> None:
    """Envoie une notification résumée pour beaucoup de produits."""
    title = f"{len(products)} Mac Reconditionnes detectes"
    lines: list[str] = []
    for emoji, p in products[:15]:  # Limiter à 15 lignes
        price_str = f"{p['price']:.2f} EUR" if p["price"] else "?"
        lines.append(f"{emoji} {p['title']} - {price_str}")
    if len(products) > 15:
        lines.append(f"… et {len(products) - 15} autre(s)")
    message = "\n".join(lines)

    try:
        resp = requests.post(
            f"{NTFY_URL}/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Tags": "apple,computer",
                "Priority": "high",
            },
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Notification groupée envoyée (%d produits)", len(products))
    except requests.RequestException as e:
        logger.error("Échec notification groupée : %s", e)


def notify_failure(error: str, consecutive_failures: int) -> None:
    """Envoie une alerte critique après plusieurs échecs consécutifs."""
    title = f"ALERTE Scraper en echec ({consecutive_failures} fois)"
    message = f"Le scraper Apple Reconditionnes a echoue {consecutive_failures} fois de suite.\n\nDerniere erreur :\n{error}"

    try:
        resp = requests.post(
            f"{NTFY_URL}/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Tags": "warning,skull",
                "Priority": "urgent",
            },
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Alerte de défaillance envoyée")
    except requests.RequestException as e:
        logger.error("Impossible d'envoyer l'alerte de défaillance : %s", e)


def notify_lifecycle(event: str) -> None:
    """Envoie une notification de démarrage ou d'arrêt du scraper."""
    if event == "start":
        title = "Scraper demarre"
        message = f"Le scraper Apple Reconditionnes est en ligne.\nTopic : {NTFY_TOPIC}\nIntervalle : {CHECK_INTERVAL_SECONDS}s (+/-60s)"
        tags = "heavy_check_mark,rocket"
        priority = "default"
    else:
        title = "Scraper arrete"
        message = "Le scraper Apple Reconditionnes a ete arrete."
        tags = "no_entry,skull"
        priority = "high"

    try:
        resp = requests.post(
            f"{NTFY_URL}/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Tags": tags,
                "Priority": priority,
            },
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Notification lifecycle envoyée : %s", event)
    except requests.RequestException as e:
        logger.error("Échec notification lifecycle (%s) : %s", event, e)


# ────────────────────────────────────────────────────────────────────────────────
#  BOUCLE PRINCIPALE
# ────────────────────────────────────────────────────────────────────────────────

def run_check(is_first_run: bool) -> None:
    """Exécute un cycle complet : scrape → compare → sync → notifie."""
    products = scrape_all()

    if not products:
        logger.warning("Aucun produit trouvé — page vide ou erreur silencieuse")
        return

    new_products, back_in_stock = sync_products(products)

    if is_first_run:
        logger.info(
            "Premier remplissage : %d produit(s) enregistré(s) (pas de notification)",
            len(products),
        )
        return

    total_alerts = len(new_products) + len(back_in_stock)
    if total_alerts > 0:
        logger.info(
            "%d nouveau(x), %d retour(s) en stock → envoi de notifications",
            len(new_products),
            len(back_in_stock),
        )
        notify_new_products(new_products, back_in_stock)
    else:
        logger.info("Aucun changement détecté")


def _handle_shutdown(signum, frame):
    """Gère l'arrêt propre sur SIGTERM / SIGINT."""
    sig_name = signal.Signals(signum).name
    logger.info("Signal %s reçu — arrêt en cours…", sig_name)
    notify_lifecycle("stop")
    sys.exit(0)


def main() -> None:
    """Point d'entrée — boucle infinie avec jitter."""
    # ── Intercepter les signaux d'arrêt (docker stop envoie SIGTERM)
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    logger.info("═══════════════════════════════════════════════════════")
    logger.info("  Scraper Apple Reconditionnés — Démarrage")
    logger.info("  Topic ntfy : %s", NTFY_TOPIC)
    logger.info("  Intervalle : %ds (±60s jitter)", CHECK_INTERVAL_SECONDS)
    logger.info("  Chemins    : %s", SCRAPE_PATHS or ["(page principale)"])
    logger.info("  BDD        : %s", DB_PATH)
    logger.info("═══════════════════════════════════════════════════════")

    init_db()
    notify_lifecycle("start")

    consecutive_failures = 0
    is_first_run = len(get_all_part_numbers()) == 0

    while True:
        try:
            run_check(is_first_run)
            consecutive_failures = 0  # Reset on success
            is_first_run = False
        except Exception as e:
            consecutive_failures += 1
            logger.error(
                "Échec du scraping (%d/%d) : %s",
                consecutive_failures,
                MAX_CONSECUTIVE_FAILURES,
                e,
            )
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                notify_failure(str(e), consecutive_failures)

        # ── Jitter : ±120 secondes autour de l'intervalle configuré
        jitter = random.randint(-120, 120)
        sleep_time = max(30, CHECK_INTERVAL_SECONDS + jitter)  # Minimum 30s
        logger.info("Prochaine vérification dans %ds", sleep_time)
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
