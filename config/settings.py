"""
Django settings for config project.
"""

import os
from datetime import timedelta
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env_file(BASE_DIR / '.env')


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DJANGO_DEBUG', 'False').strip().lower() == 'true'

ALLOWED_HOSTS = os.getenv(
    'ALLOWED_HOSTS',
    '127.0.0.1,localhost,testserver'
).split(',')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'rest_framework',
    'rest_framework.authtoken',
    'drf_spectacular',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'dj_rest_auth',
    'dj_rest_auth.registration',
    'rest_framework_simplejwt.token_blacklist',
    'auth.apps.AuthConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'auth.middleware.UploadStorageErrorMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'auth.middleware.EnsureDefaultAdminMiddleware',
    'auth.middleware.JwtCookieAuthMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'auth.context_processors.admin_header_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'mini_app_db'),
        'USER': os.getenv('POSTGRES_USER', 'mini_app_user'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'mini_app_pass'),
        'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

USE_MANIFEST_STATIC_FILES = (
    os.getenv('USE_MANIFEST_STATIC_FILES', 'false' if DEBUG else 'true').strip().lower() == 'true'
)
USE_S3 = os.getenv('USE_S3', 'false').strip().lower() == 'true'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': (
            'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'
            if USE_MANIFEST_STATIC_FILES
            else 'django.contrib.staticfiles.storage.StaticFilesStorage'
        ),
    },
}

if USE_S3:
    selectel_access_key = os.getenv('SELECTEL_ACCESS_KEY', '').strip()
    selectel_secret_key = os.getenv('SELECTEL_SECRET_KEY', '').strip()
    selectel_bucket_name = os.getenv('SELECTEL_BUCKET_NAME', 'ktfit').strip()
    selectel_endpoint_url = os.getenv('SELECTEL_ENDPOINT_URL', 'https://s3.ru-3.storage.selcloud.ru').strip()
    selectel_region_name = os.getenv('SELECTEL_REGION_NAME', 'ru-3').strip()
    selectel_custom_domain = os.getenv('SELECTEL_CUSTOM_DOMAIN', '').strip()

    s3_common_options = {
        'access_key': selectel_access_key,
        'secret_key': selectel_secret_key,
        'bucket_name': selectel_bucket_name,
        'endpoint_url': selectel_endpoint_url,
        'region_name': selectel_region_name,
        'signature_version': 's3v4',
        'default_acl': 'public-read',
        'querystring_auth': False,
        'verify': True,
        'file_overwrite': False,
    }

    if selectel_custom_domain:
        s3_common_options['custom_domain'] = selectel_custom_domain

    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3.S3Storage',
            'OPTIONS': {
                **s3_common_options,
                'location': 'media',
            },
        },
        'staticfiles': {
            'BACKEND': (
                'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'
                if USE_MANIFEST_STATIC_FILES
                else 'storages.backends.s3.S3Storage'
            ),
            'OPTIONS': {
                **s3_common_options,
                'location': 'static',
                'file_overwrite': True,
            },
        },
    }

    if selectel_custom_domain:
        MEDIA_URL = f'https://{selectel_custom_domain}/media/'
        STATIC_URL = f'https://{selectel_custom_domain}/static/'
    else:
        base_media = f'{selectel_endpoint_url}/{selectel_bucket_name}/media/'
        base_static = f'{selectel_endpoint_url}/{selectel_bucket_name}/static/'
        MEDIA_URL = base_media
        STATIC_URL = base_static

    AWS_S3_REGION_NAME = selectel_region_name
    AWS_S3_USE_SSL = True
    AWS_S3_MAX_MEMORY_SIZE = int(os.getenv('AWS_S3_MAX_MEMORY_SIZE', str(100 * 1024 * 1024)))

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGIN_ON_PASSWORD_RESET = True
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
SESSION_COOKIE_AGE = 3 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = False

EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '1025'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'False').lower() == 'true'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False').lower() == 'true'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '10'))
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'no-reply@mini-app.local')
TELEGRAM_BOT_USERNAME = os.getenv('TELEGRAM_BOT_USERNAME', '')
TELEGRAM_WEBHOOK_SECRET = os.getenv('TELEGRAM_WEBHOOK_SECRET', '')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_SUPPORT_CHAT_ID = os.getenv('TELEGRAM_SUPPORT_CHAT_ID', '')
SUPPORT_EMAIL_TO = os.getenv('SUPPORT_EMAIL_TO', EMAIL_HOST_USER or DEFAULT_FROM_EMAIL)
REGISTRATION_ACCESS_KEY = os.getenv('REGISTRATION_ACCESS_KEY', '12345678').strip()

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

REST_USE_JWT = True

REST_AUTH = {
    'USE_JWT': True,
    'JWT_AUTH_COOKIE': 'access_token',
    'JWT_AUTH_REFRESH_COOKIE': 'refresh_token',
}

REST_AUTH_REGISTER_SERIALIZERS = {
    'REGISTER_SERIALIZER': 'auth.serializers.CustomRegisterSerializer',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'AUTH_HEADER_TYPES': ('Bearer',),
    'BLACKLIST_AFTER_ROTATION': True,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Mini App API',
    'DESCRIPTION': 'API documentation for Mini App',
    'VERSION': '1.0.0',
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'loggers': {
        'auth': {
            'handlers': ['console'],
            'level': os.getenv('AUTH_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}

# Upload limits for larger files (for example videos)
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('DATA_UPLOAD_MAX_MEMORY_SIZE', str(100 * 1024 * 1024)))
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('FILE_UPLOAD_MAX_MEMORY_SIZE', str(100 * 1024 * 1024)))
