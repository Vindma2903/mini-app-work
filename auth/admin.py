from django.contrib import admin

from .models import AdminContact, AdminPasswordResetRequest


@admin.register(AdminContact)
class AdminContactAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'created_at')
    search_fields = ('user__email', 'phone')


@admin.register(AdminPasswordResetRequest)
class AdminPasswordResetRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'expires_at', 'is_used', 'created_at')
    search_fields = ('user__email',)
    list_filter = ('is_used',)
