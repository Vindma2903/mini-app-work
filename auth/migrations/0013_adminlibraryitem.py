from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('mini_auth', '0012_userexerciserepprofile'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AdminLibraryItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('section', models.CharField(choices=[('exercises', 'Exercises'), ('trainings', 'Trainings'), ('barbell', 'Barbell PRs'), ('benchmarks', 'Benchmarks')], db_index=True, default='exercises', max_length=16)),
                ('benchmark_category', models.CharField(blank=True, choices=[('girls', 'Girls'), ('heroes', 'Heroes'), ('gymnastics', 'Gymnastics')], db_index=True, default='', max_length=16)),
                ('name_ru', models.CharField(max_length=255)),
                ('name_en', models.CharField(blank=True, default='', max_length=255)),
                ('desc_ru', models.TextField(blank=True, default='')),
                ('desc_en', models.TextField(blank=True, default='')),
                ('video_file', models.FileField(blank=True, null=True, upload_to='library/videos/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='library_items_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-updated_at', '-id'],
            },
        ),
    ]
