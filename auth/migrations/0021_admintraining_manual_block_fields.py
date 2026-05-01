from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mini_auth', '0020_alter_trainingresult_unique_together_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='admintraining',
            name='manual_block_custom_name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='admintraining',
            name='manual_block_type',
            field=models.CharField(blank=True, default='', max_length=16),
        ),
    ]
