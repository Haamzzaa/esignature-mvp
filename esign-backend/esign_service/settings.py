
from pathlib import Path
from corsheaders.defaults import default_headers
CORS_ALLOW_HEADERS = list(default_headers)
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
load_dotenv()
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
import os
# pyrefly: ignore [missing-import]
import dj_database_url

DEBUG = os.environ.get("DEBUG", "False") == "True"

SECRET_KEY = os.environ.get("SECRET_KEY")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is required.")

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "esignature-mvp.onrender.com",
]

render_external_hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if render_external_hostname:
    ALLOWED_HOSTS.append(render_external_hostname)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'esign',
    'drf_yasg',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'esign.middleware.BrowserSecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    # ── Observability: must come first so request_id is set before all downstream ──
    'esign.middleware.RequestIDMiddleware',
    'esign.middleware.RequestTimingMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'esign_service.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'esign_service.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/


STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# CORS Configuration
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://esignature-mvp.vercel.app",
]

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^http://localhost:\d+$",
    r"^http://127\.0\.0\.1:\d+$",
]

CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-participant-token",
    "x-request-id",
]
# CSRF Configuration
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://esignature-mvp.vercel.app",
    "https://esignature-mvp.onrender.com",
]

X_FRAME_OPTIONS = "DENY"

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
}

# Email Configuration
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@esignature-mvp.com")

EMAIL_HOST = os.environ.get("EMAIL_HOST")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 2525))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"

# Celery Configuration
USE_CELERY = os.getenv("USE_CELERY", "False").lower() == "true"

CELERY_BROKER_URL = (
    os.getenv("REDIS_INTERNAL_URL")
    or os.getenv("REDIS_URL")
    or "redis://localhost:6379/0"
)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_SOFT_TIME_LIMIT = 30
CELERY_TASK_TIME_LIMIT = 60

import sys
if 'test' in sys.argv:
    USE_CELERY = True
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True

# Face Verification Configuration
FACE_MATCH_THRESHOLD = 0.6

# Identity Verification Configuration
IDENTITY_MATCH_THRESHOLD = 0.85


# ── Observability: Structured Logging ────────────────────────────────────────
# Console-first: always enabled. File logging is optional and opt-in.
# Enable file logging by setting ESIGN_LOG_FILE_ENABLED=True in the environment.
# Log level is controlled by ESIGN_LOG_LEVEL (default: INFO).

_LOG_LEVEL = os.environ.get("ESIGN_LOG_LEVEL", "INFO").upper()
_LOG_FILE_ENABLED = os.environ.get("ESIGN_LOG_FILE_ENABLED", "False") == "True"
_LOG_FILE_PATH = os.environ.get("ESIGN_LOG_FILE_PATH", str(BASE_DIR / "logs" / "esign.log"))

_LOG_FORMAT = (
    "%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s %(message)s"
)

if _LOG_FILE_ENABLED:
    import pathlib
    pathlib.Path(_LOG_FILE_PATH).parent.mkdir(parents=True, exist_ok=True)

_handlers = ["console"]
if _LOG_FILE_ENABLED:
    _handlers.append("file")

# Build the handlers dict dynamically — only include file handler when enabled
_logging_handlers = {
    "console": {
        "class": "logging.StreamHandler",
        "formatter": "structured",
        "filters": ["request_id"],
    },
}
if _LOG_FILE_ENABLED:
    _logging_handlers["file"] = {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": _LOG_FILE_PATH,
        "maxBytes": 10 * 1024 * 1024,  # 10 MB
        "backupCount": 5,
        "formatter": "structured",
        "filters": ["request_id"],
    }

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {
            "()": "esign.log_filters.RequestIDFilter",
        },
    },
    "formatters": {
        "structured": {
            "format": _LOG_FORMAT,
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
    },
    "handlers": _logging_handlers,
    "loggers": {
        "esign": {
            "handlers": _handlers,
            "level": _LOG_LEVEL,
            "propagate": False,
        },
        "esign.middleware": {
            "handlers": _handlers,
            "level": _LOG_LEVEL,
            "propagate": False,
        },
        "esign.health": {
            "handlers": _handlers,
            "level": _LOG_LEVEL,
            "propagate": False,
        },
        "esign.events": {
            "handlers": _handlers,
            "level": _LOG_LEVEL,
            "propagate": False,
        },
        "services": {
            "handlers": _handlers,
            "level": _LOG_LEVEL,
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

# ── Browser Security, HTTP headers & Cookie Hardening ──
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # Intentionally readable by frontend JS for AJAX CSRF headers
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

# ── Provider Configuration ───────────────────────────────────────────────
IDENTITY_OCR_PROVIDER = "gemini"
CONTRACT_OCR_PROVIDER = "gemini"
FACE_PROVIDER = "insightface"
LIVENESS_PROVIDER = "internal"
NOTIFICATION_PROVIDER = "brevo"

