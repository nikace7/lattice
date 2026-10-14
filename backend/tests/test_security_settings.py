import json
import os
import subprocess
import sys
from pathlib import Path


def configuration(**overrides):
    env = {**os.environ, **overrides}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; from config import settings as s; "
                "print(json.dumps({name: getattr(s, name, None) for name in "
                "['SECURE_SSL_REDIRECT', 'SECURE_HSTS_SECONDS', 'SECURE_PROXY_SSL_HEADER', "
                "'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE', 'DEFAULT_FROM_EMAIL']}))"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_production_security_defaults_and_explicit_proxy_trust():
    production = configuration(
        DJANGO_DEBUG="false",
        APP_ORIGIN="https://lattice.example",
        DJANGO_TRUST_PROXY="false",
        SMTP_FROM_EMAIL="Lattice <mail@lattice.example>",
    )
    assert production == {
        "SECURE_SSL_REDIRECT": True,
        "SECURE_HSTS_SECONDS": 3600,
        "SECURE_PROXY_SSL_HEADER": None,
        "SESSION_COOKIE_SECURE": True,
        "CSRF_COOKIE_SECURE": True,
        "DEFAULT_FROM_EMAIL": "Lattice <mail@lattice.example>",
    }
    trusted = configuration(
        DJANGO_DEBUG="false", APP_ORIGIN="https://lattice.example", DJANGO_TRUST_PROXY="true"
    )
    assert trusted["SECURE_PROXY_SSL_HEADER"] == ["HTTP_X_FORWARDED_PROTO", "https"]


def test_local_http_remains_available():
    local = configuration(
        DJANGO_DEBUG="true", APP_ORIGIN="http://localhost:4400", DJANGO_TRUST_PROXY="false"
    )
    assert not local["SECURE_SSL_REDIRECT"]
    assert not local["SECURE_HSTS_SECONDS"]
    assert not local["SESSION_COOKIE_SECURE"]
