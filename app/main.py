import logging

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import database_backend, init_db
from app.middleware import csrf_middleware
from app.routers import auth, pages
from app.services.photos import UPLOAD_DIR
from app.services.security import get_secret_key

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_secret_key()
    logger.info("Database backend: %s", database_backend())
    init_db()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Itinerary Planner", lifespan=lifespan)
app.middleware("http")(csrf_middleware)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
app.include_router(auth.router)
app.include_router(pages.router)
