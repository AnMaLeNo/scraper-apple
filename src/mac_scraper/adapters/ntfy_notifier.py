"""Adaptateur infrastructure — Notifications ntfy.sh.

Implémente NotifierPort. Les erreurs requests.RequestException
sont converties en NotificationDeliveryError.
"""

from __future__ import annotations

import logging

import requests

from mac_scraper.domain.exceptions import NotificationDeliveryError
from mac_scraper.domain.models import Product
from mac_scraper.ports.notifier import NotifierPort

logger = logging.getLogger("mac-scraper")


class NtfyNotifier(NotifierPort):
    """Envoie les notifications via l'API ntfy.sh."""

    def __init__(
        self,
        *,
        ntfy_url: str,
        default_topic: str,
        check_interval_seconds: int,
    ) -> None:
        self._ntfy_url = ntfy_url.rstrip("/")
        self._default_topic = default_topic
        self._check_interval_seconds = check_interval_seconds

    # ── Notifications produit (routage multicanal) ────────────────────────

    def notify_products(self, routed: dict[str, list[Product]]) -> None:
        """Dispatch les notifications vers les topics issus du routage."""
        if not routed:
            return

        for topic, products in routed.items():
            tagged = [("[NEW]", p) for p in products]
            if not tagged:
                continue

            logger.info("Envoi vers [%s] : %d produit(s)", topic, len(tagged))

            if len(tagged) > 5:
                self._send_grouped_notification(topic, tagged)
            else:
                for emoji, product in tagged:
                    self._send_single_notification(topic, emoji, product)

    def _send_single_notification(
        self, topic: str, emoji: str, product: Product
    ) -> None:
        """Envoie une notification individuelle pour un produit."""
        title = f"{emoji} Mac Reconditionne"
        price_str = (
            f"{product.price:.2f} EUR" if product.price is not None else "Prix inconnu"
        )
        message = f"{product.title}\nPrix : {price_str}"

        headers: dict[str, str] = {
            "Title": title,
            "Tags": "apple,computer",
            "Priority": "high",
        }
        if product.url:
            headers["Click"] = product.url
            headers["Actions"] = f"view, Voir sur Apple, {product.url}"

        try:
            resp = requests.post(
                f"{self._ntfy_url}/{topic}",
                data=message.encode("utf-8"),
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            logger.info(
                "  [%s] Notification envoyée : %s", topic, product.part_number
            )
        except requests.RequestException as e:
            logger.error(
                "  [%s] Échec notification pour %s : %s",
                topic,
                product.part_number,
                e,
            )

    def _send_grouped_notification(
        self, topic: str, products: list[tuple[str, Product]]
    ) -> None:
        """Envoie une notification résumée pour beaucoup de produits."""
        title = f"{len(products)} Mac Reconditionnes detectes"
        lines: list[str] = []
        for emoji, p in products[:15]:
            price_str = f"{p.price:.2f} EUR" if p.price is not None else "?"
            lines.append(f"{emoji} {p.title} - {price_str}")
        if len(products) > 15:
            lines.append(f"… et {len(products) - 15} autre(s)")
        message = "\n".join(lines)

        try:
            resp = requests.post(
                f"{self._ntfy_url}/{topic}",
                data=message.encode("utf-8"),
                headers={
                    "Title": title,
                    "Tags": "apple,computer",
                    "Priority": "high",
                },
                timeout=10,
            )
            resp.raise_for_status()
            logger.info(
                "  [%s] Notification groupée envoyée (%d produits)",
                topic,
                len(products),
            )
        except requests.RequestException as e:
            logger.error("  [%s] Échec notification groupée : %s", topic, e)

    # ── Notification d'échec ──────────────────────────────────────────────

    def notify_failure(self, error: str, consecutive: int) -> None:
        """Envoie une alerte critique après plusieurs échecs consécutifs."""
        title = f"ALERTE Scraper en echec ({consecutive} fois)"
        message = (
            f"Le scraper Apple Reconditionnes a echoue {consecutive} fois de suite.\n\n"
            f"Derniere erreur :\n{error}"
        )
        try:
            resp = requests.post(
                f"{self._ntfy_url}/{self._default_topic}",
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
            raise NotificationDeliveryError(
                f"Impossible d'envoyer l'alerte de défaillance: {e}"
            ) from e

    # ── Notification lifecycle ────────────────────────────────────────────

    def notify_lifecycle(self, event: str) -> None:
        """Envoie une notification de démarrage ou d'arrêt du scraper."""
        if event == "start":
            title = "Scraper demarre"
            message = (
                f"Le scraper Apple Reconditionnes est en ligne.\n"
                f"Topic : {self._default_topic}\n"
                f"Intervalle : {self._check_interval_seconds}s (+/-60s)"
            )
            tags = "heavy_check_mark,rocket"
            priority = "default"
        else:
            title = "Scraper arrete"
            message = "Le scraper Apple Reconditionnes a ete arrete."
            tags = "no_entry,skull"
            priority = "high"

        try:
            resp = requests.post(
                f"{self._ntfy_url}/{self._default_topic}",
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
            raise NotificationDeliveryError(
                f"Échec notification lifecycle ({event}): {e}"
            ) from e
