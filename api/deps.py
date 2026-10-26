"""Authentication dependencies for signed, httpOnly browser sessions."""

from dataclasses import dataclass
import os

from fastapi import HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


SESSION_COOKIE_NAME = "bizintel_session"
SESSION_SALT = "bizintel-browser-session-v1"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7


@dataclass(frozen=True)
class SessionUser:
    """Safe identity fields stored in the signed cookie; never credentials."""

    tenant_id: str
    username: str
    business_name: str


INSECURE_PLACEHOLDER_SECRETS = {
    "replace-with-a-long-random-secret",
    "replace-with-a-long-random-value",
    "your-secret-key",
    "change-me",
}


def validate_session_secret() -> str:
    """
    Validate that BIZINTEL_SESSION_SECRET is configured and not the insecure placeholder.
    Refuses to run if the secret is missing or default.
    """
    secret = os.environ.get("BIZINTEL_SESSION_SECRET", "").strip()
    if not secret or secret in INSECURE_PLACEHOLDER_SECRETS:
        raise RuntimeError(
            "BIZINTEL_SESSION_SECRET is missing or still set to the insecure placeholder. "
            "Please configure a long, random secret in your .env file."
        )
    return secret


def is_cookie_secure() -> bool:
    """Return True if session cookies should have the secure flag set (HTTPS)."""
    return os.environ.get("BIZINTEL_COOKIE_SECURE", "false").strip().lower() in ("true", "1", "yes")


def _serializer() -> URLSafeTimedSerializer:
    secret = validate_session_secret()
    return URLSafeTimedSerializer(secret_key=secret, salt=SESSION_SALT)


def set_session_cookie(response: Response, user: SessionUser) -> None:
    """Write a signed identity cookie after successful registration or login."""
    value = _serializer().dumps({
        "tenant_id": user.tenant_id,
        "username": user.username,
        "business_name": user.business_name,
    })
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=value,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=is_cookie_secure(),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


def require_session(request: Request) -> SessionUser:
    """Return the authenticated owner. Tenant IDs never come from requests."""
    raw_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in to continue.")

    try:
        payload = _serializer().loads(raw_cookie, max_age=SESSION_MAX_AGE_SECONDS)
        user = SessionUser(
            tenant_id=str(payload["tenant_id"]),
            username=str(payload["username"]),
            business_name=str(payload["business_name"]),
        )
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired. Please log in again.")

    if not all((user.tenant_id, user.username, user.business_name)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session is invalid. Please log in again.")
    return user
