from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("mini_auth", "0021_admintraining_manual_block_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserBenchmarkResultProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("exercise_slug", models.SlugField(max_length=120)),
                ("minutes", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("seconds", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("mode", models.CharField(choices=[("rx", "RX"), ("scaled", "SCALED")], default="rx", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="benchmark_result_profiles", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-updated_at"],
                "unique_together": {("user", "exercise_slug")},
            },
        ),
    ]
