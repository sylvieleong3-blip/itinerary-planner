from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.services.categories import ACTIVITY_CATEGORIES, activity_category
from app.services.dates import format_day_date, trip_date_range
from app.services.distance import format_time_12h, maps_link_for_activity
from app.services.photos import activity_photo_url

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["activity_photo"] = activity_photo_url
templates.env.globals["maps_link_for"] = maps_link_for_activity
templates.env.globals["format_time_12h"] = format_time_12h
templates.env.globals["format_day_date"] = format_day_date
templates.env.globals["trip_date_range"] = trip_date_range
templates.env.globals["activity_category"] = activity_category
templates.env.globals["activity_categories"] = ACTIVITY_CATEGORIES


def member_cookie_key(share_code: str) -> str:
    return f"gdp_member_{share_code}"


def get_member_id(request: Request, share_code: str) -> str | None:
    return request.cookies.get(member_cookie_key(share_code))


def set_member_cookie(response: RedirectResponse, request: Request, share_code: str, member_id: str) -> None:
    response.set_cookie(
        member_cookie_key(share_code),
        member_id,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
