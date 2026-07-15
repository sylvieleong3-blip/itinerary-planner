from datetime import date as date_type
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_member_id, member_cookie_key, set_member_cookie, templates
from app.models import Activity, ItineraryItem, Member, Trip, UserTrip, Vote, share_code
from app.services.auth import get_user_from_request
from app.services.categories import normalize_category
from app.services.dates import normalize_num_days
from app.services.distance import directions_url, maps_url, normalize_time_24, parse_duration_min
from app.services.geocode import geocode_address
from app.services.photos import delete_photo_file
from app.services.place_photos import fetch_place_photo
from app.services.scoring import RATING_LABELS, STATUS_CONFIG
from app.services.suggestions import ensure_trip_has_suggestions, seed_trip_background
from app.services.trip import (
    build_day_board,
    enrich_trip,
    get_trip_by_code,
)
from app.services.trip_covers import trip_cover_response
from app.services.weather import fetch_trip_weather

router = APIRouter()


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
    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        return {"exists": False, "published": False}
    summary = _trip_summary(trip, db)
    member_id = request.cookies.get(member_cookie_key(code))
    if member_id:
        member = (
            db.query(Member)
            .filter(Member.id == member_id, Member.trip_id == trip.id)
            .first()
        )
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


@router.get("/api/trip-cover")
async def api_trip_cover(location: str = "", code: str = "", name: str = ""):
    return await trip_cover_response(location, code, name)


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("home.html", _home_context(request, db))


@router.get("/create")
async def create_page():
    return RedirectResponse(url="/?view=create", status_code=303)


@router.post("/create")
async def create_trip(
    request: Request,
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    date: str = Form(""),
    location: str = Form(...),
    creator_name: str = Form(""),
    num_days: int = Form(1),
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

    code = share_code()
    while db.query(Trip).filter(Trip.share_code == code).first():
        code = share_code()

    num_days = normalize_num_days(num_days)
    trip_date = date.strip() or date_type.today().isoformat()
    trip = Trip(
        name=name.strip(),
        date=trip_date,
        location=location.strip(),
        share_code=code,
        num_days=num_days,
    )
    db.add(trip)
    db.flush()

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
async def trip_board(request: Request, code: str, db: Session = Depends(get_db)):
    trip = get_trip_by_code(db, code)
    if not trip:
        return trip_not_found_response(request, code)

    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)

    member = next((m for m in trip.members if m.id == member_id), None)
    if member:
        await ensure_trip_has_suggestions(trip, member_id, db)
        trip = get_trip_by_code(db, code)
        if not trip:
            return trip_not_found_response(request, code)

    enriched = enrich_trip(trip, member_id)
    member = next((m for m in trip.members if m.id == member_id), None)

    sections = [
        ("activities", "Activities"),
    ]

    my_unvoted_count = sum(
        1 for a in enriched.suggested if a.my_vote is None
    )
    any_votes = any(
        a.summary.vote_count > 0
        for a in enriched.suggested + enriched.activities
    )
    day_board = build_day_board(enriched, sections)
    weather_by_day = await fetch_trip_weather(
        enriched.trip.location,
        enriched.trip.date,
        enriched.trip.num_days or 1,
    )
    for day in day_board:
        day["weather"] = weather_by_day.get(day["day"])

    edit_mode = False
    show_builder = False
    show_plan = False
    show_voting = True
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
        },
    )


@router.post("/t/{code}/activities")
async def add_activity(
    request: Request,
    code: str,
    title: str = Form(...),
    location: str = Form(""),
    url: str = Form(""),
    notes: str = Form(""),
    suggested_time: str = Form(""),
    duration_min: int = Form(60),
    day_number: int = Form(1),
    category: str = Form("activity"),
    db: Session = Depends(get_db),
):
    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)

    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    lat, lng, resolved_location = None, None, location.strip() or None
    if resolved_location:
        geo = await geocode_address(f"{resolved_location}, {trip.location}")
        if geo:
            lat, lng = geo.latitude, geo.longitude
            resolved_location = geo.display_name

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
        duration_min=duration_min or 60,
        day_number=day_number,
        category=normalize_category(category),
        is_suggested=True,
        photo_path=None,
        photo_url=photo_url,
        proposed_by_id=member_id,
    )
    db.add(activity)
    db.commit()
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.post("/t/{code}/activities/{activity_id}/accept")
async def accept_suggested_activity(
    request: Request,
    code: str,
    activity_id: str,
    db: Session = Depends(get_db),
):
    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)

    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    member = db.query(Member).filter(Member.id == member_id, Member.trip_id == trip.id).first()
    if not member or not member.is_creator:
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

    activity.is_suggested = False
    db.commit()
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.post("/t/{code}/activities/{activity_id}/decline")
async def decline_suggested_activity(
    request: Request,
    code: str,
    activity_id: str,
    db: Session = Depends(get_db),
):
    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)

    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    member = db.query(Member).filter(Member.id == member_id, Member.trip_id == trip.id).first()
    if not member or not member.is_creator:
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
    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)

    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.trip_id == trip.id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    member = db.query(Member).filter(Member.id == member_id, Member.trip_id == trip.id).first()
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this trip")

    if activity.proposed_by_id != member_id and not member.is_creator:
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
    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)

    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        return RedirectResponse(url=f"/t/{code}", status_code=303)

    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")

    activity = db.query(Activity).filter(Activity.id == activity_id, Activity.trip_id == trip.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    if not activity.is_suggested:
        return RedirectResponse(url=f"/t/{code}", status_code=303)

    existing = (
        db.query(Vote)
        .filter(Vote.activity_id == activity_id, Vote.member_id == member_id)
        .first()
    )

    if existing:
        existing.rating = rating
        existing.veto_reason = veto_reason.strip() if rating == 1 else None
    else:
        db.add(
            Vote(
                activity_id=activity_id,
                member_id=member_id,
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
    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)

    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        return RedirectResponse(url=f"/t/{code}", status_code=303)

    activity = db.query(Activity).filter(Activity.id == activity_id, Activity.trip_id == trip.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    if not activity.is_suggested:
        return RedirectResponse(url=f"/t/{code}", status_code=303)

    existing = (
        db.query(Vote)
        .filter(Vote.activity_id == activity_id, Vote.member_id == member_id)
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
    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)

    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404)

    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.trip_id == trip.id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    member = db.query(Member).filter(Member.id == member_id, Member.trip_id == trip.id).first()
    if not member:
        raise HTTPException(status_code=403)
    if activity.proposed_by_id != member_id and not member.is_creator:
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
    url: str = Form(""),
    notes: str = Form(""),
    suggested_time: str = Form(""),
    duration_min: int = Form(60),
    day_number: int = Form(1),
    category: str = Form("activity"),
    db: Session = Depends(get_db),
):
    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)

    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404)

    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.trip_id == trip.id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    member = db.query(Member).filter(Member.id == member_id, Member.trip_id == trip.id).first()
    if not member:
        raise HTTPException(status_code=403)
    if activity.proposed_by_id != member_id and not member.is_creator:
        raise HTTPException(status_code=403, detail="Only the proposer or trip creator can edit this activity")

    lat, lng, resolved_location = None, None, location.strip() or None
    location_changed = resolved_location != (activity.location or None)

    if resolved_location:
        geo = await geocode_address(f"{resolved_location}, {trip.location}")
        if geo:
            lat, lng = geo.latitude, geo.longitude
            resolved_location = geo.display_name
    elif location.strip() == "" and activity.location:
        location_changed = True

    activity.title = title.strip()
    activity.url = url.strip() or None
    activity.notes = notes.strip() or None
    activity.location = resolved_location
    activity.latitude = lat
    activity.longitude = lng
    activity.suggested_time = suggested_time or None
    activity.duration_min = duration_min or 60
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
    member_id = get_member_id(request, code)
    if not member_id:
        raise HTTPException(status_code=401, detail="Not joined to this trip")

    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    member = db.query(Member).filter(Member.id == member_id, Member.trip_id == trip.id).first()
    if not member or not member.is_creator:
        raise HTTPException(status_code=403, detail="Only the creator can delete this trip")

    db.delete(trip)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/t/{code}/lock-voting")
async def lock_voting(request: Request, code: str, db: Session = Depends(get_db)):
    member_id = get_member_id(request, code)
    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404)

    member = db.query(Member).filter(Member.id == member_id, Member.trip_id == trip.id).first()
    if not member or not member.is_creator:
        raise HTTPException(status_code=403)

    trip.voting_locked = True
    db.commit()
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.get("/t/{code}/build", response_class=HTMLResponse)
async def build_page(request: Request, code: str, db: Session = Depends(get_db)):
    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)
    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404)
    member = db.query(Member).filter(Member.id == member_id, Member.trip_id == trip.id).first()
    if not member or not member.is_creator:
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
    member_id = get_member_id(request, code)
    form = await request.form()
    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404)

    member = db.query(Member).filter(Member.id == member_id, Member.trip_id == trip.id).first()
    if not member or not member.is_creator:
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
    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)

    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404)

    member = db.query(Member).filter(Member.id == member_id, Member.trip_id == trip.id).first()
    if not member or not member.is_creator:
        raise HTTPException(status_code=403, detail="Only the creator can edit this trip")

    return templates.TemplateResponse(
        "edit.html",
        {"request": request, "trip": trip},
    )


@router.post("/t/{code}/edit")
async def edit_trip(
    request: Request,
    code: str,
    name: str = Form(...),
    date: str = Form(...),
    location: str = Form(...),
    num_days: int = Form(1),
    db: Session = Depends(get_db),
):
    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)

    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404)

    member = db.query(Member).filter(Member.id == member_id, Member.trip_id == trip.id).first()
    if not member or not member.is_creator:
        raise HTTPException(status_code=403)

    trip.name = name.strip()
    trip.date = date
    trip.location = location.strip()
    trip.num_days = normalize_num_days(num_days)
    db.commit()

    if trip.published:
        return RedirectResponse(url=f"/t/{code}", status_code=303)
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.get("/t/{code}/plan", response_class=HTMLResponse)
async def plan_page(request: Request, code: str, db: Session = Depends(get_db)):
    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404)
    return RedirectResponse(url=f"/t/{code}", status_code=303)
