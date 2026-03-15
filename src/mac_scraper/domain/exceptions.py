"""Hiérarchie d'exceptions du domaine.

Tous les adaptateurs d'infrastructure interceptent les erreurs de bas niveau
(sqlite3.Error, requests.RequestException, etc.) et lèvent une exception
héritant de MacScraperError. La couche application et le Composition Root
ne traitent que ces exceptions abstraites.
"""

from __future__ import annotations


class MacScraperError(Exception):
    """Classe de base pour toutes les erreurs du domaine mac-scraper."""


# ── Scraping ──────────────────────────────────────────────────────────────────


class ScrapingError(MacScraperError):
    """Erreur générique lors du scraping."""


class ScrapingTimeoutError(ScrapingError):
    """Timeout lors d'une requête HTTP de scraping."""


class ScrapingParsingError(ScrapingError):
    """Impossible de parser le contenu de la page scrapée."""


# ── Repository ────────────────────────────────────────────────────────────────


class RepositoryError(MacScraperError):
    """Erreur générique d'accès aux données persistantes."""


class RepositoryOperationError(RepositoryError):
    """Échec d'une opération CRUD sur le repository."""


# ── Notification ──────────────────────────────────────────────────────────────


class NotificationError(MacScraperError):
    """Erreur générique de notification."""


class NotificationDeliveryError(NotificationError):
    """Échec de l'envoi d'une notification."""
