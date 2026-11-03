import hmac

from django.conf import settings
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .authentication import make_token


def _same(a, b):
    return hmac.compare_digest(a.encode(), b.encode())


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False)


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # Check both fields every time so response timing does not reveal which one was wrong.
        user_ok = _same(data["username"], settings.APP_USERNAME)
        pass_ok = _same(data["password"], settings.APP_PASSWORD)
        if not (settings.APP_PASSWORD and user_ok and pass_ok):
            return Response({"detail": "Wrong username or password."}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"token": make_token(settings.APP_USERNAME), "username": settings.APP_USERNAME})
