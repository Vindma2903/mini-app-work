import secrets
import logging
import json
from datetime import timedelta
from io import BytesIO

from allauth.account.models import EmailAddress
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import IntegrityError
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import FormView, TemplateView
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from .forms import (
    AdminLoginForm,
    AdminPasswordResetConfirmForm,
    AdminPasswordResetNewPasswordForm,
    AdminPasswordResetStartForm,
    LoginForm,
    RegisterPasswordForm,
    RegisterStepForm,
)
from .jwt_utils import build_token_pair_for_user, clear_jwt_cookies, get_jwt_cookie_names, set_jwt_cookies
from .models import (
    AdminContact,
    AdminPasswordResetRequest,
    CommunityReaction,
    TrainingRate,
    TrainingResult,
    UserProfile,
)

REGISTER_SESSION_KEY = 'register_step_data'
ADMIN_PASSWORD_RESET_SESSION_KEY = 'admin_password_reset_request_id'
ADMIN_PASSWORD_RESET_CODE_VERIFIED_KEY = 'admin_password_reset_code_verified'
TELEGRAM_LINK_TTL_MINUTES = 10
logger = logging.getLogger(__name__)


def get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def resolve_request_user(request):
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if auth_header.lower().startswith('bearer '):
        raw_token = auth_header.split(' ', 1)[1].strip()
        if not raw_token:
            return None, None

        jwt_auth = JWTAuthentication()
        try:
            validated_token = jwt_auth.get_validated_token(raw_token)
            user = jwt_auth.get_user(validated_token)
            return user, 'jwt'
        except (InvalidToken, AuthenticationFailed):
            return None, None

    if request.user.is_authenticated:
        return request.user, 'cookie'

    return None, None


def build_telegram_deep_link(token):
    bot_username = (settings.TELEGRAM_BOT_USERNAME or '').strip().lstrip('@')
    if not bot_username:
        return ''
    return f'https://t.me/{bot_username}?start=link_{token}'


class LoginView(FormView):
    template_name = 'auth/login.html'
    form_class = LoginForm
    success_url = reverse_lazy('auth:profile')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        access_token, refresh_token = build_token_pair_for_user(form.user)
        logger.info(
            'User login success email=%s user_id=%s ip=%s',
            form.user.email,
            form.user.id,
            get_client_ip(self.request),
        )
        response = super().form_valid(form)
        return set_jwt_cookies(response, access_token, refresh_token)

    def form_invalid(self, form):
        logger.warning(
            'User login failed email=%s ip=%s errors=%s',
            self.request.POST.get('email', ''),
            get_client_ip(self.request),
            form.errors.get_json_data(),
        )
        return super().form_invalid(form)


class AdminLoginView(FormView):
    template_name = 'auth/admin-login.html'
    form_class = AdminLoginForm
    success_url = reverse_lazy('auth:calendar')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        access_token, refresh_token = build_token_pair_for_user(form.user)
        logger.info(
            'Admin login success email=%s user_id=%s ip=%s',
            form.user.email,
            form.user.id,
            get_client_ip(self.request),
        )
        response = super().form_valid(form)
        return set_jwt_cookies(response, access_token, refresh_token)

    def form_invalid(self, form):
        logger.warning(
            'Admin login failed email=%s ip=%s errors=%s',
            self.request.POST.get('email', ''),
            get_client_ip(self.request),
            form.errors.get_json_data(),
        )
        return super().form_invalid(form)


class AdminPasswordResetStartView(FormView):
    template_name = 'auth/admin-password-reset-start.html'
    form_class = AdminPasswordResetStartForm
    success_url = reverse_lazy('auth:admin_password_reset_confirm')

    def form_valid(self, form):
        user = form.admin_user
        code = f'{secrets.randbelow(1000000):06d}'
        expires_at = timezone.now() + timedelta(minutes=10)

        reset_request = AdminPasswordResetRequest.objects.create(
            user=user,
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
            recipient_list=[user.email],
            fail_silently=False,
        )

        logger.info(
            'Admin password reset code sent email=%s user_id=%s ip=%s',
            user.email,
            user.id,
            get_client_ip(self.request),
        )
        messages.success(self.request, 'Confirmation code has been sent to your email.')
        return super().form_valid(form)

    def form_invalid(self, form):
        logger.warning(
            'Admin password reset start failed email=%s ip=%s errors=%s',
            self.request.POST.get('email', ''),
            get_client_ip(self.request),
            form.errors.get_json_data(),
        )
        return super().form_invalid(form)


class AdminPasswordResetConfirmView(FormView):
    template_name = 'auth/admin-password-reset-confirm.html'
    form_class = AdminPasswordResetConfirmForm
    success_url = reverse_lazy('auth:admin_password_reset_new_password')

    def dispatch(self, request, *args, **kwargs):
        if ADMIN_PASSWORD_RESET_SESSION_KEY not in request.session:
            return redirect('auth:admin_password_reset_start')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request_id = self.request.session.get(ADMIN_PASSWORD_RESET_SESSION_KEY)
        reset_request = AdminPasswordResetRequest.objects.select_related('user').filter(
            id=request_id,
            is_used=False,
        ).first()
        context['admin_email'] = reset_request.user.email if reset_request else ''
        return context

    def form_valid(self, form):
        request_id = self.request.session.get(ADMIN_PASSWORD_RESET_SESSION_KEY)
        reset_request = AdminPasswordResetRequest.objects.select_related('user').filter(
            id=request_id,
            is_used=False,
        ).first()
        if reset_request is None:
            logger.warning(
                'Admin password reset confirm failed missing_request request_id=%s ip=%s',
                request_id,
                get_client_ip(self.request),
            )
            form.add_error(None, form.error_messages['invalid_code'])
            return self.form_invalid(form)

        if reset_request.is_expired:
            logger.warning(
                'Admin password reset confirm failed expired request_id=%s user_id=%s ip=%s',
                request_id,
                reset_request.user_id,
                get_client_ip(self.request),
            )
            form.add_error(None, form.error_messages['expired_code'])
            return self.form_invalid(form)

        if form.cleaned_data['code'] != reset_request.code:
            logger.warning(
                'Admin password reset confirm failed wrong_code request_id=%s user_id=%s ip=%s',
                request_id,
                reset_request.user_id,
                get_client_ip(self.request),
            )
            form.add_error('code', form.error_messages['invalid_code'])
            return self.form_invalid(form)

        self.request.session[ADMIN_PASSWORD_RESET_CODE_VERIFIED_KEY] = True

        logger.info(
            'Admin password reset code confirmed email=%s user_id=%s ip=%s',
            reset_request.user.email,
            reset_request.user.id,
            get_client_ip(self.request),
        )
        return super().form_valid(form)

    def form_invalid(self, form):
        logger.warning(
            'Admin password reset confirm invalid request_id=%s ip=%s errors=%s',
            self.request.session.get(ADMIN_PASSWORD_RESET_SESSION_KEY),
            get_client_ip(self.request),
            form.errors.get_json_data(),
        )
        return super().form_invalid(form)


class AdminPasswordResetNewPasswordView(FormView):
    template_name = 'auth/admin-password-reset-new-password.html'
    form_class = AdminPasswordResetNewPasswordForm
    success_url = reverse_lazy('auth:admin_login')

    def dispatch(self, request, *args, **kwargs):
        if ADMIN_PASSWORD_RESET_SESSION_KEY not in request.session:
            return redirect('auth:admin_password_reset_start')
        if not request.session.get(ADMIN_PASSWORD_RESET_CODE_VERIFIED_KEY):
            return redirect('auth:admin_password_reset_confirm')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        request_id = self.request.session.get(ADMIN_PASSWORD_RESET_SESSION_KEY)
        reset_request = AdminPasswordResetRequest.objects.select_related('user').filter(
            id=request_id,
            is_used=False,
        ).first()
        if reset_request is None:
            form.add_error(None, 'Invalid confirmation request.')
            return self.form_invalid(form)

        if reset_request.is_expired:
            form.add_error(None, 'Confirmation code has expired. Request a new one.')
            return self.form_invalid(form)

        user = reset_request.user
        user.set_password(form.cleaned_data['password'])
        user.save(update_fields=['password'])

        reset_request.is_used = True
        reset_request.save(update_fields=['is_used'])
        self.request.session.pop(ADMIN_PASSWORD_RESET_SESSION_KEY, None)
        self.request.session.pop(ADMIN_PASSWORD_RESET_CODE_VERIFIED_KEY, None)

        logger.info(
            'Admin password updated email=%s user_id=%s ip=%s',
            user.email,
            user.id,
            get_client_ip(self.request),
        )
        messages.success(self.request, 'Password has been updated. You can sign in now.')
        return super().form_valid(form)


class RegisterView(FormView):
    template_name = 'auth/register.html'
    form_class = RegisterStepForm
    success_url = reverse_lazy('auth:register_password')

    def form_valid(self, form):
        logger.info(
            'Register step1 success email=%s phone=%s ip=%s',
            form.cleaned_data['email'],
            form.cleaned_data['phone'],
            get_client_ip(self.request),
        )
        self.request.session[REGISTER_SESSION_KEY] = {
            'first_name': form.cleaned_data['first_name'],
            'last_name': form.cleaned_data['last_name'],
            'birth_date': form.cleaned_data['birth_date'].isoformat(),
            'email': form.cleaned_data['email'],
            'phone': form.cleaned_data['phone'],
        }
        return super().form_valid(form)

    def form_invalid(self, form):
        logger.warning(
            'Register step1 failed email=%s phone=%s ip=%s errors=%s',
            self.request.POST.get('email', ''),
            self.request.POST.get('phone', ''),
            get_client_ip(self.request),
            form.errors.get_json_data(),
        )
        return super().form_invalid(form)


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
        if not signup_data:
            logger.warning(
                'Register step2 failed missing_session ip=%s',
                get_client_ip(self.request),
            )
            return redirect('auth:register')

        email = signup_data['email']
        if User.objects.filter(username__iexact=email).exists():
            form.add_error(None, 'Пользователь с таким email уже существует.')
            return self.form_invalid(form)

        try:
            user = User.objects.create_user(
                username=email,
                email=email,
                password=form.cleaned_data['password'],
                first_name=signup_data['first_name'],
                last_name=signup_data['last_name'],
                is_active=True,
            )
        except IntegrityError:
            form.add_error(None, 'Пользователь с таким email уже существует.')
            return self.form_invalid(form)
        EmailAddress.objects.add_email(self.request, user, email, confirm=True)
        self.request.session.pop(REGISTER_SESSION_KEY, None)
        logger.info(
            'Register step2 success user_created email=%s user_id=%s ip=%s',
            user.email,
            user.id,
            get_client_ip(self.request),
        )
        return super().form_valid(form)

    def form_invalid(self, form):
        logger.warning(
            'Register step2 failed email=%s ip=%s errors=%s',
            (self.request.session.get(REGISTER_SESSION_KEY) or {}).get('email', ''),
            get_client_ip(self.request),
            form.errors.get_json_data(),
        )
        return super().form_invalid(form)


class RegisterSuccessView(TemplateView):
    template_name = 'auth/register-success.html'

    def dispatch(self, request, *args, **kwargs):
        messages.success(
            request,
            'РњС‹ РѕС‚РїСЂР°РІРёР»Рё РїРёСЃСЊРјРѕ РЅР° email. РџРѕРґС‚РІРµСЂРґРёС‚Рµ СЂРµРіРёСЃС‚СЂР°С†РёСЋ РїРѕ СЃСЃС‹Р»РєРµ РёР· РїРёСЃСЊРјР°.',
        )
        return super().dispatch(request, *args, **kwargs)


class UserProtectedMixin:
    login_url = reverse_lazy('auth:login')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(self.login_url)
        return super().dispatch(request, *args, **kwargs)


class AdminProtectedMixin:
    login_url = reverse_lazy('auth:admin_login')
    fallback_url = reverse_lazy('auth:profile')
    permission_denied_message = 'Недостаточно прав для просмотра этой страницы.'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(self.login_url)
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, self.permission_denied_message)
            return redirect(self.fallback_url)
        return super().dispatch(request, *args, **kwargs)


class ProfileView(UserProtectedMixin, TemplateView):
    template_name = 'auth/profile.html'


class SettingsView(UserProtectedMixin, TemplateView):
    template_name = 'auth/settings.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        context['settings_name'] = f'{self.request.user.first_name} {self.request.user.last_name}'.strip() or self.request.user.email
        context['settings_email'] = self.request.user.email
        context['settings_first_name'] = self.request.user.first_name or ''
        context['settings_last_name'] = self.request.user.last_name or ''
        context['settings_birth_date'] = profile.birth_date.strftime('%d.%m.%Y') if profile.birth_date else ''
        context['telegram_linked'] = bool(profile.telegram_user_id)
        context['telegram_display'] = f"@{profile.telegram_username}" if profile.telegram_username else ''
        return context


class SupportView(UserProtectedMixin, TemplateView):
    template_name = 'auth/support.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['support_name'] = f'{self.request.user.first_name} {self.request.user.last_name}'.strip() or self.request.user.email
        context['support_experience'] = '8 лет'
        return context


class SupportMessageSentView(UserProtectedMixin, TemplateView):
    template_name = 'auth/support-sent.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['support_name'] = f'{self.request.user.first_name} {self.request.user.last_name}'.strip() or self.request.user.email
        context['support_experience'] = '8 лет'
        return context


class SupportSubmitView(UserProtectedMixin, View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        return redirect('auth:support_sent')


class UpdateProfileDataView(View):
    http_method_names = ['post']

    @staticmethod
    def _parse_birth_date(raw_value):
        value = str(raw_value or '').strip()
        if not value:
            return None
        for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                return timezone.datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        return 'invalid'

    def post(self, request, *args, **kwargs):
        user, auth_type = resolve_request_user(request)
        if user is None:
            return JsonResponse({'ok': False, 'error': 'auth_required'}, status=401)

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

        first_name = str(payload.get('first_name') or '').strip()
        last_name = str(payload.get('last_name') or '').strip()
        birth_date_raw = payload.get('birth_date')

        if not first_name:
            return JsonResponse({'ok': False, 'error': 'first_name_required'}, status=400)
        if not last_name:
            return JsonResponse({'ok': False, 'error': 'last_name_required'}, status=400)
        if len(first_name) > 150 or len(last_name) > 150:
            return JsonResponse({'ok': False, 'error': 'name_too_long'}, status=400)

        parsed_birth_date = self._parse_birth_date(birth_date_raw)
        if parsed_birth_date == 'invalid':
            return JsonResponse({'ok': False, 'error': 'invalid_birth_date'}, status=400)

        user.first_name = first_name
        user.last_name = last_name
        user.save(update_fields=['first_name', 'last_name'])

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.birth_date = parsed_birth_date
        profile.save(update_fields=['birth_date', 'updated_at'])

        logger.info(
            'Profile data updated user_id=%s email=%s auth=%s ip=%s',
            user.id,
            user.email,
            auth_type,
            get_client_ip(request),
        )
        return JsonResponse({
            'ok': True,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'birth_date': profile.birth_date.strftime('%d.%m.%Y') if profile.birth_date else '',
        })


class StartTelegramLinkView(View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        user, auth_type = resolve_request_user(request)
        if user is None:
            return JsonResponse({'ok': False, 'error': 'auth_required'}, status=401)

        deep_link_bot = (settings.TELEGRAM_BOT_USERNAME or '').strip()
        if not deep_link_bot:
            return JsonResponse({'ok': False, 'error': 'telegram_not_configured'}, status=400)

        profile, _ = UserProfile.objects.get_or_create(user=user)
        if profile.telegram_user_id:
            return JsonResponse(
                {
                    'ok': True,
                    'already_linked': True,
                    'linked': True,
                    'telegram_username': profile.telegram_username or '',
                }
            )

        token = secrets.token_urlsafe(24)
        expires_at = timezone.now() + timedelta(minutes=TELEGRAM_LINK_TTL_MINUTES)
        profile.telegram_link_token = token
        profile.telegram_link_expires_at = expires_at
        profile.save(update_fields=['telegram_link_token', 'telegram_link_expires_at', 'updated_at'])

        link_url = build_telegram_deep_link(token)
        logger.info(
            'Telegram link started user_id=%s email=%s auth=%s ip=%s',
            user.id,
            user.email,
            auth_type,
            get_client_ip(request),
        )
        return JsonResponse(
            {
                'ok': True,
                'linked': False,
                'deep_link': link_url,
                'expires_at': expires_at.isoformat(),
                'ttl_seconds': TELEGRAM_LINK_TTL_MINUTES * 60,
            }
        )


class TelegramLinkStatusView(View):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        user, _ = resolve_request_user(request)
        if user is None:
            return JsonResponse({'ok': False, 'error': 'auth_required'}, status=401)

        profile, _ = UserProfile.objects.get_or_create(user=user)
        is_pending = bool(profile.telegram_link_token and profile.telegram_link_expires_at and profile.telegram_link_expires_at > timezone.now())
        return JsonResponse(
            {
                'ok': True,
                'linked': bool(profile.telegram_user_id),
                'pending': is_pending,
                'telegram_username': profile.telegram_username or '',
                'telegram_first_name': profile.telegram_first_name or '',
            }
        )


@method_decorator(csrf_exempt, name='dispatch')
class TelegramWebhookView(View):
    http_method_names = ['post']

    @staticmethod
    def _extract_start_token(text):
        content = str(text or '').strip()
        if not content:
            return ''
        if not content.startswith('/start'):
            return ''

        parts = content.split(maxsplit=1)
        if len(parts) < 2:
            return ''
        payload = parts[1].strip()
        if payload.startswith('link_'):
            return payload.replace('link_', '', 1).strip()
        return ''

    def post(self, request, *args, **kwargs):
        configured_secret = (settings.TELEGRAM_WEBHOOK_SECRET or '').strip()
        if configured_secret:
            incoming_secret = (request.headers.get('X-Telegram-Bot-Api-Secret-Token') or '').strip()
            if incoming_secret != configured_secret:
                logger.warning('Telegram webhook denied invalid secret ip=%s', get_client_ip(request))
                return JsonResponse({'ok': False, 'error': 'invalid_secret'}, status=403)

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

        message = payload.get('message') or payload.get('edited_message') or {}
        from_user = message.get('from') or {}
        telegram_user_id = from_user.get('id')
        token = self._extract_start_token(message.get('text'))

        if not telegram_user_id or not token:
            return JsonResponse({'ok': True})

        now = timezone.now()
        profile = (
            UserProfile.objects.select_related('user')
            .filter(telegram_link_token=token, telegram_link_expires_at__gt=now)
            .first()
        )
        if profile is None:
            logger.warning(
                'Telegram link failed token_not_found tg_user_id=%s ip=%s',
                telegram_user_id,
                get_client_ip(request),
            )
            return JsonResponse({'ok': True})

        already_bound = (
            UserProfile.objects.exclude(pk=profile.pk)
            .filter(telegram_user_id=telegram_user_id)
            .exists()
        )
        if already_bound:
            logger.warning(
                'Telegram link failed already_bound tg_user_id=%s target_user_id=%s ip=%s',
                telegram_user_id,
                profile.user_id,
                get_client_ip(request),
            )
            return JsonResponse({'ok': True})

        profile.telegram_user_id = int(telegram_user_id)
        profile.telegram_username = str(from_user.get('username') or '')
        profile.telegram_first_name = str(from_user.get('first_name') or '')
        profile.telegram_last_name = str(from_user.get('last_name') or '')
        profile.telegram_link_token = ''
        profile.telegram_link_expires_at = None
        profile.telegram_linked_at = now
        profile.save(
            update_fields=[
                'telegram_user_id',
                'telegram_username',
                'telegram_first_name',
                'telegram_last_name',
                'telegram_link_token',
                'telegram_link_expires_at',
                'telegram_linked_at',
                'updated_at',
            ]
        )
        logger.info(
            'Telegram linked success user_id=%s email=%s tg_user_id=%s ip=%s',
            profile.user_id,
            profile.user.email,
            profile.telegram_user_id,
            get_client_ip(request),
        )
        return JsonResponse({'ok': True})


class ProfileAwardsTestsView(UserProtectedMixin, TemplateView):
    template_name = 'auth/profile-awards-tests.html'


class ProfileAwardWorkoutView(UserProtectedMixin, TemplateView):
    template_name = 'auth/profile-award-workout.html'

    @staticmethod
    def _format_result_value(result):
        if result is None:
            return '--'
        minutes = result.minutes
        seconds = result.seconds
        if minutes is None and seconds is None:
            return '--'
        if minutes is None:
            return str(seconds)
        if seconds is None:
            return str(minutes)
        return f'{minutes}x{seconds}'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sections_meta = [
            (TrainingResult.SECTION_STRENGTH, 'РЎРёР»РѕРІР°СЏ'),
            (TrainingResult.SECTION_CARDIO, 'РљР°СЂРґРёРѕ'),
            (TrainingResult.SECTION_METABOLIC, 'РњРµС‚Р°Р±РѕР»РёС‡РµСЃРєР°СЏ'),
        ]
        result_sections = [
            {'key': key, 'title': title, 'value': '--', 'mode': '--'}
            for key, title in sections_meta
        ]

        if self.request.user.is_authenticated:
            latest_result = (
                TrainingResult.objects
                .filter(user=self.request.user)
                .order_by('-training_date', '-updated_at')
                .first()
            )
            if latest_result:
                latest_date = latest_result.training_date
                latest_results = {
                    item.section: item
                    for item in TrainingResult.objects.filter(
                        user=self.request.user,
                        training_date=latest_date,
                    )
                }
                result_sections = []
                for key, title in sections_meta:
                    item = latest_results.get(key)
                    result_sections.append(
                        {
                            'key': key,
                            'title': title,
                            'value': self._format_result_value(item),
                            'mode': item.get_mode_display() if item else '--',
                        }
                    )

        context['result_sections'] = result_sections
        return context


class CalendarView(AdminProtectedMixin, TemplateView):
    template_name = 'auth/calendar.html'


class StatisticsView(AdminProtectedMixin, TemplateView):
    template_name = 'auth/statistics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['exercise_rows'] = [
            {'exercise': 'Смит 80%', 'training': 'На все тело', 'results': 5, 'reviews': 5, 'rating': '4,8'},
            {'exercise': 'Смит 80%', 'training': 'На все тело', 'results': 5, 'reviews': 5, 'rating': '4,8'},
            {'exercise': 'Смит 80%', 'training': 'На все тело', 'results': 5, 'reviews': 5, 'rating': '4,8'},
            {'exercise': 'Смит 80%', 'training': 'На все тело', 'results': 5, 'reviews': 5, 'rating': '4,8'},
            {'exercise': 'Смит 80%', 'training': 'На все тело', 'results': 5, 'reviews': 5, 'rating': '4,8'},
            {'exercise': 'Смит 80%', 'training': 'На все тело', 'results': 5, 'reviews': 5, 'rating': '4,8'},
        ]
        context['activity_rows'] = [
            {'name': 'Виктория С.', 'trainings': 19, 'received': 12, 'sent': 72},
            {'name': 'Сергей Т.', 'trainings': 20, 'received': 10, 'sent': 50},
            {'name': 'Евгений Л.', 'trainings': 84, 'received': 9, 'sent': 38},
            {'name': 'Виктория К.', 'trainings': 23, 'received': 8, 'sent': 35},
            {'name': 'Семен Р.', 'trainings': 84, 'received': 6, 'sent': 21},
            {'name': 'Анатолий Б.', 'trainings': 92, 'received': 5, 'sent': 20},
        ]
        context['achievement_rows'] = [
            {'name': 'Р’РёРєС‚РѕСЂРёСЏ РЎ.', 'visited': 10, 'goal': 10},
            {'name': 'РЎРµСЂРіРµР№ Рў.', 'visited': 8, 'goal': 8},
            {'name': 'Р•РІРіРµРЅРёР№ Р›.', 'visited': 6, 'goal': 7},
            {'name': 'Р’РёРєС‚РѕСЂРёСЏ Рљ.', 'visited': 6, 'goal': 7},
            {'name': 'РЎРµРјРµРЅ Р .', 'visited': 5, 'goal': 6},
            {'name': 'РђРЅР°С‚РѕР»РёР№ Р‘.', 'visited': 1, 'goal': 2},
        ]
        return context


class ReviewsOverviewView(AdminProtectedMixin, TemplateView):
    template_name = 'auth/reviews-overview.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['review_cards'] = [
            {'color': 'orange'},
            {'color': 'violet'},
            {'color': 'orange'},
            {'color': 'green'},
            {'color': 'green'},
            {'color': 'orange'},
            {'color': 'violet'},
            {'color': 'orange'},
        ]
        return context


class AdminProfileView(AdminProtectedMixin, TemplateView):
    template_name = 'auth/admin-profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        admin_contact = AdminContact.objects.filter(user=user).first()

        first_name = (user.first_name or 'Ксения').strip() or 'Ксения'
        last_name = (user.last_name or 'Иванова').strip() or 'Иванова'
        email = (user.email or 'admin@example.com').strip() or 'admin@example.com'
        phone = '+7 (999) 123-45-67'
        if admin_contact and admin_contact.phone:
            phone = admin_contact.phone

        initials = ''.join(part[:1] for part in [first_name, last_name] if part).upper()[:2] or 'AM'

        context['admin_profile'] = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone': phone,
            'initials': initials,
        }
        return context


class LibraryView(AdminProtectedMixin, TemplateView):
    template_name = 'auth/library.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['library_items'] = [
            {
                'name_ru': 'Аманда',
                'name_en': 'Amanda',
                'description_ru': '9-7-5 повторений на время: Выходы на кольцах Приседания со штангой (61/43 кг)',
                'description_en': '9-7-5 reps for time: Ring muscle-ups Squats with a barbell (61/43 kg)',
                'video_count': 5,
            },
            {
                'name_ru': 'Синди',
                'name_en': 'Cindy',
                'description_ru': '20 минут AMRAP: 5 подтягиваний 10 отжиманий 15 приседаний',
                'description_en': '20 minutes AMRAP: 5 pull-ups 10 push-ups 15 squats',
                'video_count': 3,
            },
            {
                'name_ru': 'Фрэн',
                'name_en': 'Fran',
                'description_ru': '21-15-9 повторений на время: Трастеры (43/29 кг) Подтягивания',
                'description_en': '21-15-9 reps for time: Thrusters (43/29 kg) Pull-ups',
                'video_count': 8,
            },
        ]
        return context


class SaveTrainingResultsView(View):
    http_method_names = ['post']

    @staticmethod
    def _parse_positive_int(value):
        if value in (None, ''):
            return None
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        if parsed < 0:
            return None
        return parsed

    def post(self, request, *args, **kwargs):
        user, auth_type = resolve_request_user(request)
        if user is None:
            logger.warning(
                'Training results save denied unauthenticated ip=%s',
                get_client_ip(request),
            )
            return JsonResponse({'ok': False, 'error': 'auth_required'}, status=401)

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

        raw_date = payload.get('date')
        if raw_date:
            try:
                training_date = timezone.datetime.strptime(raw_date, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'ok': False, 'error': 'invalid_date'}, status=400)
        else:
            training_date = timezone.localdate()

        results = payload.get('results') or {}
        if not isinstance(results, dict):
            return JsonResponse({'ok': False, 'error': 'invalid_results'}, status=400)

        valid_sections = {key for key, _ in TrainingResult.SECTION_CHOICES}
        valid_modes = {key for key, _ in TrainingResult.MODE_CHOICES}
        saved_count = 0

        for section_key, section_payload in results.items():
            if section_key not in valid_sections:
                return JsonResponse({'ok': False, 'error': f'invalid_section:{section_key}'}, status=400)
            if not isinstance(section_payload, dict):
                return JsonResponse({'ok': False, 'error': f'invalid_section_payload:{section_key}'}, status=400)

            mode = str(section_payload.get('mode') or TrainingResult.MODE_RX).lower()
            if mode not in valid_modes:
                return JsonResponse({'ok': False, 'error': f'invalid_mode:{section_key}'}, status=400)

            minutes = self._parse_positive_int(section_payload.get('minutes'))
            seconds = self._parse_positive_int(section_payload.get('seconds'))

            if minutes is None and seconds is None:
                continue

            if seconds is not None and seconds > 59:
                return JsonResponse({'ok': False, 'error': f'invalid_seconds:{section_key}'}, status=400)

            TrainingResult.objects.update_or_create(
                user=user,
                training_date=training_date,
                section=section_key,
                defaults={
                    'minutes': minutes,
                    'seconds': seconds,
                    'mode': mode,
                },
            )
            saved_count += 1

        logger.info(
            'Training results saved user_id=%s email=%s date=%s saved=%s auth=%s ip=%s',
            user.id,
            user.email,
            training_date.isoformat(),
            saved_count,
            auth_type,
            get_client_ip(request),
        )
        return JsonResponse({'ok': True, 'saved': saved_count, 'date': training_date.isoformat()})


class SaveTrainingRateView(View):
    http_method_names = ['post']

    @staticmethod
    def _parse_rate(value):
        try:
            rating = int(value)
        except (TypeError, ValueError):
            return None
        if rating < 1 or rating > 5:
            return None
        return rating

    def post(self, request, *args, **kwargs):
        user, auth_type = resolve_request_user(request)
        if user is None:
            logger.warning(
                'Training rate save denied unauthenticated ip=%s',
                get_client_ip(request),
            )
            return JsonResponse({'ok': False, 'error': 'auth_required'}, status=401)

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

        raw_date = payload.get('date')
        if raw_date:
            try:
                training_date = timezone.datetime.strptime(raw_date, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'ok': False, 'error': 'invalid_date'}, status=400)
        else:
            training_date = timezone.localdate()

        ratings = payload.get('ratings') or {}
        if not isinstance(ratings, dict):
            return JsonResponse({'ok': False, 'error': 'invalid_ratings'}, status=400)

        overall = self._parse_rate(ratings.get('overall'))
        strength = self._parse_rate(ratings.get('strength'))
        cardio = self._parse_rate(ratings.get('cardio'))
        metabolic = self._parse_rate(ratings.get('metabolic'))
        if None in (overall, strength, cardio, metabolic):
            return JsonResponse({'ok': False, 'error': 'invalid_rating_value'}, status=400)

        comment = str(payload.get('comment') or '').strip()
        if len(comment) > 1000:
            return JsonResponse({'ok': False, 'error': 'comment_too_long'}, status=400)

        TrainingRate.objects.update_or_create(
            user=user,
            training_date=training_date,
            defaults={
                'overall': overall,
                'strength': strength,
                'cardio': cardio,
                'metabolic': metabolic,
                'comment': comment,
            },
        )

        logger.info(
            'Training rate saved user_id=%s email=%s date=%s auth=%s ip=%s',
            user.id,
            user.email,
            training_date.isoformat(),
            auth_type,
            get_client_ip(request),
        )
        return JsonResponse({'ok': True, 'date': training_date.isoformat()})


class DownloadTrainingResultsImageView(View):
    http_method_names = ['post']

    @staticmethod
    def _safe_int(value):
        if value in (None, ''):
            return None
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        if number < 0:
            return None
        return number

    @staticmethod
    def _format_value(entry):
        if not isinstance(entry, dict):
            return '--'
        minutes = DownloadTrainingResultsImageView._safe_int(entry.get('minutes'))
        seconds = DownloadTrainingResultsImageView._safe_int(entry.get('seconds'))
        if minutes is None and seconds is None:
            return '--'
        if minutes is None:
            return str(seconds)
        if seconds is None:
            return str(minutes)
        return f'{minutes}x{seconds}'

    @staticmethod
    def _load_font(size, bold=False):
        font_candidates = [
            'C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf',
            'C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf',
        ]
        for path in font_candidates:
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'ok': False, 'error': 'auth_required'}, status=401)

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

        raw_date = payload.get('date')
        if raw_date:
            try:
                training_date = timezone.datetime.strptime(raw_date, '%Y-%m-%d').date()
            except ValueError:
                training_date = timezone.localdate()
        else:
            training_date = timezone.localdate()

        results = payload.get('results') or {}
        cardio_value = self._format_value(results.get('cardio'))
        strength_value = self._format_value(results.get('strength'))
        metabolic_value = self._format_value(results.get('metabolic'))
        image = Image.new('RGB', (1080, 1350), '#f5f5f5')
        draw = ImageDraw.Draw(image)

        # Match modal typography proportions (12px UI text scaled for export image).
        font_title = self._load_font(34, bold=True)
        font_label = self._load_font(30, bold=False)
        font_value = self._load_font(30, bold=False)
        font_date = self._load_font(30, bold=False)
        font_btn = self._load_font(30, bold=False)

        card_x, card_y, card_w, card_h = 75, 80, 930, 1190
        draw.rounded_rectangle((card_x, card_y, card_x + card_w, card_y + card_h), radius=32, fill='#ffffff')

        summary_x, summary_y, summary_w, summary_h = 145, 260, 790, 650
        draw.rounded_rectangle(
            (summary_x, summary_y, summary_x + summary_w, summary_y + summary_h),
            radius=32,
            fill='#f0f0f0',
        )

        title = 'Результаты тренировки'
        title_box = draw.textbbox((0, 0), title, font=font_title)
        title_w = title_box[2] - title_box[0]
        draw.text((summary_x + (summary_w - title_w) / 2, summary_y + 72), title, font=font_title, fill='#242d35')

        row_specs = [
            ('Кардио', cardio_value),
            ('Силовая', strength_value),
            ('Метаболическая', metabolic_value),
        ]
        row_x, row_w, row_h = summary_x + 50, summary_w - 100, 106
        first_row_y = summary_y + 160
        row_gap = 32

        for index, (label, value) in enumerate(row_specs):
            y = first_row_y + index * (row_h + row_gap)
            draw.rounded_rectangle((row_x, y, row_x + row_w, y + row_h), radius=24, fill='#ffffff')
            draw.text((row_x + 36, y + 34), label, font=font_label, fill='#252d35')
            value_box = draw.textbbox((0, 0), value, font=font_value)
            value_w = value_box[2] - value_box[0]
            draw.text((row_x + row_w - 36 - value_w, y + 34), value, font=font_value, fill='#252d35')

        month_names = {
            1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля', 5: 'мая', 6: 'июня',
            7: 'июля', 8: 'августа', 9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря',
        }
        pretty_date = f"{training_date.day} {month_names.get(training_date.month, '')} {training_date.year} г."
        date_box = draw.textbbox((0, 0), pretty_date, font=font_date)
        date_w = date_box[2] - date_box[0]
        draw.text((summary_x + (summary_w - date_w) / 2, summary_y + summary_h - 74), pretty_date, font=font_date, fill='#363f47')

        buffer = BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)

        filename = f'training-results-{training_date.isoformat()}.png'
        response = HttpResponse(buffer.getvalue(), content_type='image/png')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class LogoutView(View):
    http_method_names = ['get', 'post']

    def dispatch(self, request, *args, **kwargs):
        access_cookie_name, refresh_cookie_name = get_jwt_cookie_names()
        refresh_token = request.COOKIES.get(refresh_cookie_name)
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                logger.warning(
                    'Logout blacklist failed invalid_refresh ip=%s',
                    get_client_ip(request),
                )

        response = redirect('auth:login')
        clear_jwt_cookies(response)
        return response


class LeaderboardDayView(UserProtectedMixin, TemplateView):
    template_name = 'auth/leaderboard-day.html'


class CommunityView(UserProtectedMixin, TemplateView):
    template_name = 'auth/community.html'

    @staticmethod
    def _format_training_value(result):
        minutes = result.minutes
        seconds = result.seconds
        if minutes is None and seconds is None:
            return '--'
        if minutes is not None and seconds is not None:
            return f'{minutes} min {seconds} sec'
        if minutes is not None:
            return f'{minutes} min'
        return f'{seconds} sec'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['community_name'] = (
            f'{self.request.user.first_name} {self.request.user.last_name}'.strip()
            or self.request.user.email
        )
        context['community_experience'] = '8 years'

        today = timezone.localdate()
        section_meta = [
            (TrainingResult.SECTION_STRENGTH, 'Strength'),
            (TrainingResult.SECTION_CARDIO, 'Cardio'),
            (TrainingResult.SECTION_METABOLIC, 'Metabolic'),
        ]
        section_titles = dict(section_meta)
        reaction_counts = dict(
            CommunityReaction.objects
            .filter(training_date=today)
            .values('target_user_id')
            .annotate(total=Count('id'))
            .values_list('target_user_id', 'total')
        )
        my_reacted_user_ids = set(
            CommunityReaction.objects
            .filter(training_date=today, sender=self.request.user)
            .values_list('target_user_id', flat=True)
        )

        grouped = {}
        day_results = (
            TrainingResult.objects
            .select_related('user')
            .filter(training_date=today)
            .order_by('-updated_at', 'user_id')
        )
        for item in day_results:
            user_id = item.user_id
            if user_id not in grouped:
                user_name = f'{item.user.first_name} {item.user.last_name}'.strip() or item.user.email
                grouped[user_id] = {
                    'target_user_id': user_id,
                    'user_name': user_name,
                    'sections': {key: {'title': title, 'value': '--', 'mode': '--'} for key, title in section_meta},
                }

            grouped[user_id]['sections'][item.section] = {
                'title': section_titles[item.section],
                'value': self._format_training_value(item),
                'mode': item.get_mode_display(),
            }

        cards = []
        for payload in grouped.values():
            cards.append(
                {
                    'target_user_id': payload['target_user_id'],
                    'user_name': payload['user_name'],
                    'reactions_count': reaction_counts.get(payload['target_user_id'], 0),
                    'reacted_by_me': payload['target_user_id'] in my_reacted_user_ids,
                    'sections': [
                        payload['sections'][TrainingResult.SECTION_STRENGTH],
                        payload['sections'][TrainingResult.SECTION_CARDIO],
                        payload['sections'][TrainingResult.SECTION_METABOLIC],
                    ],
                }
            )

        context['community_date'] = today.strftime('%d.%m.%Y')
        context['community_cards'] = cards
        return context


class ToggleCommunityReactionView(View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        user, _ = resolve_request_user(request)
        if user is None:
            return JsonResponse({'ok': False, 'error': 'auth_required'}, status=401)

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

        target_user_id_raw = payload.get('target_user_id')
        try:
            target_user_id = int(target_user_id_raw)
        except (TypeError, ValueError):
            return JsonResponse({'ok': False, 'error': 'invalid_target_user_id'}, status=400)

        target_user = User.objects.filter(id=target_user_id).first()
        if target_user is None:
            return JsonResponse({'ok': False, 'error': 'target_user_not_found'}, status=404)

        today = timezone.localdate()
        if not TrainingResult.objects.filter(user=target_user, training_date=today).exists():
            return JsonResponse({'ok': False, 'error': 'target_has_no_results_today'}, status=400)

        reaction, created = CommunityReaction.objects.get_or_create(
            sender=user,
            target_user=target_user,
            training_date=today,
        )
        if created:
            reacted = True
        else:
            reaction.delete()
            reacted = False

        reactions_count = CommunityReaction.objects.filter(
            target_user=target_user,
            training_date=today,
        ).count()
        return JsonResponse({
            'ok': True,
            'reacted': reacted,
            'reactions_count': reactions_count,
            'target_user_id': target_user_id,
            'date': today.isoformat(),
        })


class TrainingPlanTodayView(UserProtectedMixin, TemplateView):
    template_name = 'auth/training-plan-today.html'


class AchievementsView(UserProtectedMixin, TemplateView):
    template_name = 'auth/achievements.html'


class AchievementExerciseView(UserProtectedMixin, TemplateView):
    template_name = 'auth/achievement-exercise.html'

    EXERCISE_DATA = {
        'back-pause-squat': {
            'title': 'Back Pause Squat',
            'max': [10, 10, 10, 10],
            'percent_rows': [
                [('10', '105%'), ('20', '100%'), ('15', '95%'), ('4', '90%')],
                [('10', '85%'), ('20', '80%'), ('15', '75%'), ('4', '70%')],
                [('10', '65%'), ('20', '60%'), ('15', '55%'), ('4', '50%')],
                [('10', '45%'), ('20', '40%'), ('15', '35%'), ('4', '30%')],
            ],
        },
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slug = self.kwargs.get('exercise_slug', '')
        data = self.EXERCISE_DATA.get(slug)
        if data is None:
            title = slug.replace('-', ' ').title()
            data = {
                'title': title,
                'max': ['--', '--', '--', '--'],
                'percent_rows': [
                    [('--', '105%'), ('--', '100%'), ('--', '95%'), ('--', '90%')],
                    [('--', '85%'), ('--', '80%'), ('--', '75%'), ('--', '70%')],
                    [('--', '65%'), ('--', '60%'), ('--', '55%'), ('--', '50%')],
                    [('--', '45%'), ('--', '40%'), ('--', '35%'), ('--', '30%')],
                ],
            }
        context['exercise'] = data
        return context

