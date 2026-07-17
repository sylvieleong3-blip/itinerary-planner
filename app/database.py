import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "group_day_planner.db"

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass


def _resolve_db_path() -> Path:
    if configured := os.getenv("DATABASE_PATH"):
        return Path(configured)
    if os.getenv("RENDER"):
        return Path("/var/data/group_day_planner.db")
    return DEFAULT_DB_PATH


def _turso_configured() -> bool:
    turso_url = (os.getenv("TURSO_DATABASE_URL") or "").strip()
    auth_token = (os.getenv("TURSO_AUTH_TOKEN") or "").strip()
    if not turso_url or not auth_token:
        return False
    if not turso_url.startswith("libsql://"):
        return False
    placeholders = {
        "your-auth-token",
        "your-database-name-org.turso.io",
        "libsql://your-database-name-org.turso.io",
    }
    if turso_url.lower() in placeholders or auth_token.lower() in placeholders:
        return False
    if "your-" in turso_url.lower() or "your-" in auth_token.lower():
        return False
    return True


def _create_engine():
    if _turso_configured():
        turso_url = os.environ["TURSO_DATABASE_URL"].strip()
        auth_token = os.environ["TURSO_AUTH_TOKEN"].strip()
        local_path = os.getenv("TURSO_LOCAL_PATH", "").strip()

        if local_path:
            local_file = Path(local_path).expanduser().resolve()
            local_file.parent.mkdir(parents=True, exist_ok=True)
            return create_engine(
                f"sqlite+libsql:///{local_file.as_posix()}",
                connect_args={
                    "auth_token": auth_token,
                    "sync_url": turso_url,
                },
                poolclass=StaticPool,
            )

        # Remote Turso: avoid QueuePool — network connections must not be held
        # across slow async work (geocoding, seeding, weather fetches).
        return create_engine(
            f"sqlite+{turso_url}?secure=true",
            connect_args={"auth_token": auth_token},
            poolclass=NullPool,
        )

    db_path = _resolve_db_path()
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        db_path = Path("/tmp/group_day_planner.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)

    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def database_backend() -> str:
    if _turso_configured():
        return "turso-replica" if os.getenv("TURSO_LOCAL_PATH") else "turso"
    return "sqlite"


engine = _create_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def _migrate_columns() -> None:
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    with engine.begin() as conn:
        if "trips" in tables:
            trip_columns = {col["name"] for col in inspector.get_columns("trips")}
            if "num_days" not in trip_columns:
                conn.execute(text("ALTER TABLE trips ADD COLUMN num_days INTEGER DEFAULT 1"))
            if "notes" not in trip_columns:
                conn.execute(text("ALTER TABLE trips ADD COLUMN notes VARCHAR"))
            if "voting_enabled" not in trip_columns:
                conn.execute(text("ALTER TABLE trips ADD COLUMN voting_enabled BOOLEAN DEFAULT 1"))

        if "activities" in tables:
            columns = {col["name"] for col in inspector.get_columns("activities")}
            if "photo_url" not in columns:
                conn.execute(text("ALTER TABLE activities ADD COLUMN photo_url VARCHAR"))
            if "photo_path" not in columns:
                conn.execute(text("ALTER TABLE activities ADD COLUMN photo_path VARCHAR"))
            if "day_number" not in columns:
                conn.execute(text("ALTER TABLE activities ADD COLUMN day_number INTEGER DEFAULT 1"))
            if "is_suggested" not in columns:
                conn.execute(text("ALTER TABLE activities ADD COLUMN is_suggested BOOLEAN DEFAULT 0"))
                conn.execute(
                    text(
                        "UPDATE activities SET is_suggested = 1 "
                        "WHERE notes LIKE 'Suggested for Day%'"
                    )
                )
            if "category" not in columns:
                conn.execute(text("ALTER TABLE activities ADD COLUMN category VARCHAR DEFAULT 'activity'"))
            if "sort_order" not in columns:
                conn.execute(text("ALTER TABLE activities ADD COLUMN sort_order INTEGER DEFAULT 0"))

        if "members" in tables:
            member_columns = {col["name"] for col in inspector.get_columns("members")}
            if "notify_email" not in member_columns:
                conn.execute(text("ALTER TABLE members ADD COLUMN notify_email BOOLEAN DEFAULT 1"))

        if "expenses" in tables:
            expense_columns = {col["name"] for col in inspector.get_columns("expenses")}
            if "currency" not in expense_columns:
                conn.execute(text("ALTER TABLE expenses ADD COLUMN currency VARCHAR DEFAULT 'USD'"))


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    """Short-lived session for background tasks."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
