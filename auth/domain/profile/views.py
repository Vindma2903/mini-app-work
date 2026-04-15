"""Profile view exports."""

from auth.views import (
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

__all__ = [
    "AdminProfileView",
    "AdminProfileUpdateView",
    "AdminProfilePasswordUpdateView",
    "AdminProfileUsersListView",
    "AdminProfileUserCreateView",
    "ProfileView",
    "SettingsView",
    "StartTelegramLinkView",
    "TelegramLinkStatusView",
    "TelegramWebhookView",
    "UpdateProfileDataView",
    "UpdateProfileGoalView",
]
