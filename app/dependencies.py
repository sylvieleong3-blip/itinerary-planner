from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.services.distance import format_time_12h, maps_link_for_activity
from app.services.photos import activity_photo_url

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["activity_photo"] = activity_photo_url
templates.env.globals["maps_link_for"] = maps_link_for_activity
templates.env.globals["format_time_12h"] = format_time_12h


def member_cookie_key(share_code: str) -> str:
    return f"gdp_member_{share_code}"


def get_member_id(request: Request, share_code: str) -> str | None:
    return request.cookies.get(member_cookie_key(share_code))
