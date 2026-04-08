from django.contrib import admin

from .models import AdminContact, AdminPasswordResetRequest, TrainingRate, TrainingResult, UserProfile


@admin.register(AdminContact)
class AdminContactAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'created_at')
    search_fields = ('user__email', 'phone')


@admin.register(AdminPasswordResetRequest)
class AdminPasswordResetRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'expires_at', 'is_used', 'created_at')
    search_fields = ('user__email',)
    list_filter = ('is_used',)


@admin.register(TrainingResult)
class TrainingResultAdmin(admin.ModelAdmin):
    list_display = ('user', 'training_date', 'section', 'minutes', 'seconds', 'mode', 'updated_at')
    search_fields = ('user__email',)
    list_filter = ('section', 'mode', 'training_date')


@admin.register(TrainingRate)
class TrainingRateAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'training_date',
        'overall',
        'strength',
        'cardio',
        'metabolic',
        'updated_at',
    )
    search_fields = ('user__email', 'comment')
    list_filter = ('training_date',)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'birth_date', 'telegram_user_id', 'telegram_username', 'telegram_linked_at', 'updated_at')
    search_fields = ('user__email', 'telegram_username', 'telegram_user_id')
