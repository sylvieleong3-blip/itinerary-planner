"""Pytest setup — always use local SQLite, never Turso, during tests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Set before app.database is imported (load_dotenv must not enable Turso).
_test_db = Path(tempfile.gettempdir()) / "group_day_planner_pytest.db"
os.environ["TURSO_DATABASE_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
os.environ.pop("TURSO_LOCAL_PATH", None)
os.environ.pop("RENDER", None)
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_PATH"] = str(_test_db)
