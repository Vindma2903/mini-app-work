from django.urls import path

from .views import (
    AdminLoginView,
    AdminPasswordResetConfirmView,
    AdminPasswordResetNewPasswordView,
    AdminPasswordResetStartView,
    LoginView,
    LogoutView,
    RegisterPasswordView,
    RegisterSuccessView,
    RegisterView,
    StartTelegramQuickLoginView,
    TelegramWidgetLoginView,
    TelegramQuickLoginStatusView,
)

urlpatterns = [
    path("", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("admin-auth/", AdminLoginView.as_view(), name="admin_login"),
    path("admin-auth/password-reset/", AdminPasswordResetStartView.as_view(), name="admin_password_reset_start"),
    path("admin-auth/password-reset/confirm/", AdminPasswordResetConfirmView.as_view(), name="admin_password_reset_confirm"),
    path("admin-auth/password-reset/new-password/", AdminPasswordResetNewPasswordView.as_view(), name="admin_password_reset_new_password"),
    path("register/", RegisterView.as_view(), name="register"),
    path("register/password/", RegisterPasswordView.as_view(), name="register_password"),
    path("register/success/", RegisterSuccessView.as_view(), name="register_success"),
    path("auth/telegram/widget/login/", TelegramWidgetLoginView.as_view(), name="telegram_widget_login"),
    path("auth/telegram/quick-login/start/", StartTelegramQuickLoginView.as_view(), name="telegram_quick_login_start"),
    path("auth/telegram/quick-login/status/", TelegramQuickLoginStatusView.as_view(), name="telegram_quick_login_status"),
]
