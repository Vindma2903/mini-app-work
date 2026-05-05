import os

from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.db.models import Q

from .models import UserProfile


def _ensure_verified_email(user: User, email: str) -> None:
    # Mark email as confirmed for allauth flows without violating unique_verified_email.
    EmailAddress.objects.filter(user=user).exclude(email=email).update(primary=False)
    email_row = EmailAddress.objects.filter(email=email).first()
    if email_row:
        email_row.user = user
        email_row.verified = True
        email_row.primary = True
        email_row.save(update_fields=['user', 'verified', 'primary'])
        return

    EmailAddress.objects.create(
        user=user,
        email=email,
        verified=True,
        primary=True,
    )


def _create_user_if_missing(
    *,
    username: str,
    email: str,
    password: str,
    is_staff: bool,
    is_superuser: bool,
) -> tuple[User, bool]:
    existing = User.objects.filter(Q(username=username) | Q(email=email)).first()
    if existing is not None:
        return existing, False

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        is_staff=is_staff,
        is_superuser=is_superuser,
        is_active=True,
    )
    _ensure_verified_email(user, email)
    return user, True


def ensure_default_admin() -> tuple[User, bool]:
    username = os.getenv('DEFAULT_ADMIN_USERNAME', 'admin').strip() or 'admin'
    email = os.getenv('DEFAULT_ADMIN_EMAIL', 'admin@example.com').strip() or 'admin@example.com'
    password = os.getenv('DEFAULT_ADMIN_PASSWORD', 'admin12345').strip() or 'admin12345'

    admin, created = _create_user_if_missing(
        username=username,
        email=email,
        password=password,
        is_staff=True,
        is_superuser=True,
    )

    # Keep default admin account consistent even if it existed before this run.
    admin_updates = []
    if (admin.email or '') != email:
        admin.email = email
        admin_updates.append('email')
    if not admin.is_staff:
        admin.is_staff = True
        admin_updates.append('is_staff')
    if not admin.is_superuser:
        admin.is_superuser = True
        admin_updates.append('is_superuser')
    if not admin.is_active:
        admin.is_active = True
        admin_updates.append('is_active')
    if admin_updates:
        admin.save(update_fields=admin_updates)

    _ensure_verified_email(admin, email)

    profile, _ = UserProfile.objects.get_or_create(user=admin)
    if profile.role != UserProfile.ROLE_ADMIN:
        profile.role = UserProfile.ROLE_ADMIN
        profile.save(update_fields=['role'])
    return admin, created


def ensure_default_user() -> tuple[User, bool]:
    username = os.getenv('DEFAULT_USER_USERNAME', 'user').strip() or 'user'
    email = os.getenv('DEFAULT_USER_EMAIL', 'user@example.com').strip() or 'user@example.com'
    password = os.getenv('DEFAULT_USER_PASSWORD', 'user12345').strip() or 'user12345'

    # Prevent accidental overlap with admin account by username.
    admin_username = os.getenv('DEFAULT_ADMIN_USERNAME', 'admin').strip() or 'admin'
    if username == admin_username:
        username = 'default_user'

    user, created = _create_user_if_missing(
        username=username,
        email=email,
        password=password,
        is_staff=False,
        is_superuser=False,
    )
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if profile.role != UserProfile.ROLE_USER:
        profile.role = UserProfile.ROLE_USER
        profile.save(update_fields=['role'])
    return user, created

def ensure_default_user2() -> tuple[User, bool]:
    username = os.getenv('DEFAULT_USER2_USERNAME', 'user2').strip() or 'user2'
    email = os.getenv('DEFAULT_USER2_EMAIL', 'user2@example.com').strip() or 'user2@example.com'
    password = os.getenv('DEFAULT_USER2_PASSWORD', 'user2pass12345').strip() or 'user2pass12345'

    taken_usernames = {
        os.getenv('DEFAULT_ADMIN_USERNAME', 'admin').strip() or 'admin',
        os.getenv('DEFAULT_USER_USERNAME', 'user').strip() or 'user',
    }
    if username in taken_usernames:
        username = 'default_user2'

    user2, created = _create_user_if_missing(
        username=username,
        email=email,
        password=password,
        is_staff=False,
        is_superuser=False,
    )
    profile, _ = UserProfile.objects.get_or_create(user=user2)
    if profile.role != UserProfile.ROLE_USER:
        profile.role = UserProfile.ROLE_USER
        profile.save(update_fields=['role'])
    return user2, created


def ensure_default_users() -> dict[str, tuple[User, bool]]:
    admin_result = ensure_default_admin()
    user_result = ensure_default_user()
    user2_result = ensure_default_user2()
    return {
        'admin': admin_result,
        'user': user_result,
        'user2': user2_result,
    }
