from pathlib import Path
from urllib.parse import urlsplit

import environ
from django.core.exceptions import ImproperlyConfigured

from pipeline.embedding import REVISION

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent
env = environ.Env()
environ.Env.read_env(REPO_ROOT / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if SECRET_KEY == "CHANGE_ME" or len(SECRET_KEY) < 32:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY to a random value of at least 32 characters.")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
APP_ORIGIN = env("APP_ORIGIN", default="http://localhost:4400")
origin = urlsplit(APP_ORIGIN)
if origin.scheme not in {"http", "https"} or not origin.netloc or origin.path not in {"", "/"}:
    raise ImproperlyConfigured("APP_ORIGIN must be an HTTP(S) origin without a path.")
CSRF_TRUSTED_ORIGINS = [APP_ORIGIN.rstrip("/")]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "drf_spectacular",
    "modules.identity",
    "modules.workspaces",
    "modules.collections.apps.CollectionsConfig",
    "modules.audit",
    "modules.documents",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.api.PrivateApiMiddleware",
]
ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 0  # ASGI: do not retain per-thread connections.
DATABASES["default"]["OPTIONS"] = {"connect_timeout": 3}
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("Lattice requires PostgreSQL with pgvector.")
AUTH_USER_MODEL = "identity.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7
CSRF_FAILURE_VIEW = "config.api.csrf_failure"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = origin.scheme == "https" or not DEBUG
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["config.api.BrowserSessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "config.api.Pages",
    "EXCEPTION_HANDLER": "config.api.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {"auth": "20/minute", "recovery": "5/hour", "invitations": "30/hour"},
    "NUM_PROXIES": 0,
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Lattice API",
    "DESCRIPTION": "Lattice sessions, workspace membership and collection access.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}
REDIS_URL = env("REDIS_URL")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "lattice",
    }
}
CELERY_BROKER_URL = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TASK_IGNORE_RESULT = True
CELERY_IMPORTS = ("modules.documents.indexing",)
CELERY_TASK_ROUTES = {
    "modules.documents.indexing.*": {"queue": "ingestion"},
    "modules.documents.tasks.*": {"queue": "ingestion"},
    "modules.identity.tasks.*": {"queue": "ingestion"},
    "modules.ingestion.*": {"queue": "ingestion"},
    "modules.conversations.*": {"queue": "answers"},
}
CELERY_TIMEZONE = "UTC"
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    "recover-indexes": {
        "task": "modules.documents.indexing.recover_indexes",
        "schedule": 30.0,
    },
    "recover-extractions": {
        "task": "modules.documents.tasks.recover_extractions",
        "schedule": 30.0,
    },
}

STORAGE_ROOT = (REPO_ROOT / env("STORAGE_ROOT", default=".data/storage")).resolve()
PARSER_SPOOL_ROOT = (REPO_ROOT / env("PARSER_SPOOL_ROOT", default=".data/parser")).resolve()
PARSER_TIMEOUT_SECONDS = 330
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 26 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 1
FILE_UPLOAD_HANDLERS = [
    "modules.documents.uploads.BoundedUploadHandler",
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]
MODEL_CACHE_ROOT = (REPO_ROOT / env("MODEL_CACHE_ROOT", default=".data/models")).resolve()
if env("LOCAL_EMBED_MODEL_REVISION", default="") not in {"", REVISION}:
    raise ImproperlyConfigured("LOCAL_EMBED_MODEL_REVISION must match the pinned E5 revision.")
RAG_MODE = env("RAG_MODE", default="RETRIEVAL_ONLY")
if RAG_MODE not in {"LOCAL", "CLOUD", "RETRIEVAL_ONLY", "FIXTURE"}:
    raise ImproperlyConfigured("RAG_MODE must be LOCAL, CLOUD, RETRIEVAL_ONLY or FIXTURE.")
DEMO_MODE = env.bool("DEMO_MODE", default=False)
MAX_WORKSPACE_STORAGE_BYTES = env.int("MAX_WORKSPACE_STORAGE_BYTES", default=2147483648)
MAX_DAILY_ANSWER_TOKENS = env.int("MAX_DAILY_ANSWER_TOKENS", default=100000)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("SMTP_HOST", default="localhost")
EMAIL_PORT = env.int("SMTP_PORT", default=1026)
EMAIL_TIMEOUT = 5
DEFAULT_FROM_EMAIL = "Lattice <noreply@lattice.invalid>"
