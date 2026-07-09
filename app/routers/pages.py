from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_member_id, member_cookie_key, templates
from app.models import Activity, ItineraryItem, Member, Trip, Vote, share_code
from app.services.distance import directions_url, maps_url
from app.services.geocode import geocode_address
from app.services.photos import delete_photo_file
from app.services.place_photos import fetch_place_photo
from app.services.scoring import RATING_LABELS, STATUS_CONFIG
from app.services.trip import enrich_trip, get_trip_by_code

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "error": None},
    )


@router.post("/create")
async def create_trip(
    request: Request,
    name: str = Form(...),
    date: str = Form(...),
    location: str = Form(...),
    creator_name: str = Form(...),
    db: Session = Depends(get_db),
):
    code = share_code()
    while db.query(Trip).filter(Trip.share_code == code).first():
        code = share_code()

    trip = Trip(name=name.strip(), date=date, location=location.strip(), share_code=code)
    db.add(trip)
    db.flush()

    member = Member(trip_id=trip.id, display_name=creator_name.strip(), is_creator=True)
    db.add(member)
    db.commit()

    response = RedirectResponse(url=f"/t/{code}", status_code=303)
    response.set_cookie(member_cookie_key(code), member.id, max_age=60 * 60 * 24 * 30)
    return response


@router.post("/join")
async def join_by_code(
    request: Request,
    join_code: str = Form(...),
    display_name: str = Form(...),
    db: Session = Depends(get_db),
):
    code = join_code.strip().lower()
    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        return templates.TemplateResponse(
            "home.html",
            {"request": request, "error": "Trip not found. Check your code."},
            status_code=404,
        )

    member = Member(trip_id=trip.id, display_name=display_name.strip())
    db.add(member)
    db.commit()

    response = RedirectResponse(url=f"/t/{code}", status_code=303)
    response.set_cookie(member_cookie_key(code), member.id, max_age=60 * 60 * 24 * 30)
    return response


@router.get("/t/{code}/join", response_class=HTMLResponse)
async def join_page(request: Request, code: str, db: Session = Depends(get_db)):
    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return templates.TemplateResponse(
        "join.html",
        {"request": request, "trip": trip, "error": None},
    )


@router.post("/t/{code}/join")
async def join_trip(
    code: str,
    display_name: str = Form(...),
    db: Session = Depends(get_db),
):
    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    member = Member(trip_id=trip.id, display_name=display_name.strip())
    db.add(member)
    db.commit()

    response = RedirectResponse(url=f"/t/{code}", status_code=303)
    response.set_cookie(member_cookie_key(code), member.id, max_age=60 * 60 * 24 * 30)
    return response


@router.get("/t/{code}", response_class=HTMLResponse)
async def trip_board(request: Request, code: str, db: Session = Depends(get_db)):
    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)

    trip = get_trip_by_code(db, code)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    enriched = enrich_trip(trip, member_id)
    member = next((m for m in trip.members if m.id == member_id), None)

    sections = [
        ("likely", "Likely in"),
        ("maybe", "Maybe"),
        ("vetoed", "Needs discussion (vetoed)"),
        ("unlikely", "Unlikely"),
        ("unrated", "Not yet rated"),
    ]

    my_unvoted_count = sum(
        1 for a in enriched.activities if a.my_vote is None
    ) if not enriched.trip.voting_locked else 0
    any_votes = any(a.summary.vote_count > 0 for a in enriched.activities)

    return templates.TemplateResponse(
        "trip.html",
        {
            "request": request,
            "trip": enriched.trip,
            "enriched": enriched,
            "member": member,
            "sections": sections,
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
    db: Session = Depends(get_db),
):
    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)

    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.voting_locked:
        raise HTTPException(status_code=403, detail="Voting is locked")

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
        photo_path=None,
        photo_url=photo_url,
        proposed_by_id=member_id,
    )
    db.add(activity)
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
    if trip.voting_locked:
        raise HTTPException(status_code=403, detail="Voting is locked")

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
    if not trip or trip.voting_locked:
        return RedirectResponse(url=f"/t/{code}", status_code=303)

    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be 1-5")

    activity = db.query(Activity).filter(Activity.id == activity_id, Activity.trip_id == trip.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

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
    if not trip or trip.voting_locked:
        return RedirectResponse(url=f"/t/{code}", status_code=303)

    activity = db.query(Activity).filter(Activity.id == activity_id, Activity.trip_id == trip.id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

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
    if trip.voting_locked:
        raise HTTPException(status_code=403, detail="Voting is locked")

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
    db: Session = Depends(get_db),
):
    member_id = get_member_id(request, code)
    if not member_id:
        return RedirectResponse(url=f"/t/{code}/join", status_code=303)

    trip = db.query(Trip).filter(Trip.share_code == code).first()
    if not trip:
        raise HTTPException(status_code=404)
    if trip.voting_locked:
        raise HTTPException(status_code=403, detail="Voting is locked")

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

    trip = get_trip_by_code(db, code)
    if not trip:
        raise HTTPException(status_code=404)

    enriched = enrich_trip(trip, member_id)
    if not enriched.is_creator:
        raise HTTPException(status_code=403, detail="Only creator can build itinerary")

    selected_ids: set[str] = set()
    builder_items = []

    if enriched.itinerary:
        for stop in enriched.itinerary:
            selected_ids.add(stop.activity.activity.id)
            builder_items.append({
                "activity": stop.activity,
                "start_time": stop.item.start_time,
                "duration_min": stop.item.duration_min,
                "override_note": stop.item.override_note or "",
            })
    else:
        for i, act in enumerate(enriched.grouped["likely"] + enriched.grouped["maybe"]):
            selected_ids.add(act.activity.id)
            builder_items.append({
                "activity": act,
                "start_time": act.activity.suggested_time or f"{9 + i}:00",
                "duration_min": act.activity.duration_min,
                "override_note": "",
            })

    pool = [a for a in enriched.activities if a.activity.id not in selected_ids]
    veto_count = sum(
        1 for item in builder_items
        if item["activity"].summary.has_veto and not item["override_note"]
    )

    is_editing = enriched.trip.published
    any_votes = any(a.summary.vote_count > 0 for a in enriched.activities)
    needs_votes = (
        not is_editing
        and bool(enriched.activities)
        and not any_votes
    )

    return templates.TemplateResponse(
        "build.html",
        {
            "request": request,
            "trip": enriched.trip,
            "builder_items": builder_items,
            "pool": pool,
            "veto_count": veto_count,
            "is_editing": is_editing,
            "needs_votes": needs_votes,
        },
    )


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

    db.query(ItineraryItem).filter(ItineraryItem.trip_id == trip.id).delete()

    for order, activity_id in enumerate(activity_ids):
        start_time = form.get(f"start_time_{activity_id}", "12:00")
        duration_min = int(form.get(f"duration_min_{activity_id}", 60))
        override_note = form.get(f"override_note_{activity_id}", "").strip() or None

        db.add(
            ItineraryItem(
                trip_id=trip.id,
                activity_id=activity_id,
                order=order,
                start_time=str(start_time),
                duration_min=duration_min,
                override_note=override_note,
            )
        )

    if publish:
        trip.published = True
        trip.voting_locked = True

    db.commit()

    if publish or trip.published:
        return RedirectResponse(url=f"/t/{code}/plan", status_code=303)
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
    db.commit()

    if trip.published:
        return RedirectResponse(url=f"/t/{code}/plan", status_code=303)
    return RedirectResponse(url=f"/t/{code}", status_code=303)


@router.get("/t/{code}/plan", response_class=HTMLResponse)
async def plan_page(request: Request, code: str, db: Session = Depends(get_db)):
    trip = get_trip_by_code(db, code)
    if not trip:
        raise HTTPException(status_code=404)

    member_id = get_member_id(request, code)
    enriched = enrich_trip(trip, member_id)
    member = next((m for m in trip.members if m.id == member_id), None) if member_id else None

    if not enriched.trip.published or not enriched.itinerary:
        return templates.TemplateResponse(
            "plan_unpublished.html",
            {"request": request, "trip": trip, "code": code},
        )

    return templates.TemplateResponse(
        "plan.html",
        {
            "request": request,
            "trip": enriched.trip,
            "itinerary": enriched.itinerary,
            "member": member,
            "is_creator": enriched.is_creator,
            "maps_url": maps_url,
            "directions_url": directions_url,
        },
    )
