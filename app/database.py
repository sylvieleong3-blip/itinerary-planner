from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = "sqlite:///./group_day_planner.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def _migrate_columns() -> None:
    inspector = inspect(engine)
    if "activities" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("activities")}
    with engine.begin() as conn:
        if "photo_url" not in columns:
            conn.execute(text("ALTER TABLE activities ADD COLUMN photo_url VARCHAR"))
        if "photo_path" not in columns:
            conn.execute(text("ALTER TABLE activities ADD COLUMN photo_path VARCHAR"))


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
