from .settings import *  # noqa: F403 -- inherit app settings for a disposable browser-test DB
from .settings import CACHES, DATABASES

DATABASES["default"]["TEST"] = {"NAME": "test_lattice_browser"}
CACHES["default"]["KEY_PREFIX"] = "lattice_browser"
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:4411"]
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
APP_ORIGIN = "http://127.0.0.1:4411"
EMAIL_HOST = "127.0.0.1"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
