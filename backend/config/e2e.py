import uuid

from .settings import *  # noqa: F403 -- inherit app settings for a disposable browser-test DB
from .settings import CACHES, DATABASES, MAILERS

DATABASES["default"]["TEST"] = {"NAME": "test_lattice_browser"}
CACHES["default"]["KEY_PREFIX"] = f"lattice_browser_{uuid.uuid4().hex}"
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:4411"]
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
APP_ORIGIN = "http://127.0.0.1:4411"
MAILERS["default"]["OPTIONS"]["host"] = "127.0.0.1"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
STORAGE_ROOT = REPO_ROOT / ".data" / "browser-storage"  # noqa: F405
