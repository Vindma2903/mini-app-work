import re

from django.conf import settings
from django.core.exceptions import ValidationError

ACCESS_KEY_PATTERN = re.compile(r"^\d{8}$")


def validate_registration_access_key(value: str) -> str:
    normalized_value = str(value or "").strip()
    if not ACCESS_KEY_PATTERN.fullmatch(normalized_value):
        raise ValidationError("Ключ доступа должен содержать 8 цифр.")

    configured_key = str(getattr(settings, "REGISTRATION_ACCESS_KEY", "") or "").strip()
    if not ACCESS_KEY_PATTERN.fullmatch(configured_key):
        raise ValidationError("Регистрация временно недоступна. Обратитесь к администратору.")

    if normalized_value != configured_key:
        raise ValidationError("Неверный ключ доступа.")

    return normalized_value
