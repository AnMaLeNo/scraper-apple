"""Composition Root — Point d'entrée de l'application.

Responsabilités :
1. Charger et valider la configuration (Pydantic)
2. Configurer le logging
3. Instancier les adaptateurs concrets (injection de dépendances)
4. Instancier le service applicatif (SyncService)
5. Exécuter la boucle principale avec gestion des signaux
"""

from __future__ import annotations

import logging
import random
import signal
import threading

from mac_scraper.adapters.apple_scraper import AppleScraper
from mac_scraper.adapters.ntfy_notifier import NtfyNotifier
from mac_scraper.adapters.sqlite_repository import SqliteRepository
from mac_scraper.application.sync_service import SyncService
from mac_scraper.config import Settings, load_routing_table
from mac_scraper.domain.exceptions import MacScraperError

# ─── Flag d'arrêt (utilisé par le signal handler) ────────────────────────────
_shutdown_event = threading.Event()


def _handle_shutdown(signum: int, frame: object) -> None:
    """Positionne le flag d'arrêt — aucune I/O bloquante ici."""
    sig_name = signal.Signals(signum).name
    logger = logging.getLogger("mac-scraper")
    logger.info("Signal %s reçu — arrêt demandé…", sig_name)
    _shutdown_event.set()


def main() -> None:
    """Point d'entrée — boucle infinie avec jitter."""
    # ── 1. Configuration (ValidationError si non-conforme) ───────────────
    settings = Settings()  # type: ignore[call-arg]

    # ── 2. Logging ───────────────────────────────────────────────────────
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("mac-scraper")

    # ── 3. Intercepter les signaux d'arrêt ───────────────────────────────
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    # ── 4. Injection de dépendances (Composition Root) ───────────────────
    repository = SqliteRepository(db_path=settings.db_path)
    scraper = AppleScraper(
        base_url=settings.apple_base_url,
        product_base_url=settings.apple_product_base_url,
        scrape_paths=settings.scrape_paths,
    )
    notifier = NtfyNotifier(
        ntfy_url=settings.ntfy_url,
        default_topic=settings.ntfy_topic,
        check_interval_seconds=settings.check_interval_seconds,
    )
    sync_service = SyncService(
        repository=repository,
        scraper=scraper,
        notifier=notifier,
    )

    # ── 5. Banner ────────────────────────────────────────────────────────
    logger.info("═══════════════════════════════════════════════════════")
    logger.info("  Scraper Apple Reconditionnés — Démarrage")
    logger.info("  Topic ntfy : %s", settings.ntfy_topic)
    logger.info(
        "  Intervalle : %ds (+/-%ds jitter)",
        settings.check_interval_seconds,
        settings.jitter_seconds,
    )
    logger.info("  Chemins    : %s", settings.scrape_paths or ["(page principale)"])
    logger.info("  BDD        : %s", settings.db_path)
    logger.info("═══════════════════════════════════════════════════════")

    # ── 6. Initialisation ────────────────────────────────────────────────
    repository.init()

    routing_table = load_routing_table(settings.filter_rules_path)
    if routing_table:
        logger.info("  Routage   : %d canal(aux) actif(s)", len(routing_table))
        for topic in routing_table:
            logger.info("    → %s", topic)
    else:
        logger.info("  Routage   : aucun canal (pas de notification produit)")

    notifier.notify_lifecycle("start")

    # ── 7. Boucle principale ─────────────────────────────────────────────
    consecutive_failures = 0
    is_first_run = len(repository.get_all_part_numbers()) == 0

    while not _shutdown_event.is_set():
        try:
            sync_service.run_check(
                is_first_run=is_first_run,
                routing_table=routing_table,
            )
            consecutive_failures = 0
            is_first_run = False
        except MacScraperError as e:
            consecutive_failures += 1
            logger.error(
                "Échec du scraping (%d/%d) : %s",
                consecutive_failures,
                settings.max_consecutive_failures,
                e,
            )
            if consecutive_failures >= settings.max_consecutive_failures:
                notifier.notify_failure(str(e), consecutive_failures)

        # ── Jitter ───────────────────────────────────────────────────────
        jitter = random.randint(-settings.jitter_seconds, settings.jitter_seconds)
        sleep_time = max(30, settings.check_interval_seconds + jitter)
        logger.info("Prochaine vérification dans %ds", sleep_time)
        _shutdown_event.wait(timeout=sleep_time)

    # ── 8. Nettoyage après signal d'arrêt ────────────────────────────────
    logger.info("Arrêt en cours — envoi notification de fin…")
    notifier.notify_lifecycle("stop")
    logger.info("Scraper arrêté proprement.")


if __name__ == "__main__":
    main()
