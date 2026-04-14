"""Authentication view exports."""

from auth.views import (
    AdminLoginView,
    AdminPasswordResetConfirmView,
    AdminPasswordResetNewPasswordView,
    AdminPasswordResetStartView,
    LoginView,
    LogoutView,
    RegisterPasswordView,
    RegisterSuccessView,
    RegisterView,
)

__all__ = [
    "AdminLoginView",
    "AdminPasswordResetConfirmView",
    "AdminPasswordResetNewPasswordView",
    "AdminPasswordResetStartView",
    "LoginView",
    "LogoutView",
    "RegisterPasswordView",
    "RegisterSuccessView",
    "RegisterView",
]

