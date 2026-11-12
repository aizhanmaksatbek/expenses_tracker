from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import (
    AuthContext,
    DbSession,
    anonymous_csrf_token,
    clear_session_cookie,
    create_session,
    get_auth_context,
    require_csrf,
    set_session_cookie,
    validate_anonymous_csrf,
)
from app.api.request_data import parse_request_data
from app.core.config import get_settings
from app.models import Category, User
from app.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from app.security.passwords import hash_password, verify_password
from app.services.expenses import DEFAULT_CATEGORIES

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _validation_response(exc: ValidationError, is_form: bool):
    errors = [error["msg"] for error in exc.errors()]
    if is_form:
        return JSONResponse(
            {"detail": errors},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return JSONResponse(
        {"detail": jsonable_encoder(exc.errors())},
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


async def _request_data(request: Request) -> tuple[dict, bool]:
    return await parse_request_data(request)


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    token = anonymous_csrf_token()
    response = templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={"csrf_token": token},
    )
    response.set_cookie(
        "expense_pre_auth_csrf",
        token,
        httponly=True,
        secure=get_settings().environment.lower() == "production",
        samesite="lax",
        path="/",
    )
    return response


@router.get("/auth/csrf")
def csrf_token(response: Response) -> dict[str, str]:
    token = anonymous_csrf_token()
    response.set_cookie(
        "expense_pre_auth_csrf",
        token,
        httponly=True,
        secure=get_settings().environment.lower() == "production",
        samesite="lax",
        path="/",
    )
    return {"csrf_token": token}


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    token = anonymous_csrf_token()
    response = templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={"csrf_token": token},
    )
    response.set_cookie(
        "expense_pre_auth_csrf",
        token,
        httponly=True,
        secure=get_settings().environment.lower() == "production",
        samesite="lax",
        path="/",
    )
    return response


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(request: Request, db: DbSession):
    data, is_form = await _request_data(request)
    validate_anonymous_csrf(request, data.get("csrf_token"))
    data.pop("csrf_token", None)
    try:
        registration = RegisterRequest.model_validate(data)
    except ValidationError as exc:
        return _validation_response(exc, is_form)

    existing = db.scalar(
        select(User.id).where(
            (func.lower(User.username) == registration.username)
            | (func.lower(User.email) == str(registration.email))
        )
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username or email is already registered.")

    user = User(
        username=registration.username,
        email=str(registration.email),
        password_hash=hash_password(registration.password),
    )
    db.add(user)
    try:
        db.flush()
        db.add_all(
            Category(user_id=user.id, name=category_name) for category_name in DEFAULT_CATEGORIES
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Username or email is already registered."
        ) from None
    db.refresh(user)
    if is_form:
        return RedirectResponse("/login?registered=1", status_code=status.HTTP_303_SEE_OTHER)
    return UserResponse.model_validate(user)


@router.post("/auth/login")
async def login(request: Request, db: DbSession):
    data, is_form = await _request_data(request)
    validate_anonymous_csrf(request, data.get("csrf_token"))
    data.pop("csrf_token", None)
    try:
        credentials = LoginRequest.model_validate(data)
    except ValidationError as exc:
        return _validation_response(exc, is_form)

    login_name = credentials.username.strip().lower()
    user = db.scalar(
        select(User).where(
            (func.lower(User.username) == login_name) | (func.lower(User.email) == login_name)
        )
    )
    if user is None or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username/email or password.")

    raw_token, csrf_token = create_session(db, user)
    if is_form:
        response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    else:
        response = JSONResponse({"user": UserResponse.model_validate(user).model_dump(mode="json")})
        response.headers["X-CSRF-Token"] = csrf_token
    set_session_cookie(response, raw_token)
    response.delete_cookie("expense_pre_auth_csrf", path="/")
    return response


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    db: DbSession,
    context: AuthContext = Depends(get_auth_context),
    _csrf: None = Depends(require_csrf),
) -> Response:
    context.session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    return response
