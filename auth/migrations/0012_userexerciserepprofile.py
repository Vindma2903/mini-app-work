from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mini_auth", "0011_trainingresult_result_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserExerciseRepProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("exercise_slug", models.SlugField(max_length=120)),
                ("rep_1", models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])),
                ("rep_2", models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])),
                ("rep_3", models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])),
                ("rep_4", models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="exercise_rep_profiles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
                "unique_together": {("user", "exercise_slug")},
            },
        ),
    ]
