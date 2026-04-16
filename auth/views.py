import secrets
import logging
import json
import re
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

from allauth.account.models import EmailAddress
from PIL import Image, ImageDraw, ImageFont
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.core import signing
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
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
    AdminLibraryItem,
    AdminTraining,
    AdminTrainingExercise,
    AdminPasswordResetRequest,
    CommunityReaction,
    TrainingRate,
    TrainingResult,
    UserExerciseRepProfile,
    UserProfile,
)

REGISTER_SESSION_KEY = 'register_step_data'
ADMIN_PASSWORD_RESET_SESSION_KEY = 'admin_password_reset_request_id'
ADMIN_PASSWORD_RESET_CODE_VERIFIED_KEY = 'admin_password_reset_code_verified'
ADMIN_PASSWORD_RESET_LINK_SALT = 'admin_password_reset_link_v1'
TELEGRAM_LINK_TTL_MINUTES = 10
logger = logging.getLogger(__name__)

RU_WEEKDAY = {
    0: 'Понедельник',
    1: 'Вторник',
    2: 'Среда',
    3: 'Четверг',
    4: 'Пятница',
    5: 'Суббота',
    6: 'Воскресенье',
}

RU_WEEKDAY_SHORT = {
    0: 'Пн',
    1: 'Вт',
    2: 'Ср',
    3: 'Чт',
    4: 'Пт',
    5: 'Сб',
    6: 'Вс',
}

TRAINING_DIRECTION_LABELS = {
    AdminTraining.DIRECTION_FBB: 'FBB',
    AdminTraining.DIRECTION_CROSSFIT: 'Кроссфит с Денисом Залозним',
    AdminTraining.DIRECTION_GYMNASTICS: 'Гимнастика',
    AdminTraining.DIRECTION_WORKOUT: 'Воркаут дня',
}

TRAINING_BLOCK_LABELS = {
    AdminTrainingExercise.BLOCK_STRENGTH: 'Силовая',
    AdminTrainingExercise.BLOCK_CARDIO: 'Кардио',
    AdminTrainingExercise.BLOCK_GYMNASTICS: 'Гимнастика',
    AdminTrainingExercise.BLOCK_CUSTOM: 'Свое название',
}

TRAINING_RESULT_TYPE_LABELS = {
    AdminTrainingExercise.RESULT_TIME: 'Время',
    AdminTrainingExercise.RESULT_WEIGHT: 'Вес',
    AdminTrainingExercise.RESULT_REPS: 'Кол-во повторений',
}

EXERCISE_KIND_LABELS = {
    'exercise': 'Упражнение',
    'benchmarks': 'Benchmarks',
}

RESULT_TYPE_UNITS = {
    TrainingResult.RESULT_TIME: 'мин',
    TrainingResult.RESULT_WEIGHT: 'кг',
    TrainingResult.RESULT_REPS: 'повт',
}

RESULT_MODAL_TYPE_CONFIG = {
    AdminTrainingExercise.RESULT_TIME: {
        'primary_label': 'Минуты',
        'primary_placeholder': 'мин.',
        'secondary_label': 'Секунды',
        'secondary_placeholder': 'сек.',
        'show_secondary': True,
    },
    AdminTrainingExercise.RESULT_WEIGHT: {
        'primary_label': 'Вес',
        'primary_placeholder': 'кг',
        'secondary_label': '',
        'secondary_placeholder': '',
        'show_secondary': False,
    },
    AdminTrainingExercise.RESULT_REPS: {
        'primary_label': 'Количество',
        'primary_placeholder': 'Количество',
        'secondary_label': 'Подходы',
        'secondary_placeholder': 'Подходы',
        'show_secondary': True,
    },
}


def format_admin_training_volume(exercise):
    sets = exercise.sets
    reps = exercise.reps
    if sets is None and reps is None:
        return exercise.exercise_name
    if sets is None or reps is None:
        return exercise.exercise_name
    return f'{exercise.exercise_name} {sets}x{reps}'


def get_plan_result_type_map(trainings):
    result_map = {
        TrainingResult.SECTION_STRENGTH: TrainingResult.RESULT_TIME,
        TrainingResult.SECTION_CARDIO: TrainingResult.RESULT_TIME,
        TrainingResult.SECTION_METABOLIC: TrainingResult.RESULT_TIME,
    }
    block_to_section = {
        AdminTrainingExercise.BLOCK_STRENGTH: TrainingResult.SECTION_STRENGTH,
        AdminTrainingExercise.BLOCK_CARDIO: TrainingResult.SECTION_CARDIO,
        AdminTrainingExercise.BLOCK_GYMNASTICS: TrainingResult.SECTION_METABOLIC,
    }

    for training in trainings:
        for exercise in training.exercises.all():
            section_key = block_to_section.get(exercise.block_type)
            if not section_key:
                continue
            result_map[section_key] = exercise.result_type or TrainingResult.RESULT_TIME
    return result_map


def get_admin_training_title(direction, source_type, ready_plan_title):
    if source_type == AdminTraining.SOURCE_READY and ready_plan_title:
        return ready_plan_title.strip()
    return TRAINING_DIRECTION_LABELS.get(direction, 'FBB')


def serialize_admin_training(training):
    date_value = training.training_date
    exercises_payload = []
    grouped_sections = []
    section_index = {}

    for item in training.exercises.all():
        block_label = item.block_custom_name.strip() if item.block_type == AdminTrainingExercise.BLOCK_CUSTOM else TRAINING_BLOCK_LABELS.get(item.block_type, 'Силовая')
        exercise_payload = {
            'id': item.id,
            'block_type': item.block_type,
            'block_custom_name': item.block_custom_name,
            'block_label': block_label,
            'exercise_name': item.exercise_name,
            'exercise_kind': (
                item.exercise_kind
                if str(item.exercise_kind or '').strip().lower() in EXERCISE_KIND_LABELS
                else 'exercise'
            ),
            'sets': item.sets,
            'reps': item.reps,
            'result_type': item.result_type,
            'result_type_label': TRAINING_RESULT_TYPE_LABELS.get(item.result_type, 'Время'),
            'order': item.order,
            'volume': format_admin_training_volume(item),
        }
        exercises_payload.append(exercise_payload)

        if block_label not in section_index:
            section_index[block_label] = len(grouped_sections)
            grouped_sections.append({'title': block_label, 'items': []})
        grouped_sections[section_index[block_label]]['items'].append(exercise_payload['volume'])

    first_exercise = exercises_payload[0] if exercises_payload else None
    training_title = get_admin_training_title(
        training.direction,
        training.source_type,
        training.ready_plan_title,
    )
    return {
        'id': training.id,
        'date': date_value.isoformat(),
        'date_label': date_value.strftime('%d.%m.%Y'),
        'day_name': RU_WEEKDAY.get(date_value.weekday(), ''),
        'day_number': date_value.day,
        'direction': training.direction,
        'direction_label': TRAINING_DIRECTION_LABELS.get(training.direction, training.direction),
        'title': training_title,
        'visibility': training.visibility,
        'comment': training.comment,
        'color': training.color,
        'source_type': training.source_type,
        'ready_workout_type': training.ready_workout_type,
        'ready_complex_type': training.ready_complex_type,
        'ready_complex_name': training.ready_complex_name,
        'ready_plan_title': training.ready_plan_title,
        'created_by_id': training.created_by_id,
        'block_name': first_exercise['block_label'] if first_exercise else 'РЎРёР»РѕРІР°СЏ',
        'volume': first_exercise['volume'] if first_exercise else '',
        'sections': grouped_sections,
        'exercises': exercises_payload,
    }


def build_admin_training_results_payload(training):
    block_to_section = {
        AdminTrainingExercise.BLOCK_STRENGTH: TrainingResult.SECTION_STRENGTH,
        AdminTrainingExercise.BLOCK_CARDIO: TrainingResult.SECTION_CARDIO,
        AdminTrainingExercise.BLOCK_GYMNASTICS: TrainingResult.SECTION_METABOLIC,
        AdminTrainingExercise.BLOCK_CUSTOM: TrainingResult.SECTION_METABOLIC,
    }
    default_titles = {
        TrainingResult.SECTION_STRENGTH: 'Силовая',
        TrainingResult.SECTION_CARDIO: 'Кардио',
        TrainingResult.SECTION_METABOLIC: 'Гимнастика',
    }

    columns = []
    section_index = {}
    for exercise in training.exercises.all():
        section_key = block_to_section.get(exercise.block_type)
        if not section_key:
            continue
        if section_key in section_index:
            continue

        if exercise.block_type == AdminTrainingExercise.BLOCK_CUSTOM and exercise.block_custom_name.strip():
            section_title = exercise.block_custom_name.strip()
        else:
            section_title = TRAINING_BLOCK_LABELS.get(exercise.block_type) or default_titles.get(section_key, 'Раздел')

        result_type = exercise.result_type or TrainingResult.RESULT_TIME
        section_index[section_key] = len(columns)
        columns.append(
            {
                'section_key': section_key,
                'title': section_title,
                'result_type': result_type,
                'unit': RESULT_TYPE_UNITS.get(result_type, ''),
            }
        )

    if not columns:
        columns = [
            {'section_key': TrainingResult.SECTION_STRENGTH, 'title': 'Силовая', 'result_type': TrainingResult.RESULT_TIME, 'unit': RESULT_TYPE_UNITS[TrainingResult.RESULT_TIME]},
            {'section_key': TrainingResult.SECTION_CARDIO, 'title': 'Кардио', 'result_type': TrainingResult.RESULT_TIME, 'unit': RESULT_TYPE_UNITS[TrainingResult.RESULT_TIME]},
            {'section_key': TrainingResult.SECTION_METABOLIC, 'title': 'Гимнастика', 'result_type': TrainingResult.RESULT_TIME, 'unit': RESULT_TYPE_UNITS[TrainingResult.RESULT_TIME]},
        ]
        section_index = {col['section_key']: idx for idx, col in enumerate(columns)}

    day_results = (
        TrainingResult.objects
        .select_related('user')
        .filter(training_date=training.training_date, section__in=list(section_index.keys()))
        .order_by('user__first_name', 'user__last_name', 'user__email', 'section')
    )

    grouped = {}
    for item in day_results:
        user_id = item.user_id
        if user_id not in grouped:
            user_name = f'{item.user.first_name} {item.user.last_name}'.strip() or item.user.email
            grouped[user_id] = {
                'user_name': user_name,
                'values': ['--'] * len(columns),
            }
        column_position = section_index.get(item.section)
        if column_position is None:
            continue
        grouped[user_id]['values'][column_position] = format_training_result_value(
            item.result_type or columns[column_position]['result_type'],
            item.minutes,
            item.seconds,
        )

    rows = sorted(grouped.values(), key=lambda row: row['user_name'].lower())
    return {
        'training_id': training.id,
        'training_date': training.training_date.isoformat(),
        'training_title': get_admin_training_title(training.direction, training.source_type, training.ready_plan_title),
        'columns': columns,
        'rows': rows,
    }


LEADERBOARD_SECTION_META = [
    (TrainingResult.SECTION_STRENGTH, 'Силовая'),
    (TrainingResult.SECTION_CARDIO, 'Кардио'),
    (TrainingResult.SECTION_METABOLIC, 'Метаболическая'),
]


def format_training_duration_ru(minutes, seconds):
    if minutes is None and seconds is None:
        return '--'
    if minutes is None:
        return f'{seconds} сек'
    if seconds is None:
        return f'{minutes} мин'
    return f'{minutes} мин {seconds} сек'


def format_count_with_word_ru(value, one, few, many):
    if value is None:
        return '--'
    number = int(value)
    abs_number = abs(number)
    mod100 = abs_number % 100
    mod10 = abs_number % 10
    if 11 <= mod100 <= 14:
        word = many
    elif mod10 == 1:
        word = one
    elif 2 <= mod10 <= 4:
        word = few
    else:
        word = many
    return f'{number} {word}'


def format_training_result_value(result_type, primary_value, secondary_value):
    if primary_value is None and secondary_value is None:
        return '--'

    if result_type == TrainingResult.RESULT_WEIGHT:
        if primary_value is None:
            return '--'
        return f'{primary_value} кг'

    if result_type == TrainingResult.RESULT_REPS:
        if primary_value is None and secondary_value is not None:
            return format_count_with_word_ru(secondary_value, 'раз', 'раза', 'раз')
        if primary_value is not None and secondary_value is None:
            return format_count_with_word_ru(primary_value, 'раз', 'раза', 'раз')
        approaches = format_count_with_word_ru(primary_value, 'подход', 'подхода', 'подходов')
        reps = format_count_with_word_ru(secondary_value, 'раз', 'раза', 'раз')
        return f'{approaches} по {reps}'

    return format_training_duration_ru(primary_value, secondary_value)


def score_training_result(result_type, primary_value, secondary_value):
    first = primary_value if primary_value is not None else 0
    second = secondary_value if secondary_value is not None else 0
    if result_type == TrainingResult.RESULT_TIME:
        return first * 60 + second
    return first * 1000 + second


def build_daily_leaderboard_payload(training_date):
    section_titles = dict(LEADERBOARD_SECTION_META)
    section_order = {section_key: idx for idx, (section_key, _) in enumerate(LEADERBOARD_SECTION_META)}
    grouped = {section_key: [] for section_key, _ in LEADERBOARD_SECTION_META}

    raw_results = (
        TrainingResult.objects
        .select_related('user')
        .filter(training_date=training_date)
        .filter(Q(minutes__isnull=False) | Q(seconds__isnull=False))
    )
    for item in raw_results:
        full_name = f'{item.user.first_name} {item.user.last_name}'.strip() or item.user.email
        minutes = item.minutes if item.minutes is not None else 0
        seconds = item.seconds if item.seconds is not None else 0
        grouped[item.section].append(
            {
                'user_id': item.user_id,
                'user_name': full_name,
                'minutes': item.minutes,
                'seconds': item.seconds,
                'result_type': item.result_type,
                'mode': item.get_mode_display(),
                'updated_at': item.updated_at,
                'score_seconds': score_training_result(item.result_type, minutes, seconds),
            }
        )

    sections = []
    for section_key, title in LEADERBOARD_SECTION_META:
        entries = grouped.get(section_key, [])
        entries.sort(key=lambda value: (-value['score_seconds'], value['updated_at'], value['user_id']))
        for idx, entry in enumerate(entries, start=1):
            entry['place'] = idx
            entry['medal'] = 'gold' if idx == 1 else 'silver' if idx == 2 else 'bronze' if idx == 3 else None
            entry['result_label'] = format_training_result_value(
                entry.get('result_type') or TrainingResult.RESULT_TIME,
                entry['minutes'],
                entry['seconds'],
            )
            entry['place_label'] = str(idx)
            entry['section_key'] = section_key
            entry['section_title'] = section_titles[section_key]

        sections.append(
            {
                'key': section_key,
                'title': title,
                'order': section_order[section_key],
                'entries': entries,
            }
        )

    return {
        'training_date': training_date,
        'date_label': training_date.strftime('%d.%m.%Y'),
        'sections': sections,
    }


def build_week_days(selected_date):
    week_start = selected_date - timedelta(days=selected_date.weekday())
    days = []
    for offset in range(7):
        current = week_start + timedelta(days=offset)
        days.append(
            {
                'weekday': RU_WEEKDAY_SHORT[current.weekday()],
                'day': current.day,
                'iso_date': current.isoformat(),
                'is_active': current == selected_date,
            }
        )
    return days


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


def get_user_role(user):
    if user.is_staff or user.is_superuser:
        return UserProfile.ROLE_ADMIN
    profile = None
    if getattr(user, 'pk', None):
        profile = UserProfile.objects.filter(user=user).only('role').first()
    if profile and profile.role in {UserProfile.ROLE_USER, UserProfile.ROLE_TRAINER, UserProfile.ROLE_ADMIN}:
        return profile.role
    return UserProfile.ROLE_USER


def user_has_admin_panel_access(user):
    return get_user_role(user) in {UserProfile.ROLE_ADMIN, UserProfile.ROLE_TRAINER}


def can_manage_admin_users(user):
    return get_user_role(user) == UserProfile.ROLE_ADMIN


def build_admin_password_reset_link(request, reset_request):
    token = signing.dumps(
        {
            'request_id': reset_request.id,
            'code': reset_request.code,
        },
        salt=ADMIN_PASSWORD_RESET_LINK_SALT,
    )
    url = reverse('auth:admin_password_reset_new_password')
    return request.build_absolute_uri(f'{url}?token={token}')


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
        if request.user.is_authenticated and user_has_admin_panel_access(request.user):
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
        if (
            ADMIN_PASSWORD_RESET_SESSION_KEY not in request.session
            and request.GET.get('token')
        ):
            raw_token = str(request.GET.get('token') or '').strip()
            try:
                payload = signing.loads(
                    raw_token,
                    salt=ADMIN_PASSWORD_RESET_LINK_SALT,
                    max_age=10 * 60,
                )
            except signing.BadSignature:
                payload = None
            except signing.SignatureExpired:
                payload = None

            if payload:
                request_id = payload.get('request_id')
                expected_code = str(payload.get('code') or '')
                reset_request = AdminPasswordResetRequest.objects.filter(
                    id=request_id,
                    is_used=False,
                ).first()
                if (
                    reset_request
                    and not reset_request.is_expired
                    and reset_request.code == expected_code
                ):
                    request.session[ADMIN_PASSWORD_RESET_SESSION_KEY] = reset_request.id
                    request.session[ADMIN_PASSWORD_RESET_CODE_VERIFIED_KEY] = True
                    request.session.modified = True

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
            'Р СљРЎвЂ№ Р С•РЎвЂљР С—РЎР‚Р В°Р Р†Р С‘Р В»Р С‘ Р С—Р С‘РЎРѓРЎРЉР СР С• Р Р…Р В° email. Р СџР С•Р Т‘РЎвЂљР Р†Р ВµРЎР‚Р Т‘Р С‘РЎвЂљР Вµ РЎР‚Р ВµР С–Р С‘РЎРѓРЎвЂљРЎР‚Р В°РЎвЂ Р С‘РЎР‹ Р С—Р С• РЎРѓРЎРѓРЎвЂ№Р В»Р С”Р Вµ Р С‘Р В· Р С—Р С‘РЎРѓРЎРЉР СР В°.',
        )
        return super().dispatch(request, *args, **kwargs)


class UserProtectedMixin:
    login_url = reverse_lazy('auth:login')
    allow_admin_panel_access = True
    admin_fallback_url = reverse_lazy('auth:calendar')

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(self.login_url)
        if not self.allow_admin_panel_access and user_has_admin_panel_access(request.user):
            return redirect(self.admin_fallback_url)
        return super().dispatch(request, *args, **kwargs)


class UserOnlyProtectedMixin(UserProtectedMixin):
    allow_admin_panel_access = False


class SharedProfileHeaderMixin:
    @staticmethod
    def _build_profile_name(user):
        return f'{user.first_name} {user.last_name}'.strip() or user.email

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['shared_profile_name'] = self._build_profile_name(self.request.user)
        context['shared_profile_experience'] = '8 лет'
        return context


class AdminProtectedMixin:
    login_url = reverse_lazy('auth:admin_login')
    fallback_url = reverse_lazy('auth:profile')
    permission_denied_message = 'РќРµРґРѕСЃС‚Р°С‚РѕС‡РЅРѕ РїСЂР°РІ РґР»СЏ РїСЂРѕСЃРјРѕС‚СЂР° СЌС‚РѕР№ СЃС‚СЂР°РЅРёС†С‹.'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(self.login_url)
        if not user_has_admin_panel_access(request.user):
            messages.error(request, self.permission_denied_message)
            return redirect(self.fallback_url)
        return super().dispatch(request, *args, **kwargs)


class ProfileView(SharedProfileHeaderMixin, UserOnlyProtectedMixin, TemplateView):
    template_name = 'auth/profile.html'

    @staticmethod
    def _format_training_count(value):
        remainder_ten = value % 10
        remainder_hundred = value % 100
        if remainder_ten == 1 and remainder_hundred != 11:
            word = 'тренировка'
        elif remainder_ten in (2, 3, 4) and remainder_hundred not in (12, 13, 14):
            word = 'тренировки'
        else:
            word = 'тренировок'
        return f'{value} {word}'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        weekly_goal = profile.weekly_goal or 6
        context['profile_week_goal'] = weekly_goal
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        month_start = today - timedelta(days=29)
        user_results = TrainingResult.objects.filter(user=self.request.user)
        week_visits = (
            user_results
            .filter(training_date__gte=week_start, training_date__lte=today)
            .values('training_date')
            .distinct()
            .count()
        )
        month_visits = (
            user_results
            .filter(training_date__gte=month_start, training_date__lte=today)
            .values('training_date')
            .distinct()
            .count()
        )
        all_visits = (
            user_results
            .values('training_date')
            .distinct()
            .count()
        )
        context['profile_activity_values_json'] = json.dumps(
            {
                'week': {
                    'visits': self._format_training_count(week_visits),
                    'goal': self._format_training_count(weekly_goal),
                },
                'month': {
                    'visits': self._format_training_count(month_visits),
                    'goal': self._format_training_count(20),
                },
                'all': {
                    'visits': self._format_training_count(all_visits),
                    'goal': self._format_training_count(150),
                },
            },
            ensure_ascii=False,
        )

        context['profile_stats_values_json'] = json.dumps(
            {
                'week': {
                    'given': str(
                        CommunityReaction.objects.filter(
                            sender=self.request.user,
                            training_date__gte=week_start,
                            training_date__lte=today,
                        ).count()
                    ),
                    'received': str(
                        CommunityReaction.objects.filter(
                            target_user=self.request.user,
                            training_date__gte=week_start,
                            training_date__lte=today,
                        ).count()
                    ),
                },
                'month': {
                    'given': str(
                        CommunityReaction.objects.filter(
                            sender=self.request.user,
                            training_date__gte=month_start,
                            training_date__lte=today,
                        ).count()
                    ),
                    'received': str(
                        CommunityReaction.objects.filter(
                            target_user=self.request.user,
                            training_date__gte=month_start,
                            training_date__lte=today,
                        ).count()
                    ),
                },
                'all': {
                    'given': str(
                        CommunityReaction.objects.filter(
                            sender=self.request.user,
                        ).count()
                    ),
                    'received': str(
                        CommunityReaction.objects.filter(
                            target_user=self.request.user,
                        ).count()
                    ),
                },
            },
            ensure_ascii=False,
        )
        leaderboard = build_daily_leaderboard_payload(today)
        award_counts = {1: 0, 2: 0, 3: 0}
        for section_payload in leaderboard['sections']:
            for item in section_payload['entries']:
                if item['user_id'] != self.request.user.id:
                    continue
                if item['place'] in award_counts:
                    award_counts[item['place']] += 1
                break

        context['profile_awards_summary'] = {
            'first': award_counts[1],
            'second': award_counts[2],
            'third': award_counts[3],
        }
        return context


class SettingsView(UserOnlyProtectedMixin, TemplateView):
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


class SupportView(UserOnlyProtectedMixin, TemplateView):
    template_name = 'auth/support.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['support_name'] = f'{self.request.user.first_name} {self.request.user.last_name}'.strip() or self.request.user.email
        context['support_experience'] = '8 лет'
        return context


class SupportMessageSentView(UserOnlyProtectedMixin, TemplateView):
    template_name = 'auth/support-sent.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['support_name'] = f'{self.request.user.first_name} {self.request.user.last_name}'.strip() or self.request.user.email
        context['support_experience'] = '8 лет'
        return context


class SupportSubmitView(UserOnlyProtectedMixin, View):
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


class UpdateProfileGoalView(View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        user, auth_type = resolve_request_user(request)
        if user is None:
            return JsonResponse({'ok': False, 'error': 'auth_required'}, status=401)

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

        raw_goal = payload.get('weekly_goal')
        try:
            weekly_goal = int(raw_goal)
        except (TypeError, ValueError):
            return JsonResponse({'ok': False, 'error': 'invalid_weekly_goal'}, status=400)

        if weekly_goal < 1 or weekly_goal > 30:
            return JsonResponse({'ok': False, 'error': 'weekly_goal_out_of_range'}, status=400)

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.weekly_goal = weekly_goal
        profile.save(update_fields=['weekly_goal', 'updated_at'])

        logger.info(
            'Profile weekly goal updated user_id=%s email=%s weekly_goal=%s auth=%s ip=%s',
            user.id,
            user.email,
            weekly_goal,
            auth_type,
            get_client_ip(request),
        )
        return JsonResponse({'ok': True, 'weekly_goal': weekly_goal})


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


class ProfileAwardsTestsView(UserOnlyProtectedMixin, TemplateView):
    template_name = 'auth/profile-awards-tests.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        direction_value = (
            AdminTraining.objects
            .filter(training_date=today, visibility=AdminTraining.VISIBILITY_ALL)
            .order_by('-updated_at', '-id')
            .values_list('direction', flat=True)
            .first()
        )
        context['award_training_direction_label'] = TRAINING_DIRECTION_LABELS.get(direction_value, 'FBB')
        return context


class ProfileAwardWorkoutView(UserOnlyProtectedMixin, TemplateView):
    template_name = 'auth/profile-award-workout.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        leaderboard = build_daily_leaderboard_payload(today)
        user_id = self.request.user.id
        direction_value = (
            AdminTraining.objects
            .filter(training_date=today, visibility=AdminTraining.VISIBILITY_ALL)
            .order_by('-updated_at', '-id')
            .values_list('direction', flat=True)
            .first()
        )
        training_direction_label = TRAINING_DIRECTION_LABELS.get(direction_value, 'FBB')

        result_sections = []
        award_rows = []
        award_counts = {1: 0, 2: 0, 3: 0}

        for section_payload in leaderboard['sections']:
            matched = next((item for item in section_payload['entries'] if item['user_id'] == user_id), None)
            if matched:
                if matched['place'] in award_counts:
                    award_counts[matched['place']] += 1
                place_label = f"Место: {matched['place']}"
                result_value = matched['result_label']
                result_mode = matched['mode']
            else:
                place_label = 'Место: —'
                result_value = '--'
                result_mode = '--'

            result_sections.append(
                {
                    'key': section_payload['key'],
                    'title': section_payload['title'],
                    'value': result_value,
                    'mode': result_mode,
                    'place_label': place_label,
                }
            )
            award_rows.append(
                {
                    'data_date': today.isoformat(),
                    'title': f'{training_direction_label} / {section_payload["title"]}',
                    'date': today.strftime('%d.%m.%Y'),
                    'result': f'{result_value} · {place_label}',
                }
            )

        context['result_sections'] = result_sections
        context['award_rows'] = award_rows
        context['award_summary_rows'] = [
            {'place': '1 место', 'count': award_counts[1], 'icon': 'auth/img/award-first.svg'},
            {'place': '2 место', 'count': award_counts[2], 'icon': 'auth/img/award-second.svg'},
            {'place': '3 место', 'count': award_counts[3], 'icon': 'auth/img/award-third.svg'},
        ]
        context['award_training_direction_label'] = training_direction_label
        return context


class CalendarView(AdminProtectedMixin, TemplateView):
    template_name = 'auth/calendar.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        trainings = (
            AdminTraining.objects
            .select_related('created_by')
            .prefetch_related('exercises')
            .order_by('-training_date', '-updated_at', '-id')
        )
        context['calendar_trainings_json'] = json.dumps(
            [serialize_admin_training(training) for training in trainings],
            ensure_ascii=False,
        )
        return context


def serialize_admin_user_row(user):
    first_name = (user.first_name or '').strip()
    last_name = (user.last_name or '').strip()
    email = (user.email or '').strip()
    profile_role = getattr(getattr(user, 'profile', None), 'role', None) or UserProfile.ROLE_USER
    if user.is_staff or user.is_superuser:
        role = UserProfile.ROLE_ADMIN
    elif profile_role in {UserProfile.ROLE_ADMIN, UserProfile.ROLE_TRAINER}:
        role = profile_role
    else:
        role = UserProfile.ROLE_USER
    return {
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'role': role,
        'created': True,
    }


def get_admin_profile_users_queryset():
    return (
        User.objects
        .select_related('profile')
        .filter(is_active=True)
        .filter(
            Q(is_staff=True)
            | Q(is_superuser=True)
            | Q(profile__role__in=[UserProfile.ROLE_TRAINER, UserProfile.ROLE_ADMIN])
        )
        .exclude(email__isnull=True)
        .exclude(email='')
        .order_by('-date_joined', '-id')
    )


class AdminProfileView(AdminProtectedMixin, TemplateView):
    template_name = 'auth/admin-profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        contact = AdminContact.objects.filter(user=user).only('phone').first()
        first_name = (user.first_name or '').strip()
        last_name = (user.last_name or '').strip()
        initials = ((first_name[:1] + last_name[:1]).upper() or (user.email[:2].upper() if user.email else 'AD'))

        context['admin_profile_first_name'] = first_name
        context['admin_profile_last_name'] = last_name
        context['admin_profile_email'] = user.email or ''
        context['admin_profile_phone'] = contact.phone if contact else ''
        context['admin_profile_full_name'] = f'{first_name} {last_name}'.strip() or user.email or 'Admin'
        context['admin_profile_initials'] = initials
        context['admin_profile_can_manage_users'] = can_manage_admin_users(user)

        manage_users = get_admin_profile_users_queryset()[:50]
        rows = [serialize_admin_user_row(item) for item in manage_users]
        context['admin_profile_users_rows_json'] = json.dumps(rows, ensure_ascii=False)
        return context


class AdminProfileUpdateView(AdminProtectedMixin, View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

        first_name = str(payload.get('first_name') or '').strip()
        last_name = str(payload.get('last_name') or '').strip()
        email = str(payload.get('email') or '').strip().lower()
        phone = str(payload.get('phone') or '').strip()

        field_errors = {}
        if not first_name:
            field_errors['first_name'] = 'required'
        if not last_name:
            field_errors['last_name'] = 'required'
        if not email:
            field_errors['email'] = 'required'
        if len(first_name) > 150:
            field_errors['first_name'] = 'too_long'
        if len(last_name) > 150:
            field_errors['last_name'] = 'too_long'
        if len(email) > 254:
            field_errors['email'] = 'too_long'
        if phone and len(phone) > 32:
            field_errors['phone'] = 'too_long'
        if phone and AdminContact.objects.exclude(user=request.user).filter(phone=phone).exists():
            field_errors['phone'] = 'already_exists'

        if email and User.objects.exclude(pk=request.user.pk).filter(email__iexact=email).exists():
            field_errors['email'] = 'already_exists'

        if field_errors:
            return JsonResponse({'ok': False, 'error': 'validation_error', 'field_errors': field_errors}, status=400)

        with transaction.atomic():
            request.user.first_name = first_name
            request.user.last_name = last_name
            request.user.email = email
            request.user.username = email
            request.user.save(update_fields=['first_name', 'last_name', 'email', 'username'])

            contact = AdminContact.objects.filter(user=request.user).first()
            if phone:
                if contact is None:
                    AdminContact.objects.create(user=request.user, phone=phone)
                else:
                    contact.phone = phone
                    contact.save(update_fields=['phone', 'updated_at'])
            elif contact is not None:
                contact.delete()

        full_name = f'{first_name} {last_name}'.strip() or email
        initials = ((first_name[:1] + last_name[:1]).upper() or (email[:2].upper() if email else 'AD'))
        return JsonResponse(
            {
                'ok': True,
                'profile': {
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email,
                    'phone': phone,
                    'full_name': full_name,
                    'initials': initials,
                },
            }
        )


class AdminProfilePasswordUpdateView(AdminProtectedMixin, View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

        old_password = str(payload.get('old_password') or '')
        new_password = str(payload.get('new_password') or '')
        repeat_password = str(payload.get('repeat_password') or '')

        field_errors = {}
        if not old_password:
            field_errors['old_password'] = 'required'
        if not new_password:
            field_errors['new_password'] = 'required'
        if not repeat_password:
            field_errors['repeat_password'] = 'required'
        if new_password and repeat_password and new_password != repeat_password:
            field_errors['repeat_password'] = 'mismatch'
        if old_password and not request.user.check_password(old_password):
            field_errors['old_password'] = 'invalid'

        if not field_errors and new_password:
            try:
                validate_password(new_password, user=request.user)
            except ValidationError:
                field_errors['new_password'] = 'weak'

        if field_errors:
            return JsonResponse({'ok': False, 'error': 'validation_error', 'field_errors': field_errors}, status=400)

        request.user.set_password(new_password)
        request.user.save(update_fields=['password'])
        update_session_auth_hash(request, request.user)
        return JsonResponse({'ok': True})


class AdminProfileUsersListView(AdminProtectedMixin, View):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        if not can_manage_admin_users(request.user):
            return JsonResponse({'ok': False, 'error': 'permission_denied'}, status=403)

        users = get_admin_profile_users_queryset()[:100]
        rows = [serialize_admin_user_row(item) for item in users]
        return JsonResponse({'ok': True, 'rows': rows})


class AdminProfileUserCreateView(AdminProtectedMixin, View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        if not can_manage_admin_users(request.user):
            return JsonResponse({'ok': False, 'error': 'permission_denied'}, status=403)

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

        first_name = str(payload.get('first_name') or '').strip()
        last_name = str(payload.get('last_name') or '').strip()
        email = str(payload.get('email') or '').strip().lower()
        role = str(payload.get('role') or '').strip().lower()

        field_errors = {}
        if not first_name:
            field_errors['first_name'] = 'required'
        if not last_name:
            field_errors['last_name'] = 'required'
        if not email:
            field_errors['email'] = 'required'
        if role not in {UserProfile.ROLE_TRAINER, UserProfile.ROLE_ADMIN}:
            field_errors['role'] = 'invalid_role'
        if len(first_name) > 150:
            field_errors['first_name'] = 'too_long'
        if len(last_name) > 150:
            field_errors['last_name'] = 'too_long'
        if len(email) > 254:
            field_errors['email'] = 'too_long'
        if email and User.objects.filter(email__iexact=email).exists():
            field_errors['email'] = 'already_exists'

        if field_errors:
            return JsonResponse({'ok': False, 'error': 'validation_error', 'field_errors': field_errors}, status=400)

        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                password=None,
                first_name=first_name,
                last_name=last_name,
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
            user.set_unusable_password()
            user.save(update_fields=['password'])

            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            profile.save(update_fields=['role', 'updated_at'])

            reset_request = AdminPasswordResetRequest.objects.create(
                user=user,
                code=f'{secrets.randbelow(1000000):06d}',
                expires_at=timezone.now() + timedelta(minutes=10),
            )

            invite_sent = True
            try:
                reset_link = build_admin_password_reset_link(request, reset_request)
                send_mail(
                    subject='Приглашение в админ-панель',
                    message=(
                        'Вы были добавлены в систему.\n\n'
                        'Для установки пароля откройте ссылку:\n'
                        f'{reset_link}\n\n'
                        'Ссылка действует 10 минут.'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
            except Exception:
                invite_sent = False
                logger.exception(
                    'Admin invite email send failed user_id=%s email=%s',
                    user.id,
                    email,
                )

        return JsonResponse(
            {
                'ok': True,
                'created': True,
                'invite_sent': invite_sent,
                'user': serialize_admin_user_row(user),
            }
        )


class AdminLibraryView(AdminProtectedMixin, TemplateView):
    template_name = 'auth/admin-library.html'

    @staticmethod
    def _serialize_item(item):
        return {
            'id': item.id,
            'section': item.section,
            'category': item.benchmark_category,
            'name_ru': item.name_ru,
            'name_en': item.name_en,
            'desc_ru': item.desc_ru,
            'desc_en': item.desc_en,
            'video': item.video_file.name.rsplit('/', 1)[-1] if item.video_file else '',
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = [self._serialize_item(item) for item in AdminLibraryItem.objects.all()]
        context['library_rows'] = rows
        context['library_rows_json'] = json.dumps(rows, ensure_ascii=False)
        return context


class AdminLibraryListView(AdminProtectedMixin, View):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        section = str(request.GET.get('section') or AdminLibraryItem.SECTION_EXERCISES).strip().lower()
        category = str(request.GET.get('category') or '').strip().lower()

        valid_sections = {choice[0] for choice in AdminLibraryItem.SECTION_CHOICES}
        valid_categories = {choice[0] for choice in AdminLibraryItem.BENCHMARK_CATEGORY_CHOICES}
        if section not in valid_sections:
            return JsonResponse({'ok': False, 'error': 'invalid_section'}, status=400)

        query = AdminLibraryItem.objects.filter(section=section)
        if section == AdminLibraryItem.SECTION_BENCHMARKS:
            normalized_category = category if category in valid_categories else AdminLibraryItem.CATEGORY_GIRLS
            query = query.filter(benchmark_category=normalized_category)

        rows = [AdminLibraryView._serialize_item(item) for item in query]
        return JsonResponse({'ok': True, 'rows': rows})


class AdminLibraryCreateView(AdminProtectedMixin, View):
    http_method_names = ['post']
    ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.wmv'}
    MAX_VIDEO_SIZE_BYTES = 500 * 1024 * 1024

    def post(self, request, *args, **kwargs):
        section = str(request.POST.get('section') or '').strip().lower()
        category = str(request.POST.get('category') or '').strip().lower()
        name_ru = str(request.POST.get('name_ru') or '').strip()
        name_en = str(request.POST.get('name_en') or '').strip()
        desc_ru = str(request.POST.get('desc_ru') or '').strip()
        desc_en = str(request.POST.get('desc_en') or '').strip()
        video_file = request.FILES.get('video')

        allowed_sections = {choice[0] for choice in AdminLibraryItem.SECTION_CHOICES}
        allowed_categories = {choice[0] for choice in AdminLibraryItem.BENCHMARK_CATEGORY_CHOICES}

        field_errors = {}
        if section not in allowed_sections:
            field_errors['section'] = 'invalid_section'
        if section == AdminLibraryItem.SECTION_BENCHMARKS:
            if category not in allowed_categories:
                field_errors['category'] = 'invalid_category'
        else:
            category = ''
        if not name_ru:
            field_errors['name_ru'] = 'required'
        if len(name_ru) > 255:
            field_errors['name_ru'] = 'too_long'
        if len(name_en) > 255:
            field_errors['name_en'] = 'too_long'
        if video_file:
            extension = Path(video_file.name or '').suffix.lower()
            if extension not in self.ALLOWED_VIDEO_EXTENSIONS:
                field_errors['video'] = 'invalid_video_format'
            elif getattr(video_file, 'size', 0) > self.MAX_VIDEO_SIZE_BYTES:
                field_errors['video'] = 'video_too_large'

        if field_errors:
            return JsonResponse({'ok': False, 'error': 'validation_error', 'field_errors': field_errors}, status=400)

        item = AdminLibraryItem.objects.create(
            section=section,
            benchmark_category=category,
            name_ru=name_ru,
            name_en=name_en,
            desc_ru=desc_ru,
            desc_en=desc_en,
            video_file=video_file,
            created_by=request.user,
        )

        return JsonResponse(
            {
                'ok': True,
                'item': {
                    'id': item.id,
                    'section': item.section,
                    'category': item.benchmark_category,
                    'name_ru': item.name_ru,
                    'name_en': item.name_en,
                    'desc_ru': item.desc_ru,
                    'desc_en': item.desc_en,
                    'video': item.video_file.name.rsplit('/', 1)[-1] if item.video_file else '',
                },
            }
        )


class AdminLibraryUpdateView(AdminProtectedMixin, View):
    http_method_names = ['post']
    ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.wmv'}
    MAX_VIDEO_SIZE_BYTES = 500 * 1024 * 1024

    def post(self, request, item_id, *args, **kwargs):
        item = AdminLibraryItem.objects.filter(id=item_id).first()
        if item is None:
            return JsonResponse({'ok': False, 'error': 'item_not_found'}, status=404)

        section = str(request.POST.get('section') or '').strip().lower()
        category = str(request.POST.get('category') or '').strip().lower()
        name_ru = str(request.POST.get('name_ru') or '').strip()
        name_en = str(request.POST.get('name_en') or '').strip()
        desc_ru = str(request.POST.get('desc_ru') or '').strip()
        desc_en = str(request.POST.get('desc_en') or '').strip()
        video_file = request.FILES.get('video')

        allowed_sections = {choice[0] for choice in AdminLibraryItem.SECTION_CHOICES}
        allowed_categories = {choice[0] for choice in AdminLibraryItem.BENCHMARK_CATEGORY_CHOICES}

        field_errors = {}
        if section not in allowed_sections:
            field_errors['section'] = 'invalid_section'
        if section == AdminLibraryItem.SECTION_BENCHMARKS:
            if category not in allowed_categories:
                field_errors['category'] = 'invalid_category'
        else:
            category = ''
        if not name_ru:
            field_errors['name_ru'] = 'required'
        if len(name_ru) > 255:
            field_errors['name_ru'] = 'too_long'
        if len(name_en) > 255:
            field_errors['name_en'] = 'too_long'
        if video_file:
            extension = Path(video_file.name or '').suffix.lower()
            if extension not in self.ALLOWED_VIDEO_EXTENSIONS:
                field_errors['video'] = 'invalid_video_format'
            elif getattr(video_file, 'size', 0) > self.MAX_VIDEO_SIZE_BYTES:
                field_errors['video'] = 'video_too_large'

        if field_errors:
            return JsonResponse({'ok': False, 'error': 'validation_error', 'field_errors': field_errors}, status=400)

        item.section = section
        item.benchmark_category = category
        item.name_ru = name_ru
        item.name_en = name_en
        item.desc_ru = desc_ru
        item.desc_en = desc_en
        if video_file:
            item.video_file = video_file
        item.save(
            update_fields=[
                'section',
                'benchmark_category',
                'name_ru',
                'name_en',
                'desc_ru',
                'desc_en',
                'video_file',
                'updated_at',
            ]
        )

        return JsonResponse(
            {
                'ok': True,
                'item': {
                    'id': item.id,
                    'section': item.section,
                    'category': item.benchmark_category,
                    'name_ru': item.name_ru,
                    'name_en': item.name_en,
                    'desc_ru': item.desc_ru,
                    'desc_en': item.desc_en,
                    'video': item.video_file.name.rsplit('/', 1)[-1] if item.video_file else '',
                },
            }
        )


class AdminLibraryDeleteView(AdminProtectedMixin, View):
    http_method_names = ['post']

    def post(self, request, item_id, *args, **kwargs):
        item = AdminLibraryItem.objects.filter(id=item_id).first()
        if item is None:
            return JsonResponse({'ok': False, 'error': 'item_not_found'}, status=404)

        if item.video_file:
            item.video_file.delete(save=False)
        item.delete()
        return JsonResponse({'ok': True, 'deleted_id': item_id})


class StatisticsView(AdminProtectedMixin, TemplateView):
    template_name = 'auth/statistics.html'

    MONTHS_GENITIVE = (
        'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
    )

    @staticmethod
    def _parse_iso_date(value):
        text = str(value or '').strip()
        if not text:
            return None
        try:
            return datetime.strptime(text, '%Y-%m-%d').date()
        except ValueError:
            return None

    @staticmethod
    def _format_user_short_name(user):
        first = (user.first_name or '').strip()
        last = (user.last_name or '').strip()
        if first and last:
            return f'{first} {last[0]}.'
        if first:
            return first
        return (user.email or '').strip() or f'Пользователь {user.id}'

    @classmethod
    def _default_period(cls):
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        return week_start, week_start + timedelta(days=6)

    @classmethod
    def _normalize_period(cls, start, end):
        if end < start:
            start, end = end, start
        diff = (end - start).days
        if diff < 6:
            end = start + timedelta(days=6)
        if (end - start).days > 30:
            end = start + timedelta(days=30)
        return start, end

    @classmethod
    def _format_period_label(cls, start, end):
        return (
            f"{RU_WEEKDAY.get(start.weekday(), '')}, {start.day} {cls.MONTHS_GENITIVE[start.month - 1]} {start.year} - "
            f"{RU_WEEKDAY.get(end.weekday(), '')}, {end.day} {cls.MONTHS_GENITIVE[end.month - 1]} {end.year}"
        )

    @staticmethod
    def _stars(value):
        rating = max(1, min(5, int(value)))
        return ('★' * rating) + ('☆' * (5 - rating))

    @staticmethod
    def _rating_label(value):
        return f'{float(value):.1f}'.replace('.', ',')

    @staticmethod
    def _result_unit_label(result_type):
        if result_type == TrainingResult.RESULT_WEIGHT:
            return 'кг'
        if result_type == TrainingResult.RESULT_REPS:
            return 'повт'
        return 'мин'

    @staticmethod
    def _result_value_label(result_type, minutes, seconds):
        if result_type == TrainingResult.RESULT_WEIGHT:
            if minutes is not None:
                return str(minutes)
            return str(seconds) if seconds is not None else '—'
        if result_type == TrainingResult.RESULT_REPS:
            if minutes is not None and seconds is not None:
                return f'{minutes} x {seconds}'
            if minutes is not None:
                return str(minutes)
            return str(seconds) if seconds is not None else '—'
        if minutes is None and seconds is None:
            return '—'
        if minutes is None:
            return f'0:{int(seconds):02d}'
        if seconds is None:
            return str(minutes)
        return f'{int(minutes)}:{int(seconds):02d}'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        default_start, default_end = self._default_period()
        parsed_start = self._parse_iso_date(self.request.GET.get('start')) or default_start
        parsed_end = self._parse_iso_date(self.request.GET.get('end')) or default_end
        period_start, period_end = self._normalize_period(parsed_start, parsed_end)
        period_days = (period_end - period_start).days + 1

        rates_qs = (
            TrainingRate.objects
            .select_related('user')
            .filter(training_date__range=(period_start, period_end))
            .order_by('-training_date', '-updated_at')
        )
        rates_by_date = {}
        for rate in rates_qs:
            rates_by_date.setdefault(rate.training_date, []).append(rate)

        block_to_section = {
            AdminTrainingExercise.BLOCK_STRENGTH: TrainingResult.SECTION_STRENGTH,
            AdminTrainingExercise.BLOCK_CARDIO: TrainingResult.SECTION_CARDIO,
            AdminTrainingExercise.BLOCK_GYMNASTICS: TrainingResult.SECTION_METABOLIC,
            AdminTrainingExercise.BLOCK_CUSTOM: TrainingResult.SECTION_METABOLIC,
        }

        grouped_exercises = {}
        exercise_entries = (
            AdminTrainingExercise.objects
            .select_related('training')
            .filter(training__training_date__range=(period_start, period_end))
        )
        for entry in exercise_entries:
            direction_label = TRAINING_DIRECTION_LABELS.get(entry.training.direction, 'Тренировка')
            key = (entry.exercise_name, direction_label)
            bucket = grouped_exercises.setdefault(
                key,
                {
                    'count': 0,
                    'color': entry.training.color or AdminTraining.COLOR_BLUE,
                    'dates': set(),
                    'block_type': entry.block_type,
                    'result_type': entry.result_type or AdminTrainingExercise.RESULT_TIME,
                },
            )
            bucket['count'] += 1
            bucket['dates'].add(entry.training.training_date)
            if not bucket.get('result_type') and entry.result_type:
                bucket['result_type'] = entry.result_type
        exercise_rows = []
        exercise_reviews_payload = {}
        exercise_results_payload = {}
        sorted_exercises = sorted(
            grouped_exercises.items(),
            key=lambda pair: (-pair[1]['count'], pair[0][0]),
        )
        for index, (key, data) in enumerate(sorted_exercises):
            review_key = f'exercise_{index}'
            result_key = f'result_{index}'
            review_cards = []
            training_dates = sorted(data.get('dates') or [], reverse=True)
            for training_date in training_dates:
                for rate in rates_by_date.get(training_date, []):
                    full_name = f'{rate.user.first_name} {rate.user.last_name}'.strip() or rate.user.email
                    review_cards.append(
                        {
                            'training_title': key[1],
                            'date_label': training_date.strftime('%d.%m.%Y'),
                            'author_name': full_name,
                            'comment': (rate.comment or '').strip(),
                            'strength_stars': self._stars(rate.strength),
                            'strength_value': self._rating_label(rate.strength),
                            'cardio_stars': self._stars(rate.cardio),
                            'cardio_value': self._rating_label(rate.cardio),
                            'metabolic_stars': self._stars(rate.metabolic),
                            'metabolic_value': self._rating_label(rate.metabolic),
                            'overall': float(rate.overall),
                        }
                    )

            avg_review_score = (
                sum(card.get('overall', 0.0) for card in review_cards) / len(review_cards)
                if review_cards else None
            )

            section_key = block_to_section.get(data.get('block_type'))
            result_type = data.get('result_type') or AdminTrainingExercise.RESULT_TIME
            result_rows = []
            if training_dates and section_key:
                user_latest_results = {}
                result_entries = (
                    TrainingResult.objects
                    .select_related('user')
                    .filter(training_date__in=training_dates, section=section_key)
                    .order_by('user_id', '-training_date', '-updated_at')
                )
                for result_entry in result_entries:
                    if result_entry.user_id in user_latest_results:
                        continue
                    user_latest_results[result_entry.user_id] = {
                        'name': self._format_user_short_name(result_entry.user),
                        'value': self._result_value_label(
                            result_entry.result_type or result_type,
                            result_entry.minutes,
                            result_entry.seconds,
                        ),
                    }
                result_rows = sorted(user_latest_results.values(), key=lambda row: row['name'])

            exercise_rows.append(
                {
                    'exercise': key[0],
                    'training': key[1],
                    'results': len(result_rows),
                    'reviews': len(review_cards),
                    'rating': self._rating_label(avg_review_score) if avg_review_score is not None else '0',
                    'training_color': data.get('color') or AdminTraining.COLOR_BLUE,
                    'review_key': review_key,
                    'result_key': result_key,
                }
            )
            exercise_reviews_payload[review_key] = {
                'title': key[1],
                'exercise': key[0],
                'reviews': [{k: v for k, v in card.items() if k != 'overall'} for card in review_cards],
            }
            exercise_results_payload[result_key] = {
                'title': key[1],
                'exercise': key[0],
                'unit': self._result_unit_label(result_type),
                'rows': result_rows,
            }

        exercise_rows.sort(key=lambda item: (-item['results'], item['exercise']))
        context['exercise_rows'] = exercise_rows[:12]
        context['exercise_reviews_payload'] = exercise_reviews_payload
        context['exercise_results_payload'] = exercise_results_payload

        training_counts = {
            row['user_id']: row['total']
            for row in (
                TrainingResult.objects
                .filter(training_date__range=(period_start, period_end))
                .values('user_id')
                .annotate(total=Count('id'))
            )
        }
        received_counts = {
            row['target_user_id']: row['total']
            for row in (
                CommunityReaction.objects
                .filter(training_date__range=(period_start, period_end))
                .values('target_user_id')
                .annotate(total=Count('id'))
            )
        }
        sent_counts = {
            row['sender_id']: row['total']
            for row in (
                CommunityReaction.objects
                .filter(training_date__range=(period_start, period_end))
                .values('sender_id')
                .annotate(total=Count('id'))
            )
        }
        activity_user_ids = set(training_counts) | set(received_counts) | set(sent_counts)
        users_by_id = {
            user.id: user
            for user in User.objects.filter(id__in=activity_user_ids).only('id', 'first_name', 'last_name', 'email')
        }
        activity_rows = []
        for user_id in activity_user_ids:
            user = users_by_id.get(user_id)
            if not user:
                continue
            activity_rows.append(
                {
                    'name': self._format_user_short_name(user),
                    'trainings': training_counts.get(user_id, 0),
                    'received': received_counts.get(user_id, 0),
                    'sent': sent_counts.get(user_id, 0),
                }
            )
        activity_rows.sort(key=lambda item: (-item['trainings'], -item['received'], -item['sent'], item['name']))
        context['activity_rows'] = activity_rows[:12]

        registered_users_count = UserProfile.objects.filter(role=UserProfile.ROLE_USER).count()
        active_user_ids = set(
            TrainingResult.objects
            .filter(training_date__range=(period_start, period_end))
            .values_list('user_id', flat=True)
            .distinct()
        )
        active_user_ids.update(
            TrainingRate.objects
            .filter(training_date__range=(period_start, period_end))
            .values_list('user_id', flat=True)
            .distinct()
        )
        active_user_ids.update(
            CommunityReaction.objects
            .filter(training_date__range=(period_start, period_end))
            .values_list('sender_id', flat=True)
            .distinct()
        )
        active_user_ids.update(
            CommunityReaction.objects
            .filter(training_date__range=(period_start, period_end))
            .values_list('target_user_id', flat=True)
            .distinct()
        )
        active_users_count = UserProfile.objects.filter(
            role=UserProfile.ROLE_USER,
            user_id__in=active_user_ids,
        ).count()
        context['users_registered_count'] = registered_users_count
        context['users_active_count'] = active_users_count

        today = timezone.localdate()
        context['results_today_count'] = TrainingResult.objects.filter(training_date=today).count()
        context['results_period_count'] = TrainingResult.objects.filter(
            training_date__range=(period_start, period_end)
        ).count()

        visited_counts = {
            row['user_id']: row['visited']
            for row in (
                TrainingResult.objects
                .filter(training_date__range=(period_start, period_end))
                .values('user_id')
                .annotate(visited=Count('training_date', distinct=True))
            )
        }
        achievement_user_ids = set(visited_counts.keys())
        users_with_profiles = (
            User.objects
            .select_related('profile')
            .filter(id__in=achievement_user_ids)
        )
        weeks_in_period = max(1, (period_days + 6) // 7)
        achievement_rows = []
        for user in users_with_profiles:
            weekly_goal = getattr(getattr(user, 'profile', None), 'weekly_goal', 0) or 6
            achievement_rows.append(
                {
                    'name': self._format_user_short_name(user),
                    'visited': visited_counts.get(user.id, 0),
                    'goal': weekly_goal * weeks_in_period,
                }
            )
        achievement_rows.sort(key=lambda item: (-item['visited'], item['name']))
        context['achievement_rows'] = achievement_rows[:12]

        context['range_start_iso'] = period_start.isoformat()
        context['range_end_iso'] = period_end.isoformat()
        context['range_label'] = self._format_period_label(period_start, period_end)
        return context


class ReviewsOverviewView(AdminProtectedMixin, TemplateView):
    template_name = 'auth/reviews-overview.html'

    COLOR_CYCLE = ('orange', 'violet', 'green')
    LOAD_TYPE_TO_FIELD = {
        'all': 'overall',
        'strength': 'strength',
        'cardio': 'cardio',
        'metabolic': 'metabolic',
    }
    PERIOD_OPTIONS = {'all', 'today', 'week', 'month'}

    @staticmethod
    def _stars(value):
        rating = max(1, min(5, int(value)))
        return ('★' * rating) + ('☆' * (5 - rating))

    @staticmethod
    def _rating_label(value):
        return f'{float(value):.1f}'.replace('.', ',')

    @staticmethod
    def _format_exercise_row(exercise):
        name = str(getattr(exercise, 'exercise_name', '') or '').strip()
        sets = getattr(exercise, 'sets', None)
        reps = getattr(exercise, 'reps', None)
        if name and sets and reps:
            return f'{name} x {sets} подхода по {reps}'
        return name

    @staticmethod
    def _resolve_block_label(exercise):
        if exercise.block_type == AdminTrainingExercise.BLOCK_CUSTOM:
            custom_name = str(exercise.block_custom_name or '').strip()
            if custom_name:
                return custom_name
        return TRAINING_BLOCK_LABELS.get(exercise.block_type, 'Блок')

    @staticmethod
    def _pick_training_for_rate(rate, candidates):
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        rate_anchor = getattr(rate, 'updated_at', None) or getattr(rate, 'created_at', None)
        if not rate_anchor:
            return candidates[0]
        return min(
            candidates,
            key=lambda training: abs(
                (
                    (getattr(training, 'updated_at', None) or getattr(training, 'created_at', None) or rate_anchor)
                    - rate_anchor
                ).total_seconds()
            ),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        load_type = (self.request.GET.get('load_type') or 'all').strip().lower()
        order_by = (self.request.GET.get('order_by') or 'rating_desc').strip().lower()
        period = (self.request.GET.get('period') or 'all').strip().lower()
        search_query = str(self.request.GET.get('q') or '').strip()
        search_query_folded = search_query.casefold()
        if load_type not in self.LOAD_TYPE_TO_FIELD:
            load_type = 'all'
        # Backward-compatible parsing for old values ("rating"/"date")
        if order_by in {'rating_asc', 'asc'}:
            order_by = 'rating_asc'
        elif order_by in {'rating_desc', 'desc', 'rating', 'date'}:
            order_by = 'rating_desc'
        else:
            order_by = 'rating_desc'
        if period not in self.PERIOD_OPTIONS:
            period = 'all'

        rating_field = self.LOAD_TYPE_TO_FIELD[load_type]
        rates = TrainingRate.objects.select_related('user')
        today = timezone.localdate()
        if period == 'today':
            rates = rates.filter(training_date=today)
        elif period == 'week':
            rates = rates.filter(training_date__range=(today - timedelta(days=6), today))
        elif period == 'month':
            rates = rates.filter(training_date__range=(today - timedelta(days=29), today))
        if order_by == 'rating_asc':
            rates = rates.order_by(rating_field, '-training_date', '-updated_at')
        else:
            rates = rates.order_by(f'-{rating_field}', '-training_date', '-updated_at')

        rates_list = list(rates)
        rate_dates = sorted({rate.training_date for rate in rates_list if rate.training_date})
        trainings_by_date = {}
        if rate_dates:
            trainings = (
                AdminTraining.objects
                .filter(training_date__in=rate_dates)
                .prefetch_related('exercises')
                .order_by('-training_date', '-updated_at', '-id')
            )
            for training in trainings:
                trainings_by_date.setdefault(training.training_date, []).append(training)

        review_cards = []
        training_view_payload = {}
        for index, rate in enumerate(rates_list):
            full_name = f'{rate.user.first_name} {rate.user.last_name}'.strip() or rate.user.email
            training = self._pick_training_for_rate(
                rate,
                trainings_by_date.get(rate.training_date, []),
            )
            training_key = f'rate-{rate.id}'
            training_title = TRAINING_DIRECTION_LABELS.get(training.direction, 'HIIT Training') if training else 'HIIT Training'
            if search_query_folded and search_query_folded not in training_title.casefold():
                continue
            if training:
                exercises = []
                for exercise in training.exercises.all():
                    exercise_text = self._format_exercise_row(exercise)
                    if not exercise_text:
                        continue
                    exercises.append(
                        {
                            'block': self._resolve_block_label(exercise),
                            'text': exercise_text,
                        }
                    )
                training_view_payload[training_key] = {
                    'training_id': training.id,
                    'title': TRAINING_DIRECTION_LABELS.get(training.direction, 'Тренировка'),
                    'date_label': training.training_date.strftime('%d.%m.%Y'),
                    'direction': TRAINING_DIRECTION_LABELS.get(training.direction, 'Тренировка'),
                    'visibility': 'Только для тренера' if training.visibility == AdminTraining.VISIBILITY_COACHES else 'Для всех',
                    'comment': str(training.comment or '').strip(),
                    'color': training.color or 'blue',
                    'exercises': exercises,
                }
            review_cards.append(
                {
                    'color': self.COLOR_CYCLE[index % len(self.COLOR_CYCLE)],
                    'training_title': training_title,
                    'date_label': rate.training_date.strftime('%d.%m.%Y'),
                    'author_name': full_name,
                    'comment': rate.comment.strip() or 'Без комментария',
                    'overall_stars': self._stars(rate.overall),
                    'strength_stars': self._stars(rate.strength),
                    'cardio_stars': self._stars(rate.cardio),
                    'metabolic_stars': self._stars(rate.metabolic),
                    'overall_value': self._rating_label(rate.overall),
                    'strength_value': self._rating_label(rate.strength),
                    'cardio_value': self._rating_label(rate.cardio),
                    'metabolic_value': self._rating_label(rate.metabolic),
                    'training_key': training_key,
                }
            )

        context['selected_load_type'] = load_type
        context['selected_order_by'] = order_by
        context['selected_period'] = period
        context['search_query'] = search_query
        context['review_cards'] = review_cards
        context['reviews_training_view_json'] = training_view_payload
        return context


class AdminTrainingBaseView(AdminProtectedMixin, View):
    http_method_names = ['post', 'get']

    @staticmethod
    def _parse_date(raw_date):
        value = str(raw_date or '').strip()
        if not value:
            return None
        try:
            return timezone.datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            return None

    @staticmethod
    def _parse_positive_int(value):
        if value in (None, ''):
            return None
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        if parsed <= 0:
            return None
        return parsed

    def _collect_exercises(self, payload):
        raw_exercises = payload.get('exercises') or []
        if not isinstance(raw_exercises, list):
            return None, {'exercises': 'invalid_exercises'}

        valid_block_values = {key for key, _ in AdminTrainingExercise.BLOCK_CHOICES}
        valid_result_values = {key for key, _ in AdminTrainingExercise.RESULT_CHOICES}
        valid_exercise_kinds = set(EXERCISE_KIND_LABELS.keys())
        parsed_exercises = []
        errors = {}

        for index, raw_item in enumerate(raw_exercises):
            if not isinstance(raw_item, dict):
                errors[f'exercises.{index}'] = 'invalid_exercise_item'
                continue

            block_type = str(raw_item.get('block_type') or AdminTrainingExercise.BLOCK_STRENGTH).strip().lower()
            if block_type not in valid_block_values:
                errors[f'exercises.{index}.block_type'] = 'invalid_block_type'
                continue

            result_type = str(raw_item.get('result_type') or AdminTrainingExercise.RESULT_TIME).strip().lower()
            if result_type not in valid_result_values:
                errors[f'exercises.{index}.result_type'] = 'invalid_result_type'
                continue

            exercise_kind = str(raw_item.get('exercise_kind') or 'exercise').strip().lower()
            if exercise_kind not in valid_exercise_kinds:
                errors[f'exercises.{index}.exercise_kind'] = 'invalid_exercise_kind'
                continue

            block_custom_name = str(raw_item.get('block_custom_name') or '').strip()
            if block_type == AdminTrainingExercise.BLOCK_CUSTOM and not block_custom_name:
                errors[f'exercises.{index}.block_custom_name'] = 'block_custom_name_required'
                continue

            exercise_name = str(raw_item.get('exercise_name') or '').strip()
            sets = self._parse_positive_int(raw_item.get('sets'))
            reps = self._parse_positive_int(raw_item.get('reps'))

            if not exercise_name:
                errors[f'exercises.{index}.exercise_name'] = 'exercise_name_required'
                continue
            if exercise_kind == AdminTrainingExercise.EXERCISE_KIND_EXERCISE:
                if (sets is None) != (reps is None):
                    errors[f'exercises.{index}.sets_reps'] = 'sets_and_reps_must_be_together'
                    continue
                if sets is None or reps is None:
                    errors[f'exercises.{index}.sets_reps'] = 'sets_and_reps_must_be_together'
                    continue
            else:
                sets = None
                reps = None

            parsed_exercises.append(
                {
                    'exercise_kind': exercise_kind,
                    'block_type': block_type,
                    'block_custom_name': block_custom_name,
                    'exercise_name': exercise_name,
                    'sets': sets,
                    'reps': reps,
                    'result_type': result_type,
                    'order': len(parsed_exercises),
                }
            )

        return parsed_exercises, errors

    def _validate_payload(self, payload):
        valid_directions = {key for key, _ in AdminTraining.DIRECTION_CHOICES}
        valid_visibility = {key for key, _ in AdminTraining.VISIBILITY_CHOICES}
        valid_color = {key for key, _ in AdminTraining.COLOR_CHOICES}
        valid_source = {key for key, _ in AdminTraining.SOURCE_CHOICES}

        training_date = self._parse_date(payload.get('date'))
        direction = str(payload.get('direction') or AdminTraining.DIRECTION_FBB).strip().lower()
        visibility = str(payload.get('visibility') or AdminTraining.VISIBILITY_ALL).strip().lower()
        color = str(payload.get('color') or AdminTraining.COLOR_BLUE).strip().lower()
        source_type = str(payload.get('source_type') or AdminTraining.SOURCE_MANUAL).strip().lower()
        comment = str(payload.get('comment') or '').strip()
        ready_workout_type = str(payload.get('ready_workout_type') or '').strip()
        ready_complex_type = str(payload.get('ready_complex_type') or '').strip()
        ready_complex_name = str(payload.get('ready_complex_name') or '').strip()
        ready_plan_title = str(payload.get('ready_plan_title') or '').strip()

        field_errors = {}
        if not training_date:
            field_errors['date'] = 'invalid_date'
        if direction not in valid_directions:
            field_errors['direction'] = 'invalid_direction'
        if visibility not in valid_visibility:
            field_errors['visibility'] = 'invalid_visibility'
        if color not in valid_color:
            field_errors['color'] = 'invalid_color'
        if source_type not in valid_source:
            field_errors['source_type'] = 'invalid_source_type'
        if len(comment) > 1000:
            field_errors['comment'] = 'comment_too_long'

        if source_type != AdminTraining.SOURCE_READY:
            ready_workout_type = ''
            ready_complex_type = ''
            ready_complex_name = ''
            ready_plan_title = ''

        exercises, exercise_errors = self._collect_exercises(payload)
        field_errors.update(exercise_errors)

        if source_type == AdminTraining.SOURCE_READY and not ready_plan_title:
            field_errors['ready_plan_title'] = 'ready_plan_title_required'

        if not exercises:
            if source_type == AdminTraining.SOURCE_READY and ready_plan_title:
                exercises = [
                    {
                        'exercise_kind': AdminTrainingExercise.EXERCISE_KIND_EXERCISE,
                        'block_type': AdminTrainingExercise.BLOCK_STRENGTH,
                        'block_custom_name': '',
                        'exercise_name': ready_plan_title,
                        'sets': None,
                        'reps': None,
                        'result_type': AdminTrainingExercise.RESULT_TIME,
                        'order': 0,
                    }
                ]
            else:
                field_errors['exercises'] = 'at_least_one_exercise_required'

        if field_errors:
            return None, field_errors

        return {
            'training_date': training_date,
            'direction': direction,
            'visibility': visibility,
            'comment': comment,
            'color': color,
            'source_type': source_type,
            'ready_workout_type': ready_workout_type,
            'ready_complex_type': ready_complex_type,
            'ready_complex_name': ready_complex_name,
            'ready_plan_title': ready_plan_title,
            'exercises': exercises,
        }, {}

    @staticmethod
    def _replace_exercises(training, exercises):
        training.exercises.all().delete()
        AdminTrainingExercise.objects.bulk_create(
            [
                AdminTrainingExercise(
                    training=training,
                    exercise_kind=item['exercise_kind'],
                    block_type=item['block_type'],
                    block_custom_name=item['block_custom_name'],
                    exercise_name=item['exercise_name'],
                    sets=item['sets'],
                    reps=item['reps'],
                    result_type=item['result_type'],
                    order=item['order'],
                )
                for item in exercises
            ]
        )


class AdminTrainingCreateView(AdminTrainingBaseView):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

        parsed_payload, field_errors = self._validate_payload(payload)
        if field_errors:
            return JsonResponse({'ok': False, 'error': 'validation_error', 'field_errors': field_errors}, status=400)

        with transaction.atomic():
            training = AdminTraining.objects.create(
                training_date=parsed_payload['training_date'],
                direction=parsed_payload['direction'],
                visibility=parsed_payload['visibility'],
                comment=parsed_payload['comment'],
                color=parsed_payload['color'],
                source_type=parsed_payload['source_type'],
                ready_workout_type=parsed_payload['ready_workout_type'],
                ready_complex_type=parsed_payload['ready_complex_type'],
                ready_complex_name=parsed_payload['ready_complex_name'],
                ready_plan_title=parsed_payload['ready_plan_title'],
                created_by=request.user,
            )
            self._replace_exercises(training, parsed_payload['exercises'])

        training = AdminTraining.objects.prefetch_related('exercises').get(pk=training.pk)
        return JsonResponse({'ok': True, 'training_id': training.id, 'training': serialize_admin_training(training)})


class AdminTrainingUpdateView(AdminTrainingBaseView):
    http_method_names = ['post']

    def post(self, request, training_id, *args, **kwargs):
        training = AdminTraining.objects.filter(id=training_id).first()
        if training is None:
            return JsonResponse({'ok': False, 'error': 'training_not_found'}, status=404)

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

        parsed_payload, field_errors = self._validate_payload(payload)
        if field_errors:
            return JsonResponse({'ok': False, 'error': 'validation_error', 'field_errors': field_errors}, status=400)

        with transaction.atomic():
            training.training_date = parsed_payload['training_date']
            training.direction = parsed_payload['direction']
            training.visibility = parsed_payload['visibility']
            training.comment = parsed_payload['comment']
            training.color = parsed_payload['color']
            training.source_type = parsed_payload['source_type']
            training.ready_workout_type = parsed_payload['ready_workout_type']
            training.ready_complex_type = parsed_payload['ready_complex_type']
            training.ready_complex_name = parsed_payload['ready_complex_name']
            training.ready_plan_title = parsed_payload['ready_plan_title']
            training.save(
                update_fields=[
                    'training_date',
                    'direction',
                    'visibility',
                    'comment',
                    'color',
                    'source_type',
                    'ready_workout_type',
                    'ready_complex_type',
                    'ready_complex_name',
                    'ready_plan_title',
                    'updated_at',
                ]
            )
            self._replace_exercises(training, parsed_payload['exercises'])

        training = AdminTraining.objects.prefetch_related('exercises').get(pk=training.pk)
        return JsonResponse({'ok': True, 'training_id': training.id, 'training': serialize_admin_training(training)})


class AdminTrainingDeleteView(AdminProtectedMixin, View):
    http_method_names = ['post']

    def post(self, request, training_id, *args, **kwargs):
        training = AdminTraining.objects.filter(id=training_id).first()
        if training is None:
            return JsonResponse({'ok': False, 'error': 'training_not_found'}, status=404)
        training.delete()
        return JsonResponse({'ok': True, 'training_id': training_id})


class AdminTrainingByDateView(AdminProtectedMixin, View):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        raw_date = str(request.GET.get('date') or '').strip()
        try:
            training_date = timezone.datetime.strptime(raw_date, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'ok': False, 'error': 'invalid_date'}, status=400)

        trainings = (
            AdminTraining.objects
            .filter(training_date=training_date)
            .prefetch_related('exercises')
            .order_by('-updated_at', '-id')
        )
        return JsonResponse({'ok': True, 'trainings': [serialize_admin_training(item) for item in trainings]})


class AdminTrainingResultsView(AdminProtectedMixin, View):
    http_method_names = ['get']

    def get(self, request, training_id, *args, **kwargs):
        training = (
            AdminTraining.objects
            .filter(id=training_id)
            .prefetch_related('exercises')
            .first()
        )
        if training is None:
            return JsonResponse({'ok': False, 'error': 'training_not_found'}, status=404)

        payload = build_admin_training_results_payload(training)
        return JsonResponse({'ok': True, 'results': payload})


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

        if get_user_role(user) == UserProfile.ROLE_USER and training_date != timezone.localdate():
            return JsonResponse({'ok': False, 'error': 'only_today_allowed'}, status=403)

        results = payload.get('results') or {}
        if not isinstance(results, dict):
            return JsonResponse({'ok': False, 'error': 'invalid_results'}, status=400)

        valid_sections = {key for key, _ in TrainingResult.SECTION_CHOICES}
        valid_modes = {key for key, _ in TrainingResult.MODE_CHOICES}
        valid_result_types = {key for key, _ in TrainingResult.RESULT_TYPE_CHOICES}
        saved_count = 0

        for section_key, section_payload in results.items():
            if section_key not in valid_sections:
                return JsonResponse({'ok': False, 'error': f'invalid_section:{section_key}'}, status=400)
            if not isinstance(section_payload, dict):
                return JsonResponse({'ok': False, 'error': f'invalid_section_payload:{section_key}'}, status=400)

            mode = str(section_payload.get('mode') or TrainingResult.MODE_RX).lower()
            if mode not in valid_modes:
                return JsonResponse({'ok': False, 'error': f'invalid_mode:{section_key}'}, status=400)

            result_type = str(section_payload.get('result_type') or TrainingResult.RESULT_TIME).lower()
            if result_type not in valid_result_types:
                return JsonResponse({'ok': False, 'error': f'invalid_result_type:{section_key}'}, status=400)

            minutes = self._parse_positive_int(section_payload.get('minutes'))
            seconds = self._parse_positive_int(section_payload.get('seconds'))

            if minutes is None and seconds is None:
                continue

            if result_type == TrainingResult.RESULT_TIME and seconds is not None and seconds > 59:
                return JsonResponse({'ok': False, 'error': f'invalid_seconds:{section_key}'}, status=400)

            TrainingResult.objects.update_or_create(
                user=user,
                training_date=training_date,
                section=section_key,
                defaults={
                    'result_type': result_type,
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
        result_type = str(entry.get('result_type') or TrainingResult.RESULT_TIME).strip().lower()
        minutes = DownloadTrainingResultsImageView._safe_int(entry.get('minutes'))
        seconds = DownloadTrainingResultsImageView._safe_int(entry.get('seconds'))
        return format_training_result_value(result_type, minutes, seconds)

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

        title = 'Р РµР·СѓР»СЊС‚Р°С‚С‹ С‚СЂРµРЅРёСЂРѕРІРєРё'
        title_box = draw.textbbox((0, 0), title, font=font_title)
        title_w = title_box[2] - title_box[0]
        draw.text((summary_x + (summary_w - title_w) / 2, summary_y + 72), title, font=font_title, fill='#242d35')

        row_specs = [
            ('РљР°СЂРґРёРѕ', cardio_value),
            ('РЎРёР»РѕРІР°СЏ', strength_value),
            ('РњРµС‚Р°Р±РѕР»РёС‡РµСЃРєР°СЏ', metabolic_value),
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
            1: 'СЏРЅРІР°СЂСЏ', 2: 'С„РµРІСЂР°Р»СЏ', 3: 'РјР°СЂС‚Р°', 4: 'Р°РїСЂРµР»СЏ', 5: 'РјР°СЏ', 6: 'РёСЋРЅСЏ',
            7: 'РёСЋР»СЏ', 8: 'Р°РІРіСѓСЃС‚Р°', 9: 'СЃРµРЅС‚СЏР±СЂСЏ', 10: 'РѕРєС‚СЏР±СЂСЏ', 11: 'РЅРѕСЏР±СЂСЏ', 12: 'РґРµРєР°Р±СЂСЏ',
        }
        pretty_date = f"{training_date.day} {month_names.get(training_date.month, '')} {training_date.year} Рі."
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

        redirect_name = 'auth:admin_login' if get_user_role(request.user) == UserProfile.ROLE_ADMIN else 'auth:login'
        response = redirect(redirect_name)
        clear_jwt_cookies(response)
        return response


class LeaderboardDayView(SharedProfileHeaderMixin, UserOnlyProtectedMixin, TemplateView):
    template_name = 'auth/leaderboard-day.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        raw_date = str(self.request.GET.get('date') or '').strip()
        if raw_date:
            try:
                selected_date = timezone.datetime.strptime(raw_date, '%Y-%m-%d').date()
            except ValueError:
                selected_date = timezone.localdate()
        else:
            selected_date = timezone.localdate()

        leaderboard = build_daily_leaderboard_payload(selected_date)
        direction_value = (
            AdminTraining.objects
            .filter(training_date=selected_date, visibility=AdminTraining.VISIBILITY_ALL)
            .order_by('-updated_at', '-id')
            .values_list('direction', flat=True)
            .first()
        )
        sections_by_key = {item['key']: item for item in leaderboard['sections']}
        trainings_query = AdminTraining.objects.filter(training_date=selected_date).prefetch_related('exercises')
        if get_user_role(self.request.user) == UserProfile.ROLE_USER:
            trainings_query = trainings_query.filter(visibility=AdminTraining.VISIBILITY_ALL)
        trainings = list(trainings_query.order_by('-updated_at', '-id'))

        block_to_section = {
            AdminTrainingExercise.BLOCK_STRENGTH: TrainingResult.SECTION_STRENGTH,
            AdminTrainingExercise.BLOCK_CARDIO: TrainingResult.SECTION_CARDIO,
            AdminTrainingExercise.BLOCK_GYMNASTICS: TrainingResult.SECTION_METABOLIC,
            AdminTrainingExercise.BLOCK_CUSTOM: TrainingResult.SECTION_METABOLIC,
        }
        leaderboard_training_groups = []
        for training in trainings:
            ordered_exercises = sorted(training.exercises.all(), key=lambda item: (item.order, item.id))
            exercise_lines = []
            for exercise in ordered_exercises:
                block_label = (
                    exercise.block_custom_name.strip()
                    if exercise.block_type == AdminTrainingExercise.BLOCK_CUSTOM and exercise.block_custom_name.strip()
                    else TRAINING_BLOCK_LABELS.get(exercise.block_type, 'Силовая')
                )
                volume_label = format_admin_training_volume(exercise)
                exercise_lines.append({
                    'block': block_label,
                    'value': volume_label,
                })

            group_sections = []
            seen_sections = set()
            for exercise in ordered_exercises:
                section_key = block_to_section.get(exercise.block_type)
                if not section_key:
                    continue
                section_title = (
                    exercise.block_custom_name.strip()
                    if exercise.block_type == AdminTrainingExercise.BLOCK_CUSTOM and exercise.block_custom_name.strip()
                    else dict(LEADERBOARD_SECTION_META).get(section_key, 'Раздел')
                )
                section_identity = f'{section_key}:{section_title}'
                if section_identity in seen_sections:
                    continue
                seen_sections.add(section_identity)
                group_sections.append(
                    {
                        'key': section_key,
                        'title': section_title,
                        'entries': sections_by_key.get(section_key, {}).get('entries', []),
                    }
                )

            if not group_sections:
                group_sections = list(leaderboard['sections'])

            leaderboard_training_groups.append(
                {
                    'title': get_admin_training_title(training.direction, training.source_type, training.ready_plan_title),
                    'exercise_lines': exercise_lines,
                    'sections': group_sections,
                }
            )

        if not leaderboard_training_groups:
            fallback_direction = TRAINING_DIRECTION_LABELS.get(direction_value, 'FBB')
            leaderboard_training_groups.append(
                {
                    'title': fallback_direction,
                    'exercise_lines': [],
                    'sections': list(leaderboard['sections']),
                }
            )

        context['leaderboard_date'] = leaderboard['date_label']
        context['leaderboard_sections'] = leaderboard['sections']
        context['leaderboard_training_groups'] = leaderboard_training_groups
        context['leaderboard_week_days'] = build_week_days(selected_date)
        context['leaderboard_selected_date_iso'] = selected_date.isoformat()
        context['leaderboard_training_direction_label'] = TRAINING_DIRECTION_LABELS.get(direction_value, 'FBB')

        # Dedicated presentation payload for admin leaderboard page:
        # list of cards with direction header and real exercises of the day.
        admin_cards = []
        for training in trainings:
            ordered_exercises = sorted(training.exercises.all(), key=lambda item: (item.order, item.id))
            exercise_cards = []
            for exercise in ordered_exercises:
                secondary = ''
                if exercise.sets is not None and exercise.reps is not None:
                    sets_label = format_count_with_word_ru(exercise.sets, 'подход', 'подхода', 'подходов')
                    reps_label = format_count_with_word_ru(exercise.reps, 'повторение', 'повторения', 'повторений')
                    secondary = f'{sets_label} / {reps_label}'
                elif exercise.sets is not None:
                    secondary = format_count_with_word_ru(exercise.sets, 'подход', 'подхода', 'подходов')
                elif exercise.reps is not None:
                    secondary = format_count_with_word_ru(exercise.reps, 'повторение', 'повторения', 'повторений')
                exercise_cards.append(
                    {
                        'title': (exercise.exercise_name or '').strip() or 'Упражнение',
                        'meta': secondary,
                    }
                )
            direction_label = TRAINING_DIRECTION_LABELS.get(
                training.direction,
                (training.direction or 'FBB'),
            )
            admin_cards.append(
                {
                    'training_id': training.id,
                    'direction_label': direction_label,
                    'exercise_cards': exercise_cards,
                }
            )

        context['leaderboard_admin_cards'] = admin_cards
        return context


class LeaderboardDayAdminView(AdminProtectedMixin, LeaderboardDayView):
    template_name = 'auth/leaderboard-day-admin.html'
    allow_admin_panel_access = True


class LeaderboardWorkoutDetailAdminView(AdminProtectedMixin, TemplateView):
    template_name = 'auth/leaderboard-workout-detail-admin.html'

    @staticmethod
    def _format_exercise_meta(exercise):
        sets = exercise.sets
        reps = exercise.reps
        if sets is not None and reps is not None:
            sets_label = format_count_with_word_ru(sets, 'подход', 'подхода', 'подходов')
            reps_label = format_count_with_word_ru(reps, 'повторение', 'повторения', 'повторений')
            return f'{sets_label} / {reps_label}'
        if sets is not None:
            return format_count_with_word_ru(sets, 'подход', 'подхода', 'подходов')
        if reps is not None:
            return format_count_with_word_ru(reps, 'повторение', 'повторения', 'повторений')
        return '--'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        raw_date = str(self.request.GET.get('date') or '').strip()
        if raw_date:
            try:
                selected_date = timezone.datetime.strptime(raw_date, '%Y-%m-%d').date()
            except ValueError:
                selected_date = timezone.localdate()
        else:
            selected_date = timezone.localdate()

        raw_training_id = str(self.request.GET.get('training_id') or '').strip()
        training_id = None
        if raw_training_id.isdigit():
            training_id = int(raw_training_id)

        trainings = list(
            AdminTraining.objects
            .filter(training_date=selected_date)
            .prefetch_related('exercises')
            .order_by('-updated_at', '-id')
        )
        selected_training = None
        if training_id is not None:
            selected_training = next((item for item in trainings if item.id == training_id), None)
        if selected_training is None and trainings:
            selected_training = trainings[0]

        if selected_training is None:
            context['workout_title'] = 'Тренировка'
            context['workout_direction_label'] = '--'
            context['workout_cards'] = []
            context['workout_selected_date_iso'] = selected_date.isoformat()
            context['workout_training_id'] = ''
            return context

        ordered_exercises = sorted(selected_training.exercises.all(), key=lambda item: (item.order, item.id))
        context['workout_title'] = get_admin_training_title(
            selected_training.direction,
            selected_training.source_type,
            selected_training.ready_plan_title,
        )
        context['workout_direction_label'] = TRAINING_DIRECTION_LABELS.get(
            selected_training.direction,
            (selected_training.direction or 'FBB'),
        )
        context['workout_cards'] = [
            {
                'title': (exercise.exercise_name or '').strip() or 'Упражнение',
                'meta': self._format_exercise_meta(exercise),
            }
            for exercise in ordered_exercises
        ]
        context['workout_selected_date_iso'] = selected_date.isoformat()
        context['workout_training_id'] = selected_training.id
        return context


class LeaderboardWorkoutExerciseAdminView(AdminProtectedMixin, TemplateView):
    template_name = 'auth/leaderboard-workout-exercise-admin.html'

    @staticmethod
    def _format_exercise_meta(exercise):
        sets = exercise.sets
        reps = exercise.reps
        if sets is not None and reps is not None:
            sets_label = format_count_with_word_ru(sets, 'подход', 'подхода', 'подходов')
            reps_label = format_count_with_word_ru(reps, 'повторение', 'повторения', 'повторений')
            return f'{sets_label} / {reps_label}'
        if sets is not None:
            return format_count_with_word_ru(sets, 'подход', 'подхода', 'подходов')
        if reps is not None:
            return format_count_with_word_ru(reps, 'повторение', 'повторения', 'повторений')
        return '--'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        raw_date = str(self.request.GET.get('date') or '').strip()
        if raw_date:
            try:
                selected_date = timezone.datetime.strptime(raw_date, '%Y-%m-%d').date()
            except ValueError:
                selected_date = timezone.localdate()
        else:
            selected_date = timezone.localdate()

        raw_training_id = str(self.request.GET.get('training_id') or '').strip()
        training_id = None
        if raw_training_id.isdigit():
            training_id = int(raw_training_id)

        trainings = list(
            AdminTraining.objects
            .filter(training_date=selected_date)
            .prefetch_related('exercises')
            .order_by('-updated_at', '-id')
        )
        selected_training = None
        if training_id is not None:
            selected_training = next((item for item in trainings if item.id == training_id), None)
        if selected_training is None and trainings:
            selected_training = trainings[0]

        if selected_training is None:
            context['workout_title'] = 'Тренировка'
            context['workout_kind_badge'] = '--'
            context['workout_exercises'] = []
            context['workout_leader_rows'] = []
            return context

        ordered_exercises = sorted(selected_training.exercises.all(), key=lambda item: (item.order, item.id))
        context['workout_title'] = get_admin_training_title(
            selected_training.direction,
            selected_training.source_type,
            selected_training.ready_plan_title,
        )
        context['workout_kind_badge'] = TRAINING_DIRECTION_LABELS.get(
            selected_training.direction,
            (selected_training.direction or 'FBB'),
        )
        context['workout_exercises'] = [
            {
                'index': idx + 1,
                'title': (exercise.exercise_name or '').strip() or 'Упражнение',
                'meta': self._format_exercise_meta(exercise),
            }
            for idx, exercise in enumerate(ordered_exercises)
        ]
        block_to_section = {
            AdminTrainingExercise.BLOCK_STRENGTH: TrainingResult.SECTION_STRENGTH,
            AdminTrainingExercise.BLOCK_CARDIO: TrainingResult.SECTION_CARDIO,
            AdminTrainingExercise.BLOCK_GYMNASTICS: TrainingResult.SECTION_METABOLIC,
            AdminTrainingExercise.BLOCK_CUSTOM: TrainingResult.SECTION_METABOLIC,
        }
        section_titles = dict(LEADERBOARD_SECTION_META)
        selected_section_keys = []
        for exercise in ordered_exercises:
            section_key = block_to_section.get(exercise.block_type)
            if not section_key or section_key in selected_section_keys:
                continue
            selected_section_keys.append(section_key)

        leaderboard = build_daily_leaderboard_payload(selected_date)
        sections_by_key = {section['key']: section for section in leaderboard['sections']}
        workout_leader_rows = []
        for section_key in selected_section_keys:
            section = sections_by_key.get(section_key) or {}
            for entry in section.get('entries', []):
                medal = entry.get('medal')
                workout_leader_rows.append(
                    {
                        'user_name': entry.get('user_name') or 'Участник',
                        'result_label': entry.get('result_label') or '--',
                        'section_title': section_titles.get(section_key, 'Раздел'),
                        'place_label': entry.get('place_label') or '--',
                        'row_class': (
                            'workout-leader-row--gold'
                            if medal == 'gold'
                            else 'workout-leader-row--silver'
                            if medal == 'silver'
                            else 'workout-leader-row--bronze'
                            if medal == 'bronze'
                            else ''
                        ),
                    }
                )
        context['workout_leader_rows'] = workout_leader_rows
        return context


class CommunityView(SharedProfileHeaderMixin, UserOnlyProtectedMixin, TemplateView):
    template_name = 'auth/community.html'

    @staticmethod
    def _format_training_value(result):
        return format_training_result_value(
            getattr(result, 'result_type', TrainingResult.RESULT_TIME),
            result.minutes,
            result.seconds,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['community_name'] = context.get('shared_profile_name') or (
            f'{self.request.user.first_name} {self.request.user.last_name}'.strip()
            or self.request.user.email
        )
        context['community_experience'] = context.get('shared_profile_experience') or '8 лет'

        raw_date = str(self.request.GET.get('date') or '').strip()
        if raw_date:
            try:
                selected_date = timezone.datetime.strptime(raw_date, '%Y-%m-%d').date()
            except ValueError:
                selected_date = timezone.localdate()
        else:
            selected_date = timezone.localdate()

        section_meta = [
            (TrainingResult.SECTION_STRENGTH, 'Силовая'),
            (TrainingResult.SECTION_CARDIO, 'Кардио'),
            (TrainingResult.SECTION_METABOLIC, 'Метаболическая'),
        ]
        section_titles = dict(section_meta)
        reaction_counts = dict(
            CommunityReaction.objects
            .filter(training_date=selected_date)
            .values('target_user_id')
            .annotate(total=Count('id'))
            .values_list('target_user_id', 'total')
        )
        my_reacted_user_ids = set(
            CommunityReaction.objects
            .filter(training_date=selected_date, sender=self.request.user)
            .values_list('target_user_id', flat=True)
        )

        grouped = {}
        day_results = (
            TrainingResult.objects
            .select_related('user')
            .filter(training_date=selected_date)
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

        context['community_date'] = selected_date.strftime('%d.%m.%Y')
        context['community_selected_date_iso'] = selected_date.isoformat()
        context['community_week_days'] = build_week_days(selected_date)
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
        if target_user.id == user.id:
            return JsonResponse({'ok': False, 'error': 'cannot_react_to_self'}, status=400)

        raw_date = str(payload.get('date') or '').strip()
        if raw_date:
            try:
                selected_date = timezone.datetime.strptime(raw_date, '%Y-%m-%d').date()
            except ValueError:
                selected_date = timezone.localdate()
        else:
            selected_date = timezone.localdate()

        if not TrainingResult.objects.filter(user=target_user, training_date=selected_date).exists():
            return JsonResponse({'ok': False, 'error': 'target_has_no_results_today'}, status=400)

        _, created = CommunityReaction.objects.get_or_create(
            sender=user,
            target_user=target_user,
            training_date=selected_date,
        )
        reacted = True

        reactions_count = CommunityReaction.objects.filter(
            target_user=target_user,
            training_date=selected_date,
        ).count()
        return JsonResponse({
            'ok': True,
            'reacted': reacted,
            'already_reacted': not created,
            'reactions_count': reactions_count,
            'target_user_id': target_user_id,
            'date': selected_date.isoformat(),
        })


class TrainingPlanTodayView(SharedProfileHeaderMixin, UserOnlyProtectedMixin, TemplateView):
    template_name = 'auth/training-plan-today.html'

    def get(self, request, *args, **kwargs):
        role = get_user_role(request.user)
        if role == UserProfile.ROLE_USER:
            raw_date = str(request.GET.get('date') or '').strip()
            if raw_date:
                try:
                    selected_date = timezone.datetime.strptime(raw_date, '%Y-%m-%d').date()
                except ValueError:
                    selected_date = timezone.localdate()
            else:
                selected_date = timezone.localdate()

            today = timezone.localdate()
            if selected_date < today:
                leaderboard_url = reverse_lazy('auth:leaderboard_day')
                return redirect(f'{leaderboard_url}?date={selected_date.isoformat()}')

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        role = get_user_role(self.request.user)
        raw_date = str(self.request.GET.get('date') or '').strip()
        if raw_date:
            try:
                selected_date = timezone.datetime.strptime(raw_date, '%Y-%m-%d').date()
            except ValueError:
                selected_date = timezone.localdate()
        else:
            selected_date = timezone.localdate()

        context['plan_week_days'] = build_week_days(selected_date)
        context['plan_selected_date_iso'] = selected_date.isoformat()
        context['plan_selected_date_label'] = selected_date.strftime('%d.%m.%Y')
        context['plan_today_iso'] = timezone.localdate().isoformat()
        context['plan_is_user'] = role == UserProfile.ROLE_USER

        trainings_query = AdminTraining.objects.filter(training_date=selected_date)
        if role == UserProfile.ROLE_USER:
            trainings_query = trainings_query.filter(visibility=AdminTraining.VISIBILITY_ALL)

        trainings = list(trainings_query.prefetch_related('exercises').order_by('-updated_at', '-id'))

        plan_cards = []
        for training in trainings:
            sections = []
            section_index = {}
            for exercise in training.exercises.all():
                section_title = (
                    exercise.block_custom_name.strip()
                    if exercise.block_type == AdminTrainingExercise.BLOCK_CUSTOM
                    else TRAINING_BLOCK_LABELS.get(exercise.block_type, 'Силовая')
                )
                if section_title not in section_index:
                    section_index[section_title] = len(sections)
                    sections.append({'title': section_title, 'lines': []})
                sections[section_index[section_title]]['lines'].append({
                    'text': format_admin_training_volume(exercise),
                    'show_video': True,
                    'video_url': '',
                })

            plan_cards.append(
                {
                    'title': get_admin_training_title(training.direction, training.source_type, training.ready_plan_title),
                    'sections': sections,
                    'comment': training.comment,
                    'result_types': get_plan_result_type_map([training]),
                }
            )

        context['plan_cards'] = plan_cards
        result_type_map = get_plan_result_type_map(trainings)
        context['plan_result_types_json'] = json.dumps(result_type_map, ensure_ascii=False)
        return context


class AchievementsView(SharedProfileHeaderMixin, UserOnlyProtectedMixin, TemplateView):
    template_name = 'auth/achievements.html'

    @staticmethod
    def _build_library_exercise_slug(item_id):
        return f'library-item-{item_id}'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        barbell_items = list(
            AdminLibraryItem.objects
            .filter(section=AdminLibraryItem.SECTION_BARBELL)
            .only('id', 'name_ru', 'name_en')
            .order_by('name_ru', 'name_en', 'id')
        )

        slug_map = {self._build_library_exercise_slug(item.id): item for item in barbell_items}
        profiles = {
            profile.exercise_slug: profile
            for profile in UserExerciseRepProfile.objects.filter(
                user=self.request.user,
                exercise_slug__in=list(slug_map.keys()),
            )
        }

        context['barbell_exercises'] = [
            {
                'slug': slug,
                'title': (item.name_ru or item.name_en or '').strip() or f'Упражнение {item.id}',
                'value': profiles[slug].rep_1 if slug in profiles else None,
            }
            for slug, item in slug_map.items()
        ]

        benchmark_items = list(
            AdminLibraryItem.objects
            .filter(section=AdminLibraryItem.SECTION_BENCHMARKS)
            .only('id', 'name_ru', 'name_en', 'benchmark_category')
            .order_by('benchmark_category', 'name_ru', 'name_en', 'id')
        )

        benchmark_slug_map = {self._build_library_exercise_slug(item.id): item for item in benchmark_items}
        benchmark_profiles = {
            profile.exercise_slug: profile
            for profile in UserExerciseRepProfile.objects.filter(
                user=self.request.user,
                exercise_slug__in=list(benchmark_slug_map.keys()),
            )
        }

        def serialize_benchmark(item):
            slug = self._build_library_exercise_slug(item.id)
            return {
                'slug': slug,
                'title': (item.name_ru or item.name_en or '').strip() or f'Упражнение {item.id}',
                'value': benchmark_profiles[slug].rep_1 if slug in benchmark_profiles else None,
            }

        context['benchmark_exercises'] = {
            'girls': [serialize_benchmark(item) for item in benchmark_items if item.benchmark_category == AdminLibraryItem.CATEGORY_GIRLS],
            'heroes': [serialize_benchmark(item) for item in benchmark_items if item.benchmark_category == AdminLibraryItem.CATEGORY_HEROES],
            'gymnastics': [serialize_benchmark(item) for item in benchmark_items if item.benchmark_category == AdminLibraryItem.CATEGORY_GYMNASTICS],
        }
        return context


class AchievementExerciseView(UserOnlyProtectedMixin, TemplateView):
    template_name = 'auth/achievement-exercise.html'

    EXERCISE_DATA = {
        'back-pause-squat': {
            'title': 'Back Pause Squat',
            'max': [10, 10, 10, 10],
        },
    }
    PERCENT_MATRIX = [
        [105, 100, 95, 90],
        [85, 80, 75, 70],
        [65, 60, 55, 50],
        [45, 40, 35, 30],
    ]

    @staticmethod
    def _to_positive_int(value):
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        if parsed < 1:
            return None
        return parsed

    @classmethod
    def _round_percent_value(cls, base_value, percent_value):
        return (base_value * percent_value + 50) // 100

    @classmethod
    def _build_percent_rows(cls, base_rep):
        safe_base_rep = cls._to_positive_int(base_rep) or 10
        rows = []
        for percent_row in cls.PERCENT_MATRIX:
            row_cells = []
            for percent_value in percent_row:
                computed = cls._round_percent_value(safe_base_rep, percent_value)
                row_cells.append((str(computed), f'{percent_value}%'))
            rows.append(row_cells)
        return rows

    @staticmethod
    def _build_relative_percents(reps):
        first = reps[0]
        return {
            'p1': 100,
            'p2': (reps[1] * 100 + first // 2) // first,
            'p3': (reps[2] * 100 + first // 2) // first,
            'p4': (reps[3] * 100 + first // 2) // first,
        }

    @classmethod
    def _get_default_reps(cls, slug):
        data = cls.EXERCISE_DATA.get(slug) or {}
        reps = data.get('max') or [10, 10, 10, 10]
        normalized = []
        for value in reps[:4]:
            parsed = cls._to_positive_int(value)
            normalized.append(parsed if parsed is not None else 10)
        while len(normalized) < 4:
            normalized.append(10)
        return normalized

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slug = self.kwargs.get('exercise_slug', '')
        data = self.EXERCISE_DATA.get(slug)
        if data is None:
            library_match = re.fullmatch(r'library-item-(\d+)', slug)
            if library_match:
                item = (
                    AdminLibraryItem.objects
                    .filter(
                        id=int(library_match.group(1)),
                        section__in=[AdminLibraryItem.SECTION_BARBELL, AdminLibraryItem.SECTION_BENCHMARKS],
                    )
                    .only('id', 'name_ru', 'name_en')
                    .first()
                )
                if item is not None:
                    data = {
                        'title': (item.name_ru or item.name_en or '').strip() or f'Упражнение {item.id}',
                        'max': [10, 10, 10, 10],
                    }
        if data is None:
            title = slug.replace('-', ' ').title()
            data = {
                'title': title,
                'max': [10, 10, 10, 10],
            }
        default_reps = self._get_default_reps(slug)
        profile = UserExerciseRepProfile.objects.filter(user=self.request.user, exercise_slug=slug).first()
        if profile:
            raw_reps = [profile.rep_1, profile.rep_2, profile.rep_3, profile.rep_4]
            reps = []
            for index, value in enumerate(raw_reps):
                normalized = self._to_positive_int(value)
                reps.append(normalized if normalized is not None else default_reps[index])
        else:
            reps = default_reps

        context['exercise'] = {
            'title': data.get('title') or slug.replace('-', ' ').title(),
            'max': reps,
            'percent_rows': self._build_percent_rows(reps[0]),
        }
        context['exercise_initial_reps_json'] = json.dumps(
            {
                'rep_1': reps[0],
                'rep_2': reps[1],
                'rep_3': reps[2],
                'rep_4': reps[3],
            },
            ensure_ascii=False,
        )
        context['exercise_relative_percents_json'] = json.dumps(self._build_relative_percents(reps), ensure_ascii=False)
        context['exercise_update_url'] = reverse_lazy('auth:achievement_exercise_update', kwargs={'exercise_slug': slug})
        return context


class AchievementExerciseUpdateView(View):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        user, _ = resolve_request_user(request)
        if user is None:
            return JsonResponse({'ok': False, 'error': 'auth_required'}, status=401)

        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

        slug = str(kwargs.get('exercise_slug') or '').strip().lower()
        if not slug:
            return JsonResponse({'ok': False, 'error': 'invalid_exercise_slug'}, status=400)

        rep_1 = AchievementExerciseView._to_positive_int(payload.get('rep_1'))
        rep_2 = AchievementExerciseView._to_positive_int(payload.get('rep_2'))
        rep_3 = AchievementExerciseView._to_positive_int(payload.get('rep_3'))
        rep_4 = AchievementExerciseView._to_positive_int(payload.get('rep_4'))
        if None in (rep_1, rep_2, rep_3, rep_4):
            return JsonResponse({'ok': False, 'error': 'invalid_reps'}, status=400)

        profile, _ = UserExerciseRepProfile.objects.update_or_create(
            user=user,
            exercise_slug=slug,
            defaults={
                'rep_1': rep_1,
                'rep_2': rep_2,
                'rep_3': rep_3,
                'rep_4': rep_4,
            },
        )
        reps = [profile.rep_1, profile.rep_2, profile.rep_3, profile.rep_4]
        percent_rows = AchievementExerciseView._build_percent_rows(reps[0])
        return JsonResponse(
            {
                'ok': True,
                'reps': {
                    'rep_1': reps[0],
                    'rep_2': reps[1],
                    'rep_3': reps[2],
                    'rep_4': reps[3],
                },
                'relative_percents': AchievementExerciseView._build_relative_percents(reps),
                'percent_rows': [
                    [{'value': value, 'percent': percent} for value, percent in row]
                    for row in percent_rows
                ],
            }
        )


