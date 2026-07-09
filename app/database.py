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
