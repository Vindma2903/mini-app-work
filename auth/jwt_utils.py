from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken


def get_jwt_cookie_names():
    rest_auth = getattr(settings, 'REST_AUTH', {})
    access_name = rest_auth.get('JWT_AUTH_COOKIE', 'access_token')
    refresh_name = rest_auth.get('JWT_AUTH_REFRESH_COOKIE', 'refresh_token')
    return access_name, refresh_name


def build_token_pair_for_user(user):
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), str(refresh)


def set_jwt_cookies(response, access_token, refresh_token=None):
    access_name, refresh_name = get_jwt_cookie_names()

    response.set_cookie(
        access_name,
        access_token,
        httponly=True,
        secure=False,
        samesite='Lax',
    )

    if refresh_token is not None:
        response.set_cookie(
            refresh_name,
            refresh_token,
            httponly=True,
            secure=False,
            samesite='Lax',
        )

    return response


def clear_jwt_cookies(response):
    access_name, refresh_name = get_jwt_cookie_names()
    response.delete_cookie(access_name, samesite='Lax')
    response.delete_cookie(refresh_name, samesite='Lax')
    return response
