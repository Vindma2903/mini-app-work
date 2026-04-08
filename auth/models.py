from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class AdminContact(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='admin_contact',
    )
    phone = models.CharField(max_length=32, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.email} ({self.phone})'


class AdminPasswordResetRequest(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='admin_password_reset_requests',
    )
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Password reset request for {self.user.email}'

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class TrainingResult(models.Model):
    SECTION_STRENGTH = 'strength'
    SECTION_CARDIO = 'cardio'
    SECTION_METABOLIC = 'metabolic'
    SECTION_CHOICES = (
        (SECTION_STRENGTH, 'Strength'),
        (SECTION_CARDIO, 'Cardio'),
        (SECTION_METABOLIC, 'Metabolic'),
    )

    MODE_RX = 'rx'
    MODE_SCALED = 'scaled'
    MODE_CHOICES = (
        (MODE_RX, 'RX'),
        (MODE_SCALED, 'SCALED'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='training_results',
    )
    training_date = models.DateField(default=timezone.localdate, db_index=True)
    section = models.CharField(max_length=16, choices=SECTION_CHOICES)
    minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    seconds = models.PositiveSmallIntegerField(null=True, blank=True)
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default=MODE_RX)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-training_date', '-updated_at']
        unique_together = ('user', 'training_date', 'section')

    def __str__(self):
        return f'{self.user.email}: {self.training_date} ({self.section})'


class TrainingRate(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='training_rates',
    )
    training_date = models.DateField(default=timezone.localdate, db_index=True)
    overall = models.PositiveSmallIntegerField()
    strength = models.PositiveSmallIntegerField()
    cardio = models.PositiveSmallIntegerField()
    metabolic = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-training_date', '-updated_at']
        unique_together = ('user', 'training_date')

    def __str__(self):
        return f'{self.user.email}: {self.training_date} rate={self.overall}'


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    birth_date = models.DateField(null=True, blank=True)
    telegram_user_id = models.BigIntegerField(null=True, blank=True, unique=True)
    telegram_username = models.CharField(max_length=255, blank=True, default='')
    telegram_first_name = models.CharField(max_length=255, blank=True, default='')
    telegram_last_name = models.CharField(max_length=255, blank=True, default='')
    telegram_link_token = models.CharField(max_length=128, blank=True, default='', db_index=True)
    telegram_link_expires_at = models.DateTimeField(null=True, blank=True)
    telegram_linked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Profile of {self.user.email}'
