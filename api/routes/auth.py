"""Authentication routes backed by the existing authentication service."""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.deps import SessionUser, clear_session_cookie, require_session, set_session_cookie
from api.schemas import LoginRequest, PublicUser, RegisterRequest
from services.auth_service import authenticate_user, register_user


router = APIRouter(prefix="/api/auth", tags=["auth"])


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
def login(payload: LoginRequest, response: Response) -> PublicUser:
    user = authenticate_user(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")

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
