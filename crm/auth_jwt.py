import base64
import hashlib
import hmac
import json
import time

from django.conf import settings


JWT_COOKIE_NAME = "crm_access_token"
JWT_MAX_AGE = 60 * 60 * 12


def _b64encode(payload):
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _b64decode(payload):
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode((payload + padding).encode("ascii"))


def _signature(message):
    return _b64encode(hmac.new(settings.SECRET_KEY.encode("utf-8"), message.encode("ascii"), hashlib.sha256).digest())


def gerar_token(user):
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
    payload = _b64encode(
        json.dumps(
            {
                "sub": user.pk,
                "username": user.username,
                "iat": int(time.time()),
                "exp": int(time.time()) + JWT_MAX_AGE,
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    message = f"{header}.{payload}"
    return f"{message}.{_signature(message)}"


def validar_token(token):
    try:
        header, payload, signature = token.split(".")
    except ValueError:
        return None

    message = f"{header}.{payload}"
    if not hmac.compare_digest(_signature(message), signature):
        return None

    try:
        data = json.loads(_b64decode(payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None

    if int(data.get("exp", 0)) < int(time.time()):
        return None
    return data
