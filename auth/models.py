from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator


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

    RESULT_TIME = 'time'
    RESULT_WEIGHT = 'weight'
    RESULT_REPS = 'reps'
    RESULT_TYPE_CHOICES = (
        (RESULT_TIME, 'Time'),
        (RESULT_WEIGHT, 'Weight'),
        (RESULT_REPS, 'Reps count'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='training_results',
    )
    training_date = models.DateField(default=timezone.localdate, db_index=True)
    section = models.CharField(max_length=16, choices=SECTION_CHOICES)
    result_type = models.CharField(max_length=16, choices=RESULT_TYPE_CHOICES, default=RESULT_TIME)
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


class CommunityReaction(models.Model):
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='community_reactions_sent',
    )
    target_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='community_reactions_received',
    )
    training_date = models.DateField(default=timezone.localdate, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('sender', 'target_user', 'training_date')

    def __str__(self):
        return (
            f'{self.sender.email} -> {self.target_user.email}: '
            f'{self.training_date.isoformat()}'
        )


class UserExerciseRepProfile(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='exercise_rep_profiles',
    )
    exercise_slug = models.SlugField(max_length=120)
    rep_1 = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    rep_2 = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    rep_3 = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    rep_4 = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ('user', 'exercise_slug')

    def __str__(self):
        return f'{self.user.email}: {self.exercise_slug}'


class AdminTraining(models.Model):
    VISIBILITY_COACHES = 'coaches'
    VISIBILITY_ALL = 'all'
    VISIBILITY_CHOICES = (
        (VISIBILITY_COACHES, 'Only for coaches'),
        (VISIBILITY_ALL, 'For all'),
    )

    SOURCE_MANUAL = 'manual'
    SOURCE_LIBRARY = 'library'
    SOURCE_READY = 'ready'
    SOURCE_CHOICES = (
        (SOURCE_MANUAL, 'Manual'),
        (SOURCE_LIBRARY, 'Library'),
        (SOURCE_READY, 'Ready complex'),
    )

    DIRECTION_FBB = 'fbb'
    DIRECTION_CROSSFIT = 'crossfit'
    DIRECTION_GYMNASTICS = 'gymnastics'
    DIRECTION_WORKOUT = 'workout'
    DIRECTION_FUNCTIONAL = 'functional'
    DIRECTION_STRENGTH = 'strength'
    DIRECTION_CHOICES = (
        (DIRECTION_FBB, 'FBB'),
        (DIRECTION_CROSSFIT, 'Crossfit with Denis Zalozniy'),
        (DIRECTION_GYMNASTICS, 'Gymnastics'),
        (DIRECTION_WORKOUT, 'Training of the day'),
        (DIRECTION_FUNCTIONAL, 'Functional training'),
        (DIRECTION_STRENGTH, 'Strength training'),
    )

    COLOR_BLUE = 'blue'
    COLOR_ORANGE = 'orange'
    COLOR_GREEN = 'green'
    COLOR_PINK = 'pink'
    COLOR_VIOLET = 'violet'
    COLOR_CHOICES = (
        (COLOR_BLUE, 'Blue'),
        (COLOR_ORANGE, 'Orange'),
        (COLOR_GREEN, 'Green'),
        (COLOR_PINK, 'Pink'),
        (COLOR_VIOLET, 'Violet'),
    )

    MANUAL_RESULT_TIME = 'time'
    MANUAL_RESULT_WEIGHT = 'weight'
    MANUAL_RESULT_REPS = 'reps'
    MANUAL_RESULT_CHOICES = (
        (MANUAL_RESULT_TIME, 'Time'),
        (MANUAL_RESULT_WEIGHT, 'Weight'),
        (MANUAL_RESULT_REPS, 'Reps count'),
    )

    training_date = models.DateField(default=timezone.localdate, db_index=True)
    direction = models.CharField(max_length=32, choices=DIRECTION_CHOICES, default=DIRECTION_FBB)
    visibility = models.CharField(max_length=16, choices=VISIBILITY_CHOICES, default=VISIBILITY_ALL)
    comment = models.TextField(blank=True, default='')
    color = models.CharField(max_length=16, choices=COLOR_CHOICES, default=COLOR_BLUE)
    source_type = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    comment_for_coaches = models.TextField(blank=True, default='')
    comment_for_athletes = models.TextField(blank=True, default='')
    manual_description_ru = models.TextField(blank=True, default='')
    manual_description_en = models.TextField(blank=True, default='')
    manual_sets = models.PositiveSmallIntegerField(null=True, blank=True)
    manual_result_type = models.CharField(
        max_length=16,
        choices=MANUAL_RESULT_CHOICES,
        blank=True,
        default='',
    )
    ready_workout_type = models.CharField(max_length=32, blank=True, default='')
    ready_complex_type = models.CharField(max_length=32, blank=True, default='')
    ready_complex_name = models.CharField(max_length=255, blank=True, default='')
    ready_plan_title = models.CharField(max_length=255, blank=True, default='')
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='admin_trainings_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-training_date', '-updated_at']

    def __str__(self):
        return f'{self.training_date.isoformat()} {self.get_direction_display()}'


class AdminTrainingExercise(models.Model):
    EXERCISE_KIND_EXERCISE = 'exercise'
    EXERCISE_KIND_BENCHMARKS = 'benchmarks'
    EXERCISE_KIND_CHOICES = (
        (EXERCISE_KIND_EXERCISE, 'Exercise'),
        (EXERCISE_KIND_BENCHMARKS, 'Benchmarks'),
    )

    BLOCK_STRENGTH = 'strength'
    BLOCK_CARDIO = 'cardio'
    BLOCK_GYMNASTICS = 'gymnastics'
    BLOCK_CUSTOM = 'custom'
    BLOCK_CHOICES = (
        (BLOCK_STRENGTH, 'Strength'),
        (BLOCK_CARDIO, 'Cardio'),
        (BLOCK_GYMNASTICS, 'Gymnastics'),
        (BLOCK_CUSTOM, 'Custom'),
    )

    RESULT_TIME = 'time'
    RESULT_WEIGHT = 'weight'
    RESULT_REPS = 'reps'
    RESULT_CHOICES = (
        (RESULT_TIME, 'Time'),
        (RESULT_WEIGHT, 'Weight'),
        (RESULT_REPS, 'Reps count'),
    )

    training = models.ForeignKey(
        AdminTraining,
        on_delete=models.CASCADE,
        related_name='exercises',
    )
    library_item = models.ForeignKey(
        'AdminLibraryItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_exercises',
    )
    block_type = models.CharField(max_length=16, choices=BLOCK_CHOICES, default=BLOCK_STRENGTH)
    block_custom_name = models.CharField(max_length=255, blank=True, default='')
    exercise_kind = models.CharField(max_length=16, choices=EXERCISE_KIND_CHOICES, default=EXERCISE_KIND_EXERCISE)
    exercise_name = models.CharField(max_length=255)
    sets = models.PositiveSmallIntegerField(null=True, blank=True)
    reps = models.PositiveSmallIntegerField(null=True, blank=True)
    result_type = models.CharField(max_length=16, choices=RESULT_CHOICES, default=RESULT_TIME)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.training_id}: {self.exercise_name}'


class UserProfile(models.Model):
    ROLE_USER = 'user'
    ROLE_TRAINER = 'trainer'
    ROLE_ADMIN = 'admin'
    ROLE_CHOICES = (
        (ROLE_USER, 'User'),
        (ROLE_TRAINER, 'Trainer'),
        (ROLE_ADMIN, 'Admin'),
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_USER)
    birth_date = models.DateField(null=True, blank=True)
    weekly_goal = models.PositiveSmallIntegerField(default=6)
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


class AdminLibraryItem(models.Model):
    SECTION_EXERCISES = 'exercises'
    SECTION_TRAININGS = 'trainings'
    SECTION_BARBELL = 'barbell'
    SECTION_BENCHMARKS = 'benchmarks'
    SECTION_CHOICES = (
        (SECTION_EXERCISES, 'Exercises'),
        (SECTION_TRAININGS, 'Trainings'),
        (SECTION_BARBELL, 'Barbell PRs'),
        (SECTION_BENCHMARKS, 'Benchmarks'),
    )

    CATEGORY_GIRLS = 'girls'
    CATEGORY_HEROES = 'heroes'
    CATEGORY_GYMNASTICS = 'gymnastics'
    CATEGORY_TOTAL = 'total'
    BENCHMARK_CATEGORY_CHOICES = (
        (CATEGORY_GIRLS, 'Girls'),
        (CATEGORY_HEROES, 'Heroes'),
        (CATEGORY_GYMNASTICS, 'Gymnastics'),
        (CATEGORY_TOTAL, 'Total'),
    )

    MOVEMENT_GROUP_SQUAT = 'squat'
    MOVEMENT_GROUP_PUSH = 'push'
    MOVEMENT_GROUP_PULL = 'pull'
    MOVEMENT_GROUP_BEND = 'bend'
    MOVEMENT_GROUP_LUNGE = 'lunge'
    MOVEMENT_GROUP_OLYMPIC = 'olympic'
    MOVEMENT_GROUP_PLYOMETRIC = 'plyometric'
    MOVEMENT_GROUP_CARDIO = 'cardio'
    MOVEMENT_GROUP_TRX = 'trx'
    MOVEMENT_GROUP_CHOICES = (
        (MOVEMENT_GROUP_SQUAT, 'Squat'),
        (MOVEMENT_GROUP_PUSH, 'Push'),
        (MOVEMENT_GROUP_PULL, 'Pull'),
        (MOVEMENT_GROUP_BEND, 'Bend'),
        (MOVEMENT_GROUP_LUNGE, 'Lunge'),
        (MOVEMENT_GROUP_OLYMPIC, 'Olympic'),
        (MOVEMENT_GROUP_PLYOMETRIC, 'Plyometric'),
        (MOVEMENT_GROUP_CARDIO, 'Cardio'),
        (MOVEMENT_GROUP_TRX, 'TRX'),
    )

    section = models.CharField(max_length=16, choices=SECTION_CHOICES, default=SECTION_EXERCISES, db_index=True)
    benchmark_category = models.CharField(
        max_length=16,
        choices=BENCHMARK_CATEGORY_CHOICES,
        blank=True,
        default='',
        db_index=True,
    )
    movement_group = models.CharField(
        max_length=16,
        choices=MOVEMENT_GROUP_CHOICES,
        blank=True,
        default='',
        db_index=True,
    )
    name_ru = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255, blank=True, default='')
    desc_ru = models.TextField(blank=True, default='')
    desc_en = models.TextField(blank=True, default='')
    video_file = models.FileField(upload_to='library/videos/', blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='library_items_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']

    def __str__(self):
        return f'{self.name_ru} ({self.section})'
