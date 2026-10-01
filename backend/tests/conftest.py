import pytest


@pytest.fixture(autouse=True)
def isolated_test_cache(settings):
    # Clearing test rate limits must never flush the application's Redis broker.
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
