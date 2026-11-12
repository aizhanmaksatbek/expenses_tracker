import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import AuthSession, User

DbSession = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: AuthSession


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_auth_context(request: Request, db: DbSession) -> AuthContext:
    token = request.cookies.get("expense_session")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required.")

    auth_session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == _token_hash(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(timezone.utc),
        )
    )
    if auth_session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is invalid or expired.")

    user = db.get(User, auth_session.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session user no longer exists.")
    return AuthContext(user=user, session=auth_session)


def get_current_user(context: Annotated[AuthContext, Depends(get_auth_context)]) -> User:
    return context.user


async def require_csrf(
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> None:
    supplied_token = request.headers.get("x-csrf-token")
    if supplied_token is None and request.headers.get("content-type", "").startswith(
        "application/x-www-form-urlencoded"
    ):
        form_data = await request.form()
        supplied_token = str(form_data.get("csrf_token", ""))
    if not supplied_token or not secrets.compare_digest(supplied_token, context.session.csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token is missing or invalid.")


def create_session(db: Session, user: User) -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    settings = get_settings()
    session = AuthSession(
        user_id=user.id,
        token_hash=_token_hash(raw_token),
        csrf_token=csrf_token,
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=settings.session_lifetime_seconds),
    )
    db.add(session)
    db.commit()
    return raw_token, csrf_token


def set_session_cookie(response: Response, raw_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        "expense_session",
        raw_token,
        max_age=settings.session_lifetime_seconds,
        httponly=True,
        secure=settings.environment.lower() == "production",
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie("expense_session", path="/", httponly=True, samesite="lax")


def anonymous_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def validate_anonymous_csrf(request: Request, token: str | None) -> None:
    cookie_token = request.cookies.get("expense_pre_auth_csrf", "")
    if not cookie_token or not token or not secrets.compare_digest(cookie_token, token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token is missing or invalid.")
