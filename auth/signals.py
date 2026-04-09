import os

from django.db.models.signals import post_migrate
from django.db.utils import OperationalError, ProgrammingError
from django.dispatch import receiver

from .seeds import ensure_default_users


def _is_enabled(value: str | None) -> bool:
    return (value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


@receiver(post_migrate)
def create_default_admin_on_migrate(**kwargs) -> None:
    if not _is_enabled(os.getenv('AUTO_CREATE_ADMIN', '1')):
        return

    try:
        ensure_default_users()
    except (OperationalError, ProgrammingError):
        # Ignore DB-not-ready edge cases during early migration lifecycle.
        return


def ensure_default_admin_on_startup() -> None:
    if not _is_enabled(os.getenv('AUTO_CREATE_ADMIN', '1')):
        return

    try:
        ensure_default_users()
    except (OperationalError, ProgrammingError):
        # DB can be unavailable early during process startup.
        return
