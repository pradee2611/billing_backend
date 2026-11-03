import hashlib
import hmac

from django.conf import settings
from django.core import signing
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

SALT = "billing-login"


class Operator:
    """The signed-in shop user. There is a single account, configured in the environment."""

    is_authenticated = True

    def __init__(self, username):
        self.username = username


def _password_fingerprint():
    # Changing the password in .env invalidates every token issued before.
    return hashlib.sha256(settings.APP_PASSWORD.encode()).hexdigest()[:16]


def make_token(username):
    return signing.dumps({"u": username, "p": _password_fingerprint()}, salt=SALT)


class BearerAuthentication(BaseAuthentication):
    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != b"bearer":
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("Invalid token.")
        try:
            data = signing.loads(parts[1].decode(), salt=SALT, max_age=settings.AUTH_TOKEN_MAX_AGE)
        except (signing.BadSignature, UnicodeDecodeError):
            raise AuthenticationFailed("Invalid or expired token.")
        if not hmac.compare_digest(data.get("p", ""), _password_fingerprint()):
            raise AuthenticationFailed("Password changed, please sign in again.")
        return Operator(data["u"]), None

    def authenticate_header(self, request):
        return "Bearer"  # makes DRF answer 401 instead of 403
