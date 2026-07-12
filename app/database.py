import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "group_day_planner.db"


def _resolve_db_path() -> Path:
    if configured := os.getenv("DATABASE_PATH"):
        return Path(configured)
    if os.getenv("RENDER"):
        return Path("/tmp/group_day_planner.db")
    return DEFAULT_DB_PATH


DB_PATH = _resolve_db_path()
try:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
except OSError:
    DB_PATH = Path("/tmp/group_day_planner.db")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

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
