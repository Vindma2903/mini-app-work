import os

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.db import transaction


def _ensure_verified_email(user: User, email: str) -> None:
    # Mark email as confirmed for allauth flows that require mandatory verification.
    # Keep at most one primary email per user to satisfy allauth unique_primary_email.
    with transaction.atomic():
        EmailAddress.objects.filter(user=user).update(primary=False)

        target = (
            EmailAddress.objects
            .filter(user=user, email__iexact=email)
            .order_by('id')
            .first()
        )
        if target is None:
            EmailAddress.objects.create(
                user=user,
                email=email,
                verified=True,
                primary=True,
            )
        else:
            target.email = email
            target.verified = True
            target.primary = True
            target.save(update_fields=['email', 'verified', 'primary'])


def ensure_default_admin() -> tuple[User, bool]:
    username = os.getenv('DEFAULT_ADMIN_USERNAME', 'admin').strip() or 'admin'
    email = os.getenv('DEFAULT_ADMIN_EMAIL', 'admin@example.com').strip() or 'admin@example.com'
    password = os.getenv('DEFAULT_ADMIN_PASSWORD', 'admin12345').strip() or 'admin12345'

    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            'email': email,
            'is_staff': True,
            'is_superuser': True,
            'is_active': True,
        },
    )

    user.email = email
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.set_password(password)
    user.save(update_fields=['email', 'is_staff', 'is_superuser', 'is_active', 'password'])
    _ensure_verified_email(user, email)

    return user, created


def ensure_default_user() -> tuple[User, bool]:
    username = os.getenv('DEFAULT_USER_USERNAME', 'user').strip() or 'user'
    email = os.getenv('DEFAULT_USER_EMAIL', 'user@example.com').strip() or 'user@example.com'
    password = os.getenv('DEFAULT_USER_PASSWORD', 'user12345').strip() or 'user12345'

    # Prevent accidental overlap with admin account by username.
    admin_username = os.getenv('DEFAULT_ADMIN_USERNAME', 'admin').strip() or 'admin'
    if username == admin_username:
        username = 'default_user'

    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            'email': email,
            'is_staff': False,
            'is_superuser': False,
            'is_active': True,
        },
    )

    user.email = email
    user.is_staff = False
    user.is_superuser = False
    user.is_active = True
    user.set_password(password)
    user.save(update_fields=['email', 'is_staff', 'is_superuser', 'is_active', 'password'])
    _ensure_verified_email(user, email)

    return user, created


def ensure_default_users() -> dict[str, tuple[User, bool]]:
    admin_result = ensure_default_admin()
    user_result = ensure_default_user()
    return {
        'admin': admin_result,
        'user': user_result,
    }
