from datetime import date as date_type
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import (
    clear_member_cookie,
    get_member_id,
    get_trip_member,
    member_cookie_key,
    require_trip_member_json,
    require_trip_member_redirect,
    set_member_cookie,
    templates,
)
from app.services.security import client_ip, rate_limit
from app.models import Activity, ConfirmationItem, Expense, ItineraryItem, Member, PackingItem, Trip, TripPhoto, UserTrip, Vote, share_code
from app.services.auth import get_user_from_request
from app.services.categories import normalize_category
from app.services.day_plan import delete_city, delete_country, delete_day, reorder_days
from app.services.dates import normalize_num_days
from app.services.destinations import (
    backfill_destination_country_codes,
    backfill_destination_names,
    destinations_by_country,
    normalize_destination_names,
    sync_trip_destinations,
    trip_destination_names,
)
from app.services.route_plan import sync_trip_from_route_plan
from app.services.distance import directions_url, format_time_12h, maps_url, normalize_time_24, parse_duration_min, parse_optional_duration_min
from app.services.geocode import ensure_activity_coordinates, geocode_confirmed_activities_background, geocode_for_trip
from app.services.expenses import (
    EXPENSE_CURRENCIES,
    compute_balances,
    default_expense_currency,
    format_cents,
    normalize_currency,
)
from app.services.members import reassign_and_remove_member
from app.services.notifications import notify_trip_members
from app.services.photos import UPLOAD_DIR, delete_photo_file
from app.services.scheduling import detect_day_conflicts
from app.services.place_photos import fetch_place_photo
from app.services.scoring import RATING_LABELS, STATUS_CONFIG
from app.services.suggestions import seed_trip_background
from app.services.trip import (
    build_day_board,
    enrich_trip,
    get_trip_by_code,
    group_days_by_country,
)
from app.services.trip_covers import trip_cover_response
from app.services.weather import fetch_trip_weather

router = APIRouter()


def _form_checkbox(value: str | list[str] | None) -> bool:
    if value is None:
        return False
    values = value if isinstance(value, list) else [value]
    return any((v or "").strip().lower() in ("1", "on", "true", "yes") for v in values)


def _parse_form_coords(latitude: str = "", longitude: str = "") -> tuple[float | None, float | None]:
    try:
        lat_text = (latitude or "").strip()
        lng_text = (longitude or "").strip()
        if not lat_text or not lng_text:
            return None, None
        lat = float(lat_text)
        lng = float(lng_text)
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return lat, lng
    except ValueError:
        pass
    return None, None


async def _resolve_activity_location(
    trip,
    location: str,
    *,
    form_lat: str = "",
    form_lng: str = "",
) -> tuple[float | None, float | None, str | None]:
    resolved_location = location.strip() or None
    lat, lng = _parse_form_coords(form_lat, form_lng)

    if lat is not None and lng is not None:
        return lat, lng, resolved_location

    if resolved_location:
        geo = await geocode_for_trip(resolved_location, trip)
        if geo:
            return geo.latitude, geo.longitude, geo.display_name

    return None, None, resolved_location


def _bg_notify_trip(trip_id: str, subject: str, body: str, app_url: str) -> None:
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        trip = db.query(Trip).filter(Trip.id == trip_id).first()
        if trip:
            notify_trip_members(db, trip, subject=subject, body=body, app_url=app_url)
    finally:
        db.close()


def _link_user_trip(db: Session, user, trip: Trip, *, is_creator: bool) -> None:
    if not user:
        return
    existing = (
        db.query(UserTrip)
        .filter(UserTrip.user_id == user.id, UserTrip.trip_id == trip.id)
        .first()
    )
    if existing:
        if is_creator and not existing.is_creator:
            existing.is_creator = True
        return
    db.add(UserTrip(user_id=user.id, trip_id=trip.id, is_creator=is_creator))


def _home_context(request: Request, db: Session, **extra) -> dict:
    ctx = {
        "request": request,
        "error": None,
        "initial_view": None,
        "auth_email": "",
        "auth_name": "",
        "user": get_user_from_request(request, db),
    }
    ctx.update(extra)
    return ctx


def trip_not_found_response(request: Request, code: str) -> HTMLResponse:
    return templates.TemplateResponse(
        "trip_not_found.html",
        {"request": request, "code": code},
        status_code=404,
    )


def _trip_summary(trip: Trip, db: Session, *, is_creator: bool = False) -> dict:
    activity_count = (
        db.query(Activity)
        .filter(Activity.trip_id == trip.id, Activity.is_suggested.is_(False))
        .count()
    )
    members = (
        db.query(Member)
        .filter(Member.trip_id == trip.id)
        .order_by(Member.is_creator.desc(), Member.id)
        .limit(6)
        .all()
    )
    return {
        "code": trip.share_code,
        "exists": True,
        "published": trip.published,
        "name": trip.name,
        "date": trip.date,
        "location": trip.location,
        "num_days": trip.num_days or 1,
        "is_creator": is_creator,
        "activity_count": activity_count,
        "members": [
            {"name": m.display_name, "initial": (m.display_name or "?")[0].upper()}
            for m in members
        ],
    }


@router.get("/t/{code}/exists")
async def trip_exists(code: str, request: Request, db: Session = Depends(get_db)):
    if not rate_limit(f"trip_exists:{client_ip(request)}", max_calls=60, window_sec=60):
        return JSONResponse({"error": "Too many requests"}, status_code=429)
    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        return {"exists": False, "published": False}
    summary = _trip_summary(trip, db)
    member_id = request.cookies.get(member_cookie_key(code))
    if member_id:
        _, member = get_trip_member(db, code, member_id)
        if member:
            summary["is_creator"] = member.is_creator
    if not summary.get("is_creator"):
        user = get_user_from_request(request, db)
        if user:
            link = (
                db.query(UserTrip)
                .filter(UserTrip.user_id == user.id, UserTrip.trip_id == trip.id, UserTrip.is_creator.is_(True))
                .first()
            )
            if link:
                summary["is_creator"] = True
    return summary


@router.get("/api/my-trips")
async def api_my_trips(request: Request, db: Session = Depends(get_db)):
    """Return trips for this browser (cookies) and logged-in account."""
    seen: set[str] = set()
    trips: list[dict] = []

    def add_trip(trip: Trip, *, is_creator: bool) -> None:
        if trip.share_code in seen:
            return
        seen.add(trip.share_code)
        trips.append(_trip_summary(trip, db, is_creator=is_creator))

    user = get_user_from_request(request, db)
    if user:
        for link in db.query(UserTrip).filter(UserTrip.user_id == user.id).all():
            trip = db.query(Trip).filter(Trip.id == link.trip_id).first()
            if trip:
                add_trip(trip, is_creator=link.is_creator)

    for key, member_id in request.cookies.items():
        if not key.startswith("gdp_member_"):
            continue
        code = key.removeprefix("gdp_member_")
        if code in seen:
            continue
        trip = db.query(Trip).filter(Trip.share_code == code).first()
        if not trip:
            continue
        member = (
            db.query(Member)
            .filter(Member.id == member_id, Member.trip_id == trip.id)
            .first()
        )
        if not member:
            continue
        add_trip(trip, is_creator=member.is_creator)

    return {"trips": trips}


@router.get("/api/me")
async def api_me(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_request(request, db)
    if not user:
        return {"logged_in": False}
    return {
        "logged_in": True,
        "email": user.email,
        "display_name": user.display_name,
    }


@router.get("/api/location-search")
async def api_location_search(
    request: Request,
    q: str = "",
    country: str = "",
    type: str = "",
    lat: float | None = None,
    lon: float | None = None,
):
    if not rate_limit(f"location_search:{client_ip(request)}", max_calls=30, window_sec=60):
        return JSONResponse({"error": "Too many requests"}, status_code=429)
    from app.services.location_search import search_locations

    results = await search_locations(
        q,
        country=country or None,
        search_type=type or None,
        lat=lat,
        lon=lon,
    )
    return {"results": results}


@router.get("/api/trip-cover")
async def api_trip_cover(location: str = "", code: str = "", name: str = ""):
    return await trip_cover_response(location, code, name)


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("home.html", _home_context(request, db))


@router.get("/create")
async def create_page():
    return RedirectResponse(url="/?view=create", status_code=303)


@router.get("/create/route", response_class=HTMLResponse)
async def create_route_page(request: Request, db: Session = Depends(get_db)):
    name = (request.query_params.get("name") or "").strip()
    return templates.TemplateResponse(
        "create_route.html",
        {**_home_context(request, db), "trip_name": name},
    )


@router.post("/create")
async def create_trip(
    request: Request,
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    date: str = Form(""),
    location: str = Form(""),
    locations: list[str] = Form([]),
    location_countries: list[str] = Form([]),
    route_plan: str = Form(""),
    creator_name: str = Form(""),
    num_days: int = Form(1),
    voting_enabled: list[str] = Form([]),
    db: Session = Depends(get_db),
):
    user = get_user_from_request(request, db)
    creator = creator_name.strip() or (user.display_name if user else "")
    if not creator:
        return templates.TemplateResponse(
            "home.html",
            _home_context(
                request,
                db,
                error="Enter your name.",
                initial_view="create",
            ),
            status_code=400,
        )

    destination_names = normalize_destination_names(locations)
    if not destination_names and location.strip():
        destination_names = normalize_destination_names([location])
    use_route_plan = bool((route_plan or "").strip())

    if not use_route_plan and not destination_names:
        return templates.TemplateResponse(
            "home.html",
            _home_context(
                request,
                db,
                error="Add at least one destination.",
                initial_view="create",
            ),
            status_code=400,
        )

    code = share_code()
    while db.query(Trip).filter(Trip.share_code == code).first():
        code = share_code()

    num_days = normalize_num_days(num_days)
    trip_date = date.strip() or date_type.today().isoformat()
    trip = Trip(
        name=name.strip(),
        date=trip_date,
        location=destination_names[0] if destination_names else "",
        share_code=code,
        num_days=num_days,
        voting_enabled=_form_checkbox(voting_enabled),
    )
    db.add(trip)
    db.flush()

    if use_route_plan:
        try:
            num_days = sync_trip_from_route_plan(trip, route_plan)
        except ValueError as exc:
            return templates.TemplateResponse(
                "home.html",
                _home_context(
                    request,
                    db,
                    error=str(exc),
                    initial_view="create",
                ),
                status_code=400,
            )
    else:
        sync_trip_destinations(
            trip,
            destination_names,
            num_days=num_days,
            country_names=location_countries,
        )

    member = Member(trip_id=trip.id, display_name=creator, is_creator=True)
    db.add(member)
    _link_user_trip(db, user, trip, is_creator=True)
    db.commit()

    background_tasks.add_task(seed_trip_background, trip.id, member.id)

    response = RedirectResponse(url=f"/t/{code}", status_code=303)
    set_member_cookie(response, request, code, member.id)
    return response


@router.post("/join")
async def join_by_code(
    request: Request,
    join_code: str = Form(...),
    display_name: str = Form(""),
    db: Session = Depends(get_db),
):
    code = join_code.strip().lower()
    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        return templates.TemplateResponse(
            "home.html",
            _home_context(
                request,
                db,
                error="Trip not found. Check your code.",
                initial_view="join",
            ),
            status_code=404,
        )

    user = get_user_from_request(request, db)
    guest_name = display_name.strip() or (user.display_name if user else "")
    if not guest_name:
        return templates.TemplateResponse(
            "home.html",
            _home_context(
                request,
                db,
                error="Enter your name.",
                initial_view="join",
            ),
            status_code=400,
        )

    member = Member(trip_id=trip.id, display_name=guest_name)
    db.add(member)
    _link_user_trip(db, user, trip, is_creator=False)
    db.commit()

    response = RedirectResponse(url=f"/t/{code}", status_code=303)
    set_member_cookie(response, request, code, member.id)
    return response


@router.get("/t/{code}/join", response_class=HTMLResponse)
async def join_page(request: Request, code: str, db: Session = Depends(get_db)):
    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        return trip_not_found_response(request, code)
    return templates.TemplateResponse(
        "join.html",
        {"request": request, "trip": trip, "error": None},
    )


@router.post("/t/{code}/join")
async def join_trip(
    request: Request,
    code: str,
    display_name: str = Form(""),
    db: Session = Depends(get_db),
):
    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        return trip_not_found_response(request, code)

    user = get_user_from_request(request, db)
    guest_name = display_name.strip() or (user.display_name if user else "")
    if not guest_name:
        return templates.TemplateResponse(
            "join.html",
            {"request": request, "trip": trip, "error": "Enter your name."},
            status_code=400,
        )

    member = Member(trip_id=trip.id, display_name=guest_name)
    db.add(member)
    _link_user_trip(db, user, trip, is_creator=False)
    db.commit()

    response = RedirectResponse(url=f"/t/{code}", status_code=303)
    set_member_cookie(response, request, code, member.id)
    return response


@router.get("/t/{code}", response_class=HTMLResponse)
async def trip_board(
    request: Request,
    code: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    if backfill_destination_country_codes(trip):
        db.commit()
        trip = get_trip_by_code(db, code)
        if not trip:
            return trip_not_found_response(request, code)

    if backfill_destination_names(trip):
        db.commit()
        trip = get_trip_by_code(db, code)
        if not trip:
            return trip_not_found_response(request, code)

    member_id = member.id
    background_tasks.add_task(seed_trip_background, trip.id, member_id)
    background_tasks.add_task(geocode_confirmed_activities_background, trip.id)
    trip = get_trip_by_code(db, code)
    if not trip:
        return trip_not_found_response(request, code)

    enriched = enrich_trip(trip, member_id)

    sections = [
        ("activities", "Activities"),
    ]

    my_unvoted_count = (
        sum(1 for a in enriched.suggested if a.my_vote is None)
        if trip.voting_enabled
        else 0
    )
    any_votes = any(
        a.summary.vote_count > 0
        for a in enriched.suggested + enriched.activities
    )
    day_board = build_day_board(enriched, sections)
    weather_names = trip_destination_names(enriched.trip)
    weather_by_day = await fetch_trip_weather(
        weather_names[0] if weather_names else enriched.trip.location,
        enriched.trip.date,
        enriched.trip.num_days or 1,
    )
    for day in day_board:
        day["weather"] = weather_by_day.get(day["day"])

    packing_items = (
        db.query(PackingItem)
        .filter(PackingItem.trip_id == trip.id)
        .order_by(PackingItem.sort_order, PackingItem.created_at)
        .all()
    )
    packed_count = sum(1 for item in packing_items if item.is_packed)

    confirmation_items = (
        db.query(ConfirmationItem)
        .options(joinedload(ConfirmationItem.added_by))
        .filter(ConfirmationItem.trip_id == trip.id)
        .order_by(ConfirmationItem.sort_order, ConfirmationItem.created_at)
        .all()
    )

    confirmed_activities = [a.activity for a in enriched.activities if not a.activity.is_suggested]

    all_conflicts = detect_day_conflicts(confirmed_activities)
    conflicts_by_day: dict[int, list] = {}
    for c in all_conflicts:
        conflicts_by_day.setdefault(c.day, []).append(c)

    map_pins_by_day: dict[int, list] = {}
    for act in confirmed_activities:
        if act.latitude is None or act.longitude is None:
            continue
        day = act.day_number or 1
        map_pins_by_day.setdefault(day, []).append({
            "id": act.id,
            "title": act.title,
            "lat": act.latitude,
            "lng": act.longitude,
            "time": act.suggested_time or "",
        })
    for day_pins in map_pins_by_day.values():
        day_pins.sort(key=lambda p: p.get("time") or "99:99")

    expenses = (
        db.query(Expense)
        .options(joinedload(Expense.paid_by))
        .filter(Expense.trip_id == trip.id)
        .order_by(Expense.created_at.desc())
        .all()
    )
    expense_balances = compute_balances(db, trip.id, trip.members)

    edit_mode = False
    show_builder = False
    show_plan = False
    show_voting = bool(trip.voting_enabled)
    show_waiting = False
    builder_ctx = None
    itinerary_days = None

    return templates.TemplateResponse(
        "trip.html",
        {
            "request": request,
            "trip": enriched.trip,
            "enriched": enriched,
            "member": member,
            "sections": sections,
            "day_board": day_board,
            "weather_by_day": weather_by_day,
            "show_builder": show_builder,
            "show_plan": show_plan,
            "show_voting": show_voting,
            "show_waiting": show_waiting,
            "edit_mode": edit_mode,
            "builder_ctx": builder_ctx,
            "directions_url": directions_url,
            "rating_labels": RATING_LABELS,
            "status_config": STATUS_CONFIG,
            "maps_url": maps_url,
            "my_unvoted_count": my_unvoted_count,
            "any_votes": any_votes,
            "packing_items": packing_items,
            "packed_count": packed_count,
            "confirmation_items": confirmation_items,
            "expenses": expenses,
            "expense_balances": expense_balances,
            "expense_currencies": EXPENSE_CURRENCIES,
            "default_expense_currency": default_expense_currency(trip),
            "format_cents": format_cents,
            "conflicts_by_day": conflicts_by_day,
            "map_pins_by_day": map_pins_by_day,
        },
    )


@router.post("/t/{code}/packing")
async def add_packing_item(
    request: Request,
    code: str,
    label: str = Form(...),
    db: Session = Depends(get_db),
):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, _member = auth

    text = label.strip()
    if not text:
        return RedirectResponse(url=f"/t/{code}", status_code=303)

    next_order = (
        db.query(PackingItem)
        .filter(PackingItem.trip_id == trip.id)
        .count()
    )
    db.add(PackingItem(trip_id=trip.id, label=text, sort_order=next_order))
    db.commit()
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.post("/t/{code}/packing/{item_id}/toggle")
async def toggle_packing_item(
    request: Request,
    code: str,
    item_id: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, _member = auth

    item = (
        db.query(PackingItem)
        .filter(PackingItem.id == item_id, PackingItem.trip_id == trip.id)
        .first()
    )
    if not item:
        return JSONResponse({"error": "Not found"}, status_code=404)

    item.is_packed = not item.is_packed
    db.commit()

    total = db.query(PackingItem).filter(PackingItem.trip_id == trip.id).count()
    packed = (
        db.query(PackingItem)
        .filter(PackingItem.trip_id == trip.id, PackingItem.is_packed.is_(True))
        .count()
    )
    return JSONResponse({"is_packed": item.is_packed, "packed": packed, "total": total})


@router.post("/t/{code}/packing/{item_id}/delete")
async def delete_packing_item(
    request: Request,
    code: str,
    item_id: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, _member = auth

    item = (
        db.query(PackingItem)
        .filter(PackingItem.id == item_id, PackingItem.trip_id == trip.id)
        .first()
    )
    if not item:
        return JSONResponse({"error": "Not found"}, status_code=404)

    db.delete(item)
    db.commit()

    total = db.query(PackingItem).filter(PackingItem.trip_id == trip.id).count()
    packed = (
        db.query(PackingItem)
        .filter(PackingItem.trip_id == trip.id, PackingItem.is_packed.is_(True))
        .count()
    )
    return JSONResponse({"ok": True, "packed": packed, "total": total})


@router.post("/t/{code}/confirmations")
async def add_confirmation_item(
    request: Request,
    code: str,
    label: str = Form(...),
    confirmation_code: str = Form(...),
    db: Session = Depends(get_db),
):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    text = label.strip()
    code_text = confirmation_code.strip()
    if not text or not code_text:
        return RedirectResponse(url=f"/t/{code}", status_code=303)

    next_order = (
        db.query(ConfirmationItem)
        .filter(ConfirmationItem.trip_id == trip.id)
        .count()
    )
    db.add(
        ConfirmationItem(
            trip_id=trip.id,
            label=text,
            code=code_text,
            added_by_member_id=member.id,
            sort_order=next_order,
        )
    )
    db.commit()
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.post("/t/{code}/confirmations/{item_id}/delete")
async def delete_confirmation_item(
    request: Request,
    code: str,
    item_id: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, _member = auth

    item = (
        db.query(ConfirmationItem)
        .filter(ConfirmationItem.id == item_id, ConfirmationItem.trip_id == trip.id)
        .first()
    )
    if not item:
        return JSONResponse({"error": "Not found"}, status_code=404)

    db.delete(item)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/t/{code}/members/{target_member_id}/remove")
async def remove_trip_member(
    request: Request,
    code: str,
    target_member_id: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, actor = auth

    if not actor.is_creator:
        return JSONResponse({"error": "Only the host can remove travelers"}, status_code=403)

    target = (
        db.query(Member)
        .filter(Member.id == target_member_id, Member.trip_id == trip.id)
        .first()
    )
    if not target:
        return JSONResponse({"error": "Not found"}, status_code=404)
    if target.is_creator:
        return JSONResponse({"error": "Cannot remove the host"}, status_code=400)

    reassign_and_remove_member(db, trip.id, target)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/t/{code}/leave")
async def leave_trip(request: Request, code: str, db: Session = Depends(get_db)):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, member = auth

    if member.is_creator:
        return JSONResponse({"error": "Host cannot leave — delete the trip or transfer host first"}, status_code=400)

    user = get_user_from_request(request, db)
    if user:
        db.query(UserTrip).filter(UserTrip.user_id == user.id, UserTrip.trip_id == trip.id).delete()

    reassign_and_remove_member(db, trip.id, member)
    db.commit()

    response = RedirectResponse(url="/", status_code=303)
    clear_member_cookie(response, request, code)
    return response


@router.post("/t/{code}/activities/reorder")
async def reorder_confirmed_activities(
    request: Request,
    code: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, member = auth

    if not member.is_creator:
        return JSONResponse({"error": "Only the host can reorder"}, status_code=403)

    data = await request.json()
    day = int(data.get("day", 1))
    order = data.get("order", [])
    if not isinstance(order, list):
        return JSONResponse({"error": "Invalid order"}, status_code=400)

    for idx, activity_id in enumerate(order):
        activity = (
            db.query(Activity)
            .filter(Activity.id == activity_id, Activity.trip_id == trip.id, Activity.is_suggested.is_(False))
            .first()
        )
        if activity and (activity.day_number or 1) == day:
            activity.sort_order = idx

    db.commit()
    return JSONResponse({"ok": True})


@router.post("/t/{code}/days/reorder")
async def reorder_trip_days(
    request: Request,
    code: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, member = auth

    if not member.is_creator:
        return JSONResponse({"error": "Only the host can reorder days"}, status_code=403)

    data = await request.json()
    order = data.get("order", [])
    if not isinstance(order, list):
        return JSONResponse({"error": "Invalid order"}, status_code=400)

    try:
        reorder_days(trip, [int(day) for day in order])
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    db.commit()
    return JSONResponse({"ok": True})


@router.post("/t/{code}/days/{day_number}/delete")
async def delete_trip_day(
    request: Request,
    code: str,
    day_number: int,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, member = auth

    if not member.is_creator:
        return JSONResponse({"error": "Only the host can delete days"}, status_code=403)

    try:
        delete_day(db, trip, day_number)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    db.commit()
    return JSONResponse({"ok": True})


@router.post("/t/{code}/countries/{country_code}/delete")
async def delete_trip_country(
    request: Request,
    code: str,
    country_code: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, member = auth

    if not member.is_creator:
        return JSONResponse({"error": "Only the host can remove countries"}, status_code=403)

    try:
        delete_country(db, trip, country_code)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    db.commit()
    return JSONResponse({"ok": True})


@router.post("/t/{code}/cities/delete")
async def delete_trip_city(
    request: Request,
    code: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, member = auth

    if not member.is_creator:
        return JSONResponse({"error": "Only the host can remove cities"}, status_code=403)

    data = await request.json()
    country_code = data.get("country_code", "")
    city = data.get("city", "")

    try:
        delete_city(db, trip, country_code, city)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    db.commit()
    return JSONResponse({"ok": True})


@router.post("/t/{code}/expenses")
async def add_expense(
    request: Request,
    code: str,
    label: str = Form(...),
    amount: str = Form(...),
    paid_by: str = Form(...),
    currency: str = Form("USD"),
    db: Session = Depends(get_db),
):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, _member = auth

    text = label.strip()
    try:
        amount_cents = int(round(float(amount.replace("$", "").replace(",", "").strip()) * 100))
    except ValueError:
        return RedirectResponse(url=f"/t/{code}?error=expense_invalid", status_code=303)
    if not text or amount_cents <= 0:
        return RedirectResponse(url=f"/t/{code}?error=expense_invalid", status_code=303)

    payer = db.query(Member).filter(Member.id == paid_by, Member.trip_id == trip.id).first()
    if not payer:
        return RedirectResponse(url=f"/t/{code}?error=expense_invalid", status_code=303)

    db.add(
        Expense(
            trip_id=trip.id,
            label=text,
            amount_cents=amount_cents,
            currency=normalize_currency(currency),
            paid_by_member_id=payer.id,
        )
    )
    db.commit()
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.post("/t/{code}/expenses/{expense_id}/delete")
async def delete_expense(
    request: Request,
    code: str,
    expense_id: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, _member = auth

    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.trip_id == trip.id).first()
    if not expense:
        return JSONResponse({"error": "Not found"}, status_code=404)

    db.delete(expense)
    db.commit()
    balances = compute_balances(db, trip.id, trip.members)
    return JSONResponse({"ok": True, "balances": balances["balances"]})


@router.post("/t/{code}/photos")
async def upload_trip_photo(
    request: Request,
    code: str,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, member = auth

    data = await photo.read()
    try:
        from app.services.photos import save_trip_photo
        file_path = save_trip_photo(trip.id, data, photo.content_type or "")
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    db.add(TripPhoto(
        trip_id=trip.id,
        uploaded_by_member_id=member.id,
        file_path=file_path,
    ))
    db.commit()
    return JSONResponse({"ok": True, "url": file_path})


@router.post("/t/{code}/photos/{photo_id}/delete")
async def delete_trip_photo(
    request: Request,
    code: str,
    photo_id: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, member = auth

    photo = (
        db.query(TripPhoto)
        .filter(TripPhoto.id == photo_id, TripPhoto.trip_id == trip.id)
        .first()
    )
    if not photo:
        return JSONResponse({"error": "Not found"}, status_code=404)

    if photo.uploaded_by_member_id != member.id and not member.is_creator:
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    delete_photo_file(photo.file_path)
    db.delete(photo)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/t/{code}/notes")
async def save_trip_notes(
    request: Request,
    code: str,
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, _member = auth

    trip.notes = notes.strip() or None
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/t/{code}/activities")
async def add_activity(
    request: Request,
    code: str,
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    location: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
    url: str = Form(""),
    notes: str = Form(""),
    suggested_time: str = Form(""),
    duration_min: str = Form(""),
    day_number: int = Form(1),
    category: str = Form("activity"),
    db: Session = Depends(get_db),
):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    lat, lng, resolved_location = await _resolve_activity_location(
        trip,
        location,
        form_lat=latitude,
        form_lng=longitude,
    )

    photo_url = await fetch_place_photo(
        title=title.strip(),
        location=resolved_location,
        latitude=lat,
        longitude=lng,
        city_context=trip.location,
    )

    day_number = max(1, min(int(day_number or 1), trip.num_days or 1))

    activity = Activity(
        trip_id=trip.id,
        title=title.strip(),
        url=url.strip() or None,
        notes=notes.strip() or None,
        location=resolved_location,
        latitude=lat,
        longitude=lng,
        suggested_time=suggested_time or None,
        duration_min=parse_optional_duration_min(duration_min),
        day_number=day_number,
        category=normalize_category(category),
        is_suggested=True,
        photo_path=None,
        photo_url=photo_url,
        proposed_by_id=member.id,
    )
    db.add(activity)
    db.commit()
    actor = member.display_name or "Someone"
    app_url = f"{request.url.scheme}://{request.url.netloc}"
    background_tasks.add_task(
        _bg_notify_trip,
        trip.id,
        "New suggestion",
        f"{actor} suggested \"{activity.title}\" for Day {activity.day_number}.",
        app_url,
    )
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.post("/t/{code}/activities/{activity_id}/accept")
async def accept_suggested_activity(
    request: Request,
    code: str,
    background_tasks: BackgroundTasks,
    activity_id: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    if not member.is_creator:
        raise HTTPException(status_code=403, detail="Only the trip creator can approve suggestions")

    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.trip_id == trip.id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    if not activity.is_suggested:
        return RedirectResponse(url=f"/t/{code}", status_code=303)

    day = activity.day_number or 1
    next_order = (
        db.query(Activity)
        .filter(
            Activity.trip_id == trip.id,
            Activity.is_suggested.is_(False),
            Activity.day_number == day,
        )
        .count()
    )
    activity.is_suggested = False
    activity.sort_order = next_order
    await ensure_activity_coordinates(activity, trip)
    db.commit()
    app_url = f"{request.url.scheme}://{request.url.netloc}"
    background_tasks.add_task(
        _bg_notify_trip,
        trip.id,
        "Suggestion approved",
        f"The host approved \"{activity.title}\" for Day {day}.",
        app_url,
    )
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.post("/t/{code}/activities/{activity_id}/decline")
async def decline_suggested_activity(
    request: Request,
    code: str,
    activity_id: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    if not member.is_creator:
        raise HTTPException(status_code=403, detail="Only the trip creator can decline suggestions")

    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.trip_id == trip.id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    if not activity.is_suggested:
        return RedirectResponse(url=f"/t/{code}", status_code=303)

    delete_photo_file(activity.photo_path)
    db.delete(activity)
    db.commit()
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.post("/t/{code}/activities/{activity_id}/delete")
async def delete_activity(
    request: Request,
    code: str,
    activity_id: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.trip_id == trip.id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    if activity.proposed_by_id != member.id and not member.is_creator:
        raise HTTPException(status_code=403, detail="Only the proposer or trip creator can delete this activity")

    delete_photo_file(activity.photo_path)
    db.delete(activity)
    db.commit()
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.post("/t/{code}/vote/{activity_id}")
async def vote(
    request: Request,
    code: str,
    activity_id: str,
    rating: int = Form(...),
    veto_reason: str = Form(""),
    db: Session = Depends(get_db),
):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    if not trip.voting_enabled:
        return RedirectResponse(url=f"/t/{code}", status_code=303)

    if trip.voting_locked:
        return RedirectResponse(url=f"/t/{code}?error=voting_locked", status_code=303)

    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")

    activity = db.query(Activity).filter(Activity.id == activity_id, Activity.trip_id == trip.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    if not activity.is_suggested:
        return RedirectResponse(url=f"/t/{code}", status_code=303)

    existing = (
        db.query(Vote)
        .filter(Vote.activity_id == activity_id, Vote.member_id == member.id)
        .first()
    )

    if existing:
        existing.rating = rating
        existing.veto_reason = veto_reason.strip() if rating == 1 else None
    else:
        db.add(
            Vote(
                activity_id=activity_id,
                member_id=member.id,
                rating=rating,
                veto_reason=veto_reason.strip() if rating == 1 else None,
            )
        )
    db.commit()
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.post("/t/{code}/vote/{activity_id}/clear")
async def clear_vote(
    request: Request,
    code: str,
    activity_id: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    if not trip.voting_enabled:
        return RedirectResponse(url=f"/t/{code}", status_code=303)

    if trip.voting_locked:
        return RedirectResponse(url=f"/t/{code}?error=voting_locked", status_code=303)

    activity = db.query(Activity).filter(Activity.id == activity_id, Activity.trip_id == trip.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    if not activity.is_suggested:
        return RedirectResponse(url=f"/t/{code}", status_code=303)

    existing = (
        db.query(Vote)
        .filter(Vote.activity_id == activity_id, Vote.member_id == member.id)
        .first()
    )
    if existing:
        db.delete(existing)
        db.commit()

    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.get("/t/{code}/activities/{activity_id}/edit", response_class=HTMLResponse)
async def edit_activity_page(
    request: Request,
    code: str,
    activity_id: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.trip_id == trip.id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    if activity.proposed_by_id != member.id and not member.is_creator:
        raise HTTPException(status_code=403, detail="Only the proposer or trip creator can edit this activity")

    return templates.TemplateResponse(
        "edit_activity.html",
        {"request": request, "trip": trip, "activity": activity},
    )


@router.post("/t/{code}/activities/{activity_id}/edit")
async def edit_activity(
    request: Request,
    code: str,
    activity_id: str,
    title: str = Form(...),
    location: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
    url: str = Form(""),
    notes: str = Form(""),
    suggested_time: str = Form(""),
    duration_min: str = Form(""),
    day_number: int = Form(1),
    category: str = Form("activity"),
    db: Session = Depends(get_db),
):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.trip_id == trip.id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    if activity.proposed_by_id != member.id and not member.is_creator:
        raise HTTPException(status_code=403, detail="Only the proposer or trip creator can edit this activity")

    lat, lng = activity.latitude, activity.longitude
    resolved_location = location.strip() or None
    location_changed = resolved_location != (activity.location or None)

    form_lat, form_lng = _parse_form_coords(latitude, longitude)
    if form_lat is not None and form_lng is not None:
        lat, lng = form_lat, form_lng
    elif resolved_location:
        geo = await geocode_for_trip(resolved_location, trip)
        if geo:
            lat, lng = geo.latitude, geo.longitude
            resolved_location = geo.display_name
    elif location.strip() == "" and activity.location:
        location_changed = True
        lat, lng = None, None

    activity.title = title.strip()
    activity.url = url.strip() or None
    activity.notes = notes.strip() or None
    activity.location = resolved_location
    activity.latitude = lat
    activity.longitude = lng
    activity.suggested_time = suggested_time or None
    activity.duration_min = parse_optional_duration_min(duration_min)
    activity.day_number = max(1, min(int(day_number or 1), trip.num_days or 1))
    activity.category = normalize_category(category)

    if location_changed or not activity.photo_url:
        photo_url = await fetch_place_photo(
            title=activity.title,
            location=resolved_location,
            latitude=lat,
            longitude=lng,
            city_context=trip.location,
        )
        if photo_url:
            activity.photo_url = photo_url

    db.commit()
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.post("/t/{code}/delete")
async def delete_trip(
    request: Request,
    code: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_json(request, code, db)
    if isinstance(auth, JSONResponse):
        return auth
    trip, member = auth

    if not member.is_creator:
        raise HTTPException(status_code=403, detail="Only the creator can delete this trip")

    db.delete(trip)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/t/{code}/lock-voting")
async def lock_voting(request: Request, code: str, db: Session = Depends(get_db)):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    if not member.is_creator:
        raise HTTPException(status_code=403)

    trip.voting_locked = True
    db.commit()
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.get("/t/{code}/build", response_class=HTMLResponse)
async def build_page(request: Request, code: str, db: Session = Depends(get_db)):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    if not member.is_creator:
        raise HTTPException(status_code=403, detail="Only creator can build itinerary")
    url = f"/t/{code}"
    if trip.published:
        url += "?edit=1"
    return RedirectResponse(url=url, status_code=303)


@router.post("/t/{code}/build")
async def save_itinerary(
    request: Request,
    code: str,
    db: Session = Depends(get_db),
):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    form = await request.form()

    if not member.is_creator:
        raise HTTPException(status_code=403)

    publish = form.get("action") == "publish"
    activity_ids = form.getlist("activity_id")

    if activity_ids:
        activities = (
            db.query(Activity)
            .filter(Activity.trip_id == trip.id, Activity.id.in_(activity_ids))
            .all()
        )
        day_by_id = {a.id: a.day_number or 1 for a in activities}
        order_index = {aid: i for i, aid in enumerate(activity_ids)}
        activity_ids = sorted(
            activity_ids,
            key=lambda aid: (day_by_id.get(aid, 1), order_index.get(aid, 0)),
        )

    db.query(ItineraryItem).filter(ItineraryItem.trip_id == trip.id).delete()

    for order, activity_id in enumerate(activity_ids):
        start_time = normalize_time_24(form.get(f"start_time_{activity_id}"))
        duration_min = parse_duration_min(form.get(f"duration_min_{activity_id}"))
        override_note = form.get(f"override_note_{activity_id}", "").strip() or None

        db.add(
            ItineraryItem(
                trip_id=trip.id,
                activity_id=activity_id,
                order=order,
                start_time=start_time,
                duration_min=duration_min,
                override_note=override_note,
            )
        )

    if publish:
        trip.published = True
        trip.voting_locked = True

    db.commit()

    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.get("/t/{code}/edit", response_class=HTMLResponse)
async def edit_trip_page(request: Request, code: str, db: Session = Depends(get_db)):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    if not member.is_creator:
        raise HTTPException(status_code=403, detail="Only the creator can edit this trip")

    trip = (
        db.query(Trip)
        .options(joinedload(Trip.destinations))
        .filter(Trip.share_code == code)
        .first()
    )

    return templates.TemplateResponse(
        "edit.html",
        {"request": request, "trip": trip},
    )


@router.get("/t/{code}/edit/route", response_class=HTMLResponse)
async def edit_route_page(request: Request, code: str, db: Session = Depends(get_db)):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    if not member.is_creator:
        raise HTTPException(status_code=403, detail="Only the creator can edit this trip")

    trip = (
        db.query(Trip)
        .options(joinedload(Trip.destinations))
        .filter(Trip.share_code == code)
        .first()
    )

    return templates.TemplateResponse(
        "edit_route.html",
        {"request": request, "trip": trip},
    )


@router.post("/t/{code}/edit")
async def edit_trip(
    request: Request,
    code: str,
    name: str = Form(...),
    date: str = Form(...),
    location: str = Form(""),
    locations: list[str] = Form([]),
    location_countries: list[str] = Form([]),
    route_plan: str = Form(""),
    num_days: int = Form(1),
    voting_enabled: list[str] = Form([]),
    db: Session = Depends(get_db),
):
    auth = require_trip_member_redirect(request, code, db)
    if isinstance(auth, RedirectResponse):
        return auth
    trip, member = auth

    if not member.is_creator:
        raise HTTPException(status_code=403)

    trip = (
        db.query(Trip)
        .options(joinedload(Trip.destinations))
        .filter(Trip.share_code == code)
        .first()
    )

    destination_names = normalize_destination_names(locations)
    if not destination_names and location.strip():
        destination_names = normalize_destination_names([location])
    use_route_plan = bool((route_plan or "").strip())

    if not use_route_plan and not destination_names:
        return templates.TemplateResponse(
            "edit.html",
            {
                "request": request,
                "trip": trip,
                "error": "Add at least one destination.",
            },
            status_code=400,
        )

    trip.name = name.strip()
    trip.date = date
    trip.voting_enabled = _form_checkbox(voting_enabled)
    if use_route_plan:
        try:
            sync_trip_from_route_plan(trip, route_plan)
        except ValueError as exc:
            return templates.TemplateResponse(
                "edit.html",
                {
                    "request": request,
                    "trip": trip,
                    "error": str(exc),
                },
                status_code=400,
            )
    else:
        trip.num_days = normalize_num_days(num_days)
        sync_trip_destinations(
            trip,
            destination_names,
            num_days=trip.num_days,
            country_names=location_countries,
        )
    db.commit()

    if trip.published:
        return RedirectResponse(url=f"/t/{code}", status_code=303)
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.get("/t/{code}/plan", response_class=HTMLResponse)
async def plan_page(request: Request, code: str, db: Session = Depends(get_db)):
    trip = get_trip_by_code(db, code)
    if not trip:
        raise HTTPException(status_code=404)

    member_id = get_member_id(request, code)
    _, member = get_trip_member(db, code, member_id) if member_id else (trip, None)

    if not trip.published and not member:
        return templates.TemplateResponse(
            "plan_unpublished.html",
            {"request": request, "code": code},
        )

    enriched = enrich_trip(trip, member_id=None)
    sections = [("activities", "Activities")]
    day_board = build_day_board(enriched, sections)
    country_groups = group_days_by_country(day_board)
    route_by_country = destinations_by_country(trip)
    is_creator = member.is_creator if member else False

    return templates.TemplateResponse(
        "public_plan.html",
        {
            "request": request,
            "trip": trip,
            "day_board": day_board,
            "country_groups": country_groups,
            "route_by_country": route_by_country,
            "member": member,
            "is_creator": is_creator,
            "format_time_12h": format_time_12h,
        },
    )
