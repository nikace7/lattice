from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView


class UserData(serializers.Serializer):
    id = serializers.UUIDField()
    username = serializers.CharField()


class SessionData(serializers.Serializer):
    user = UserData(allow_null=True)
    csrfToken = serializers.CharField()


class Credentials(serializers.Serializer):
    username = serializers.CharField(max_length=150, validators=[UnicodeUsernameValidator()])
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)


class Registration(Credentials):
    email = serializers.EmailField(max_length=254)

    def validate_email(self, value):
        return value.lower()


def session_data(request):
    return {
        "user": {"id": str(request.user.pk), "username": request.user.username}
        if request.user.is_authenticated
        else None,
        "csrfToken": get_token(request),
    }


class SessionView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=SessionData)
    def get(self, request):
        return Response(session_data(request))


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    @extend_schema(request=Credentials, responses=SessionData)
    def post(self, request):
        data = Credentials(data=request.data)
        data.is_valid(raise_exception=True)
        user = authenticate(request, **data.validated_data)
        if user is None:
            raise AuthenticationFailed("The username or password is incorrect.")
        login(request, user)
        return Response(session_data(request))


class RegisterView(LoginView):
    @extend_schema(request=Registration, responses={201: SessionData})
    def post(self, request):
        data = Registration(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        user = get_user_model()(username=values["username"], email=values.get("email", ""))
        try:
            validate_password(values["password"], user)
        except DjangoValidationError as error:
            raise ValidationError({"password": error.messages}) from error
        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(**values)
        except IntegrityError as error:
            raise ValidationError(
                "Unable to register with these details. Sign in or use account recovery."
            ) from error
        login(request, user)
        return Response(session_data(request), status=201)


class LogoutView(APIView):
    @extend_schema(request=None, responses=SessionData)
    def post(self, request):
        logout(request)
        return Response(session_data(request))
