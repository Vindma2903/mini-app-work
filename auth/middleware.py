import os
from threading import Lock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db.utils import OperationalError, ProgrammingError
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .jwt_utils import get_jwt_cookie_names
from .seeds import ensure_default_users


class EnsureDefaultAdminMiddleware:
    _init_lock = Lock()
    _initialized = False

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _is_enabled() -> bool:
        return (os.getenv('AUTO_CREATE_ADMIN', '1') or '').strip().lower() in {'1', 'true', 'yes', 'on'}

    @classmethod
    def _ensure_once(cls) -> None:
        if cls._initialized or not cls._is_enabled():
            return
        with cls._init_lock:
            if cls._initialized:
                return
            try:
                ensure_default_users()
                cls._initialized = True
            except (OperationalError, ProgrammingError):
                # DB may be temporarily unavailable; retry on next request.
                return

    def __call__(self, request):
        self._ensure_once()
        return self.get_response(request)


class JwtCookieAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt_auth = JWTAuthentication()
        self.user_model = get_user_model()

    @staticmethod
    def _extract_bearer_token(request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.lower().startswith('bearer '):
            return None
        token = auth_header.split(' ', 1)[1].strip()
        return token or None

    def _authenticate_by_token(self, raw_token):
        if not raw_token:
            return None
        try:
            validated_token = self.jwt_auth.get_validated_token(raw_token)
            return self.jwt_auth.get_user(validated_token)
        except (InvalidToken, AuthenticationFailed):
            return None

    def _refresh_access_from_refresh_cookie(self, request):
        access_cookie_name, refresh_cookie_name = get_jwt_cookie_names()
        refresh_raw = request.COOKIES.get(refresh_cookie_name)
        if not refresh_raw:
            return None
        try:
            refresh = RefreshToken(refresh_raw)
            user_id = refresh.get('user_id')
            if not user_id:
                return None
            user = self.user_model.objects.filter(id=user_id).first()
            if user is None or not user.is_active:
                return None
            new_access = str(refresh.access_token)
            request._jwt_new_access_token = new_access
            request._jwt_access_cookie_name = access_cookie_name
            return user
        except TokenError:
            return None

    def __call__(self, request):
        user = None

        raw_token = self._extract_bearer_token(request)
        if raw_token:
            user = self._authenticate_by_token(raw_token)

        if user is None:
            access_cookie_name, _ = get_jwt_cookie_names()
            access_raw = request.COOKIES.get(access_cookie_name)
            user = self._authenticate_by_token(access_raw)

        if user is None:
            user = self._refresh_access_from_refresh_cookie(request)

        if user is not None:
            request.user = user
            request._cached_user = user
        elif not getattr(request, 'user', None):
            request.user = AnonymousUser()

        response = self.get_response(request)

        new_access = getattr(request, '_jwt_new_access_token', None)
        access_cookie_name = getattr(request, '_jwt_access_cookie_name', None)
        if new_access and access_cookie_name:
            response.set_cookie(
                access_cookie_name,
                new_access,
                httponly=True,
                secure=False,
                samesite='Lax',
            )

        return response
