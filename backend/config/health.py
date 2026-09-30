from tempfile import TemporaryFile

from django.conf import settings
from django.db import connection
from django.db.utils import DatabaseError
from drf_spectacular.utils import extend_schema
from redis import Redis
from redis.exceptions import RedisError
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


class LiveStatus(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok"])


class ReadyStatus(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "unavailable"])
    checks = serializers.DictField(child=serializers.BooleanField())


@extend_schema(responses=LiveStatus, auth=[])
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def live(request):
    return Response({"status": "ok"}, headers={"Cache-Control": "no-store"})


@extend_schema(responses={200: ReadyStatus, 503: ReadyStatus}, auth=[])
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def ready(request):
    checks = {"database": False, "redis": False, "storage": False}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            checks["database"] = cursor.fetchone()[0]
    except (DatabaseError, OSError):
        pass  # Failure is represented in the safe response, never as a raw connection exception.
    try:
        with Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2
        ) as redis:
            checks["redis"] = bool(redis.ping())
    except (RedisError, OSError):
        pass
    try:
        with TemporaryFile(dir=settings.STORAGE_ROOT) as probe:
            probe.write(b"ready")
            probe.flush()
        checks["storage"] = True
    except OSError:
        pass
    healthy = all(checks.values())
    return Response(
        {"status": "ok" if healthy else "unavailable", "checks": checks},
        status=200 if healthy else 503,
        headers={"Cache-Control": "no-store"},
    )
