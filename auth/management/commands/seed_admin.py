from django.core.management.base import BaseCommand

from auth.seeds import ensure_default_users


class Command(BaseCommand):
    help = 'Create or update default users (admin + regular user) from environment variables.'

    def handle(self, *args, **options):
        result = ensure_default_users()
        admin_user, admin_created = result['admin']
        regular_user, regular_created = result['user']

        admin_action = 'created' if admin_created else 'updated'
        user_action = 'created' if regular_created else 'updated'

        self.stdout.write(self.style.SUCCESS(
            f'Default admin {admin_action}: username="{admin_user.username}", email="{admin_user.email}"'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'Default user {user_action}: username="{regular_user.username}", email="{regular_user.email}"'
        ))
