from django.contrib.auth.hashers import make_password
from django.db import migrations


DEFAULT_USER_EMAIL = "user@example.com"
DEFAULT_USER_PASSWORD = "UserPass123!"
DEFAULT_USER2_EMAIL = "user2@example.com"
DEFAULT_USER2_PASSWORD = "User2Pass123!"
DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_ADMIN_PASSWORD = "AdminPass123!"


def seed_default_users(apps, schema_editor):
    User = apps.get_model("auth", "User")
    EmailAddress = apps.get_model("account", "EmailAddress")

    def ensure_verified_primary_email(user_obj, email):
        EmailAddress.objects.filter(user_id=user_obj.id).exclude(email=email).update(primary=False)
        email_row = EmailAddress.objects.filter(email=email).first()
        if email_row:
            email_row.user_id = user_obj.id
            email_row.verified = True
            email_row.primary = True
            email_row.save(update_fields=["user_id", "verified", "primary"])
            return
        EmailAddress.objects.create(
            user_id=user_obj.id,
            email=email,
            verified=True,
            primary=True,
        )

    user, _ = User.objects.get_or_create(
        username=DEFAULT_USER_EMAIL,
        defaults={
            "email": DEFAULT_USER_EMAIL,
            "first_name": "Olga",
            "last_name": "User",
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
            "password": make_password(DEFAULT_USER_PASSWORD),
        },
    )
    ensure_verified_primary_email(user, DEFAULT_USER_EMAIL)

    user2, _ = User.objects.get_or_create(
        username=DEFAULT_USER2_EMAIL,
        defaults={
            "email": DEFAULT_USER2_EMAIL,
            "first_name": "Vika",
            "last_name": "User",
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
            "password": make_password(DEFAULT_USER2_PASSWORD),
        },
    )
    ensure_verified_primary_email(user2, DEFAULT_USER2_EMAIL)

    admin, _ = User.objects.get_or_create(
        username=DEFAULT_ADMIN_EMAIL,
        defaults={
            "email": DEFAULT_ADMIN_EMAIL,
            "first_name": "Admin",
            "last_name": "User",
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
            "password": make_password(DEFAULT_ADMIN_PASSWORD),
        },
    )
    ensure_verified_primary_email(admin, DEFAULT_ADMIN_EMAIL)


class Migration(migrations.Migration):
    dependencies = [
        ("mini_auth", "0006_communityreaction"),
        ("account", "0009_emailaddress_unique_primary_email"),
    ]

    operations = [
        migrations.RunPython(seed_default_users, migrations.RunPython.noop),
    ]
