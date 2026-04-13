from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mini_auth", "0010_userprofile_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="trainingresult",
            name="result_type",
            field=models.CharField(
                choices=[("time", "Time"), ("weight", "Weight"), ("reps", "Reps count")],
                default="time",
                max_length=16,
            ),
        ),
    ]
