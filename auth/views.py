import secrets
from datetime import timedelta

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import FormView, TemplateView

from .forms import (
    AdminLoginForm,
    AdminPasswordResetConfirmForm,
    AdminPasswordResetStartForm,
    LoginForm,
    RegisterPasswordForm,
    RegisterStepForm,
)
from .models import AdminPasswordResetRequest

REGISTER_SESSION_KEY = 'register_step_data'
ADMIN_PASSWORD_RESET_SESSION_KEY = 'admin_password_reset_request_id'


class LoginView(FormView):
    template_name = 'auth/login.html'
    form_class = LoginForm
    success_url = reverse_lazy('auth:login')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        login(self.request, form.user)
        return super().form_valid(form)


class AdminLoginView(FormView):
    template_name = 'auth/admin-login.html'
    form_class = AdminLoginForm
    success_url = reverse_lazy('admin:index')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        login(self.request, form.user)
        return super().form_valid(form)


class AdminPasswordResetStartView(FormView):
    template_name = 'auth/admin-password-reset-start.html'
    form_class = AdminPasswordResetStartForm
    success_url = reverse_lazy('auth:admin_password_reset_confirm')

    def form_valid(self, form):
        contact = form.admin_contact
        code = f'{secrets.randbelow(1000000):06d}'
        expires_at = timezone.now() + timedelta(minutes=10)

        reset_request = AdminPasswordResetRequest.objects.create(
            user=contact.user,
            code=code,
            expires_at=expires_at,
        )
        self.request.session[ADMIN_PASSWORD_RESET_SESSION_KEY] = reset_request.id

        send_mail(
            subject='Admin password reset code',
            message=(
                'Your password reset confirmation code is: '
                f'{code}\n\nThis code is valid for 10 minutes.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[contact.user.email],
            fail_silently=False,
        )

        messages.success(self.request, 'Confirmation code has been sent to your email.')
        return super().form_valid(form)


class AdminPasswordResetConfirmView(FormView):
    template_name = 'auth/admin-password-reset-confirm.html'
    form_class = AdminPasswordResetConfirmForm
    success_url = reverse_lazy('auth:admin_login')

    def dispatch(self, request, *args, **kwargs):
        if ADMIN_PASSWORD_RESET_SESSION_KEY not in request.session:
            return redirect('auth:admin_password_reset_start')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        request_id = self.request.session.get(ADMIN_PASSWORD_RESET_SESSION_KEY)
        reset_request = AdminPasswordResetRequest.objects.select_related('user').filter(
            id=request_id,
            is_used=False,
        ).first()
        if reset_request is None:
            form.add_error(None, form.error_messages['invalid_code'])
            return self.form_invalid(form)

        if reset_request.is_expired:
            form.add_error(None, form.error_messages['expired_code'])
            return self.form_invalid(form)

        if form.cleaned_data['code'] != reset_request.code:
            form.add_error('code', form.error_messages['invalid_code'])
            return self.form_invalid(form)

        user = reset_request.user
        user.set_password(form.cleaned_data['password'])
        user.save(update_fields=['password'])

        reset_request.is_used = True
        reset_request.save(update_fields=['is_used'])
        self.request.session.pop(ADMIN_PASSWORD_RESET_SESSION_KEY, None)

        messages.success(self.request, 'Password has been updated. You can sign in now.')
        return super().form_valid(form)


class RegisterView(FormView):
    template_name = 'auth/register.html'
    form_class = RegisterStepForm
    success_url = reverse_lazy('auth:register_password')

    def form_valid(self, form):
        self.request.session[REGISTER_SESSION_KEY] = {
            'first_name': form.cleaned_data['first_name'],
            'last_name': form.cleaned_data['last_name'],
            'birth_date': form.cleaned_data['birth_date'].isoformat(),
            'email': form.cleaned_data['email'],
            'phone': form.cleaned_data['phone'],
        }
        return super().form_valid(form)


class RegisterPasswordView(FormView):
    template_name = 'auth/register-password.html'
    form_class = RegisterPasswordForm
    success_url = reverse_lazy('auth:register_success')

    def dispatch(self, request, *args, **kwargs):
        if REGISTER_SESSION_KEY not in request.session:
            return redirect('auth:register')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        signup_data = self.request.session.get(REGISTER_SESSION_KEY)
        email = signup_data['email']
        user = User.objects.create_user(
            username=email,
            email=email,
            password=form.cleaned_data['password'],
            first_name=signup_data['first_name'],
            last_name=signup_data['last_name'],
            is_active=True,
        )
        EmailAddress.objects.add_email(self.request, user, email, confirm=True)
        self.request.session.pop(REGISTER_SESSION_KEY, None)
        return super().form_valid(form)


class RegisterSuccessView(TemplateView):
    template_name = 'auth/register-success.html'

    def dispatch(self, request, *args, **kwargs):
        messages.success(
            request,
            'Мы отправили письмо на email. Подтвердите регистрацию по ссылке из письма.',
        )
        return super().dispatch(request, *args, **kwargs)


class ProfileView(TemplateView):
    template_name = 'auth/profile.html'


class ProfileAwardsTestsView(TemplateView):
    template_name = 'auth/profile-awards-tests.html'


class ProfileAwardWorkoutView(TemplateView):
    template_name = 'auth/profile-award-workout.html'


class CalendarView(TemplateView):
    template_name = 'auth/calendar.html'


class LeaderboardDayView(TemplateView):
    template_name = 'auth/leaderboard-day.html'


class CommunityView(TemplateView):
    template_name = 'auth/community.html'


class TrainingPlanTodayView(TemplateView):
    template_name = 'auth/training-plan-today.html'
