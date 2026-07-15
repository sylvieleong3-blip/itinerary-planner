from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import templates
from app.models import User
from app.services.auth import (
    SESSION_COOKIE,
    SESSION_LONG_AGE,
    SESSION_SHORT_AGE,
    create_session_token,
    get_user_by_email,
    hash_password,
    normalize_email,
    validate_email,
    validate_password,
    verify_password,
)

router = APIRouter()


def _set_session_cookie(response: RedirectResponse, request: Request, user_id: str, *, remember: bool) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user_id),
        max_age=SESSION_LONG_AGE if remember else SESSION_SHORT_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )


def _clear_session_cookie(response: RedirectResponse, request: Request) -> None:
    response.delete_cookie(SESSION_COOKIE, samesite="lax", secure=request.url.scheme == "https")


@router.post("/auth/signup")
async def signup(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    remember: str = Form(""),
    db: Session = Depends(get_db),
):
    email_error = validate_email(email)
    password_error = validate_password(password)
    name = display_name.strip()
    errors: list[str] = []
    if email_error:
        errors.append(email_error)
    if password_error:
        errors.append(password_error)
    if not name:
        errors.append("Enter your name.")
    if password != password_confirm:
        errors.append("Passwords do not match.")
    if not errors and get_user_by_email(db, email):
        errors.append("An account with this email already exists.")

    if errors:
        return templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "error": errors[0],
                "initial_view": "signup",
                "auth_email": normalize_email(email),
                "auth_name": name,
                "user": None,
            },
            status_code=400,
        )

    user = User(
        email=normalize_email(email),
        display_name=name,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()

    response = RedirectResponse(url="/", status_code=303)
    _set_session_cookie(response, request, user.id, remember=remember == "1")
    return response


@router.post("/auth/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "error": "Incorrect email or password.",
                "initial_view": "login",
                "auth_email": normalize_email(email),
                "user": None,
            },
            status_code=401,
        )

    response = RedirectResponse(url="/", status_code=303)
    _set_session_cookie(response, request, user.id, remember=remember == "1")
    return response


@router.post("/auth/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/", status_code=303)
    _clear_session_cookie(response, request)
    return response
