from django.urls import path, re_path
from dj_rest_auth.registration.views import ResendEmailVerificationView, VerifyEmailView

from .api_views import EmailRegisterView

urlpatterns = [
    path('', EmailRegisterView.as_view(), name='rest_register'),
    path('verify-email/', VerifyEmailView.as_view(), name='rest_verify_email'),
    path(
        'resend-email/',
        ResendEmailVerificationView.as_view(),
        name='rest_resend_email',
    ),
    re_path(
        r'^account-confirm-email/(?P<key>[-:\w]+)/$',
        VerifyEmailView.as_view(),
        name='account_confirm_email',
    ),
]
