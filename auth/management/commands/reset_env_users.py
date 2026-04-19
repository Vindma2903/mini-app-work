from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from auth.seeds import ensure_default_admin, ensure_default_user


class Command(BaseCommand):
    help = (
        'Delete every user (CASCADE removes related rows: profiles, trainings created_by that user, '
        'reactions, etc.). Then create only the default admin and default regular user from environment '
        'variables, with verified primary email for django-allauth.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes',
            action='store_true',
            dest='confirm',
            help='Required acknowledgement for this destructive operation.',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            raise CommandError('Refusing destructive reset without --yes')

        User = get_user_model()
        with transaction.atomic():
            deleted = User.objects.all().delete()
            # deleted is (total_count, {model_label: count, ...})
            total, per_model = deleted[0], deleted[1]
            self.stdout.write(self.style.WARNING(f'Removed {total} rows in total.'))
            for label, count in sorted(per_model.items(), key=lambda x: x[0]):
                if count:
                    self.stdout.write(f'  {label}: {count}')

        with transaction.atomic():
            admin, admin_created = ensure_default_admin()
            user, user_created = ensure_default_user()

        self.stdout.write(
            self.style.SUCCESS(
                f'Admin {"created" if admin_created else "updated"}: '
                f'username={admin.username!r} email={admin.email!r}'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'User {"created" if user_created else "updated"}: '
                f'username={user.username!r} email={user.email!r}'
            )
        )
        self.stdout.write(
            'Primary emails are verified via auth.seeds (django-allauth EmailAddress). '
            'Optional third demo user: set AUTO_SEED_DEFAULT_USER2=1 before migrate / first request.'
        )
