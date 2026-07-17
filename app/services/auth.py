import re

import bcrypt
from sqlalchemy.orm import Session

from app.models import User
from app.services.security import create_session_token as _create_session_token
from app.services.security import get_secret_key, read_session_token as _read_session_token

SESSION_COOKIE = "gdp_user_session"
SESSION_SHORT_AGE = 60 * 60 * 24
SESSION_LONG_AGE = 60 * 60 * 24 * 30

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_session_token(user_id: str) -> str:
    get_secret_key()
    return _create_session_token(user_id)


def read_session_token(token: str, *, max_age: int) -> str | None:
    get_secret_key()
    return _read_session_token(token, max_age=max_age)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email(email: str) -> str | None:
    normalized = normalize_email(email)
    if not normalized or not EMAIL_RE.match(normalized):
        return "Enter a valid email address."
    return None


def validate_password(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters."
    return None


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == normalize_email(email)).first()


def get_user_by_id(db: Session, user_id: str) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_user_from_request(request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    for max_age in (SESSION_LONG_AGE, SESSION_SHORT_AGE):
        user_id = read_session_token(token, max_age=max_age)
        if user_id:
            return get_user_by_id(db, user_id)
    return None
