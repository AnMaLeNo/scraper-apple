"""Port abstrait — Notifications."""

from __future__ import annotations

from abc import ABC, abstractmethod

from mac_scraper.domain.models import Product


class NotifierPort(ABC):
    """Interface abstraite pour l'envoi de notifications.

    Raises:
        NotificationDeliveryError: en cas d'échec d'envoi.
    """

    @abstractmethod
    def notify_products(self, routed: dict[str, list[Product]]) -> None:
        """Dispatch les notifications produit vers les canaux routés.

        Args:
            routed: dictionnaire {topic: [produits]} issu du routage multicanal.
        """

    @abstractmethod
    def notify_failure(self, error: str, consecutive: int) -> None:
        """Envoie une alerte après plusieurs échecs consécutifs."""

    @abstractmethod
    def notify_lifecycle(self, event: str) -> None:
        """Envoie une notification de démarrage ou d'arrêt."""
