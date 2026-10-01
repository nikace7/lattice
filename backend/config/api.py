import uuid
from urllib.parse import urlsplit

from django.http import JsonResponse
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException
from rest_framework.pagination import CursorPagination


class BrowserSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        # Login/registration need CSRF checks even before the user has a session.
        self.enforce_csrf(request)
        return super().authenticate(request)

    def authenticate_header(self, request):
        return "Session"


class Conflict(APIException):
    status_code = 409
    default_detail = "This item changed. Refresh and try again."
    default_code = "conflict"


class Pages(CursorPagination):
    page_size = 20
    page_size_query_param = "pageSize"
    max_page_size = 100
    ordering = "id"

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        for direction in ("next", "previous"):
            if response.data[direction]:
                url = urlsplit(response.data[direction])
                response.data[direction] = url._replace(scheme="", netloc="").geturl()
        return response


def api_exception_handler(exc, context):
    from rest_framework.views import exception_handler

    response = exception_handler(exc, context)
    if response is not None:
        detail = response.data
        response.data = {
            "error": {
                "code": getattr(exc, "default_code", "request_error"),
                "message": str(detail.get("detail", "Check the submitted fields."))
                if isinstance(detail, dict)
                else "Check the submitted fields.",
                "requestId": str(uuid.uuid4()),
            }
        }
        if isinstance(detail, dict) and "detail" not in detail:
            response.data["error"]["fieldErrors"] = detail
        response["Cache-Control"] = "no-store"
    return response


class PrivateApiMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "no-store"
        return response


def csrf_failure(request, reason=""):
    return JsonResponse(
        {
            "error": {
                "code": "csrf_failed",
                "message": "Refresh the page and try again.",
                "requestId": str(uuid.uuid4()),
            }
        },
        status=403,
    )
