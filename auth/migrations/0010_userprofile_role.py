from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mini_auth", "0009_admintraining_admintrainingexercise"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[("user", "User"), ("trainer", "Trainer")],
                default="user",
                max_length=16,
            ),
        ),
    ]
