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
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.views.generic import FormView, TemplateView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from .forms import (
    AdminLoginForm,
    AdminPasswordResetConfirmForm,
    AdminPasswordResetStartForm,
    LoginForm,
    RegisterPasswordForm,
    RegisterStepForm,
)
from .jwt_utils import build_token_pair_for_user, clear_jwt_cookies, get_jwt_cookie_names, set_jwt_cookies
from .models import AdminPasswordResetRequest, TrainingRate, TrainingResult

REGISTER_SESSION_KEY = 'register_step_data'
ADMIN_PASSWORD_RESET_SESSION_KEY = 'admin_password_reset_request_id'
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
    success_url = reverse_lazy('auth:profile')

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

        logger.info(
            'Admin password reset code sent email=%s user_id=%s ip=%s',
            contact.user.email,
            contact.user.id,
            get_client_ip(self.request),
        )
        messages.success(self.request, 'Confirmation code has been sent to your email.')
        return super().form_valid(form)

    def form_invalid(self, form):
        logger.warning(
            'Admin password reset start failed phone=%s ip=%s errors=%s',
            self.request.POST.get('phone', ''),
            get_client_ip(self.request),
            form.errors.get_json_data(),
        )
        return super().form_invalid(form)


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

        user = reset_request.user
        user.set_password(form.cleaned_data['password'])
        user.save(update_fields=['password'])

        reset_request.is_used = True
        reset_request.save(update_fields=['is_used'])
        self.request.session.pop(ADMIN_PASSWORD_RESET_SESSION_KEY, None)

        logger.info(
            'Admin password updated email=%s user_id=%s ip=%s',
            user.email,
            user.id,
            get_client_ip(self.request),
        )
        messages.success(self.request, 'Password has been updated. You can sign in now.')
        return super().form_valid(form)

    def form_invalid(self, form):
        logger.warning(
            'Admin password reset confirm invalid request_id=%s ip=%s errors=%s',
            self.request.session.get(ADMIN_PASSWORD_RESET_SESSION_KEY),
            get_client_ip(self.request),
            form.errors.get_json_data(),
        )
        return super().form_invalid(form)


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


class JwtProtectedMixin:
    login_url = reverse_lazy('auth:login')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(self.login_url)
        return super().dispatch(request, *args, **kwargs)


class ProfileView(JwtProtectedMixin, TemplateView):
    template_name = 'auth/profile.html'


class ProfileAwardsTestsView(JwtProtectedMixin, TemplateView):
    template_name = 'auth/profile-awards-tests.html'


class ProfileAwardWorkoutView(JwtProtectedMixin, TemplateView):
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


class CalendarView(JwtProtectedMixin, TemplateView):
    template_name = 'auth/calendar.html'


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


class LeaderboardDayView(JwtProtectedMixin, TemplateView):
    template_name = 'auth/leaderboard-day.html'


class CommunityView(JwtProtectedMixin, TemplateView):
    template_name = 'auth/community.html'


class TrainingPlanTodayView(JwtProtectedMixin, TemplateView):
    template_name = 'auth/training-plan-today.html'


class AchievementsView(JwtProtectedMixin, TemplateView):
    template_name = 'auth/achievements.html'


class AchievementExerciseView(JwtProtectedMixin, TemplateView):
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

