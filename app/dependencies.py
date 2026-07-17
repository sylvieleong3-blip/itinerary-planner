from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.models import Member, Trip
from app.services.auth import get_user_from_request
from app.services.members import find_or_create_member_for_user
from app.services.trip import get_trip_by_code

from app.services.categories import ACTIVITY_CATEGORIES, activity_category
from app.services.dates import format_day_date, trip_date_range
from app.services.distance import format_time_12h, maps_link_for_activity
from app.services.destinations import (
    country_label,
    destination_for_day,
    destinations_by_country,
    trip_country_codes_csv,
    trip_destination_names,
)
from app.services.trip import group_days_by_country_and_city
from app.services.route_plan import trip_to_route_plan
from app.services.geocode import infer_country_code
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
templates.env.globals["infer_country_code"] = infer_country_code
templates.env.globals["trip_country_codes_csv"] = trip_country_codes_csv
templates.env.globals["trip_destination_names"] = trip_destination_names
templates.env.globals["destination_for_day"] = destination_for_day
templates.env.globals["destinations_by_country"] = destinations_by_country
templates.env.globals["country_label"] = country_label
templates.env.globals["trip_route_plan"] = trip_to_route_plan
templates.env.globals["group_days_by_country_and_city"] = group_days_by_country_and_city


def member_cookie_key(share_code: str) -> str:
    return f"gdp_member_{share_code}"


def get_member_id(request: Request, share_code: str) -> str | None:
    return request.cookies.get(member_cookie_key(share_code))


def clear_member_cookie(response: Response, request: Request, share_code: str) -> None:
    response.delete_cookie(
        member_cookie_key(share_code),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )


def set_member_cookie(response: Response, request: Request, share_code: str, member_id: str) -> None:
    response.set_cookie(
        member_cookie_key(share_code),
        member_id,
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )


def get_trip_member(db: Session, share_code: str, member_id: str | None) -> tuple[Trip | None, Member | None]:
    if not member_id:
        return None, None
    trip = get_trip_by_code(db, share_code)
    if not trip:
        return None, None
    member = (
        db.query(Member)
        .filter(Member.id == member_id, Member.trip_id == trip.id)
        .first()
    )
    return trip, member


def _restore_member_for_logged_in_user(
    request: Request,
    share_code: str,
    db: Session,
) -> tuple[Trip, Member] | None:
    user = get_user_from_request(request, db)
    if not user:
        return None
    trip = get_trip_by_code(db, share_code)
    if not trip:
        return None
    member = find_or_create_member_for_user(db, trip, user)
    if not member:
        return None
    request.state.pending_member_cookie = (share_code, member.id)
    return trip, member


def apply_pending_member_cookie(request: Request, response: Response) -> None:
    pending = getattr(request.state, "pending_member_cookie", None)
    if not pending:
        return
    share_code, member_id = pending
    if not get_member_id(request, share_code):
        set_member_cookie(response, request, share_code, member_id)


def require_trip_member_redirect(
    request: Request,
    share_code: str,
    db: Session,
) -> tuple[Trip, Member] | RedirectResponse:
    member_id = get_member_id(request, share_code)
    if member_id:
        trip, member = get_trip_member(db, share_code, member_id)
        if trip and member:
            return trip, member
        response = RedirectResponse(url=f"/t/{share_code}/join", status_code=303)
        clear_member_cookie(response, request, share_code)
        return response

    restored = _restore_member_for_logged_in_user(request, share_code, db)
    if restored:
        return restored

    return RedirectResponse(url=f"/t/{share_code}/join", status_code=303)


def require_trip_member_json(
    request: Request,
    share_code: str,
    db: Session,
) -> tuple[Trip, Member] | JSONResponse:
    member_id = get_member_id(request, share_code)
    if member_id:
        trip, member = get_trip_member(db, share_code, member_id)
        if trip and member:
            return trip, member

    restored = _restore_member_for_logged_in_user(request, share_code, db)
    if restored:
        return restored

    return JSONResponse({"error": "Unauthorized"}, status_code=403)
