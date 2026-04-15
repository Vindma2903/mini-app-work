from django.urls import path

from .views import (
    AdminProfileUserCreateView,
    AdminProfileUsersListView,
    AdminProfilePasswordUpdateView,
    AdminProfileUpdateView,
    AdminProfileView,
    ProfileView,
    SettingsView,
    StartTelegramLinkView,
    TelegramLinkStatusView,
    TelegramWebhookView,
    UpdateProfileDataView,
    UpdateProfileGoalView,
)

urlpatterns = [
    path("admin/profile/", AdminProfileView.as_view(), name="admin_profile"),
    path("admin/profile/update/", AdminProfileUpdateView.as_view(), name="admin_profile_update"),
    path("admin/profile/password/", AdminProfilePasswordUpdateView.as_view(), name="admin_profile_password"),
    path("admin/profile/users/list/", AdminProfileUsersListView.as_view(), name="admin_profile_users_list"),
    path("admin/profile/users/create/", AdminProfileUserCreateView.as_view(), name="admin_profile_user_create"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("settings/", SettingsView.as_view(), name="settings"),
    path("settings/profile-data/", UpdateProfileDataView.as_view(), name="settings_profile_data"),
    path("profile/goal/", UpdateProfileGoalView.as_view(), name="profile_goal"),
    path("settings/telegram/link-start/", StartTelegramLinkView.as_view(), name="settings_telegram_link_start"),
    path("settings/telegram/status/", TelegramLinkStatusView.as_view(), name="settings_telegram_status"),
    path("telegram/webhook/", TelegramWebhookView.as_view(), name="telegram_webhook"),
]
