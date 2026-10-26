from collections import defaultdict
import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from api.deps import SessionUser, clear_session_cookie, require_session, set_session_cookie
from api.schemas import LoginRequest, PublicUser, RegisterRequest
from services.auth_service import authenticate_user, register_user


router = APIRouter(prefix="/api/auth", tags=["auth"])

# Rate limiting storage: (username_lower, ip) -> list of failure timestamps
_failed_attempts: dict[tuple[str, str], list[float]] = defaultdict(list)
RATE_LIMIT_WINDOW_SECONDS = 600.0  # 10 minutes
RATE_LIMIT_MAX_ATTEMPTS = 5


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def _check_rate_limit(username: str, ip: str) -> None:
    now = time.time()
    key = (username.strip().lower(), ip)
    valid_attempts = [t for t in _failed_attempts[key] if now - t < RATE_LIMIT_WINDOW_SECONDS]
    _failed_attempts[key] = valid_attempts
    if len(valid_attempts) >= RATE_LIMIT_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please wait 10 minutes before trying again.",
        )


def _record_failure(username: str, ip: str) -> None:
    now = time.time()
    key = (username.strip().lower(), ip)
    _failed_attempts[key].append(now)


def _clear_failures(username: str, ip: str) -> None:
    key = (username.strip().lower(), ip)
    _failed_attempts.pop(key, None)


def reset_rate_limits() -> None:
    """Helper for testing to reset rate limit states."""
    _failed_attempts.clear()


def _public_user(user: SessionUser) -> PublicUser:
    return PublicUser(username=user.username, business_name=user.business_name)


@router.post("/register", response_model=PublicUser, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response) -> PublicUser:
    success, message = register_user(payload.username, payload.password, payload.business_name)
    if not success:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)

    user = authenticate_user(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Account created, but sign-in failed. Please try logging in.")

    session_user = SessionUser(user.tenant_id, user.username, user.business_name)
    set_session_cookie(response, session_user)
    return _public_user(session_user)


@router.post("/login", response_model=PublicUser)
def login(payload: LoginRequest, request: Request, response: Response) -> PublicUser:
    ip = _get_client_ip(request)
    _check_rate_limit(payload.username, ip)

    user = authenticate_user(payload.username, payload.password)
    if user is None:
        _record_failure(payload.username, ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")

    _clear_failures(payload.username, ip)
    session_user = SessionUser(user.tenant_id, user.username, user.business_name)
    set_session_cookie(response, session_user)
    return _public_user(session_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=PublicUser)
def me(user: SessionUser = Depends(require_session)) -> PublicUser:
    return _public_user(user)
