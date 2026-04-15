from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mini_auth', '0013_adminlibraryitem'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                choices=[('user', 'User'), ('trainer', 'Trainer'), ('admin', 'Admin')],
                default='user',
                max_length=16,
            ),
        ),
    ]
