"""Suggest activities for a trip location using curated picks, Wikipedia, and OpenStreetMap."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import httpx

from app.services.categories import activity_category, normalize_category
from app.services.dates import normalize_num_days
from app.services.geocode import geocode_address

HEADERS = {
    "User-Agent": "ItineraryPlanner/1.0 (friend itinerary app)",
    "Accept": "application/json",
}

WIKI_API = "https://en.wikipedia.org/w/api.php"
OVERPASS_API = "https://overpass-api.de/api/interpreter"

# Cap auto-suggested activities so very long trips stay responsive.
MAX_SUGGESTIONS = 60

SKIP_TITLES = {
    "city", "town", "village", "country", "district", "borough",
    "united kingdom", "england", "london", "main page",
}

PLACE_HINTS = (
    "museum", "gallery", "park", "garden", "palace", "castle", "cathedral",
    "church", "bridge", "tower", "market", "square", "theatre", "theater",
    "zoo", "aquarium", "stadium", "abbey", "memorial", "monument", "pier",
    "beach", "harbour", "harbor", "station", "quarter", "walk", "trail",
    "experience", "centre", "center", "hall", "house", "ruins", "fort",
)

# Popular picks by destination — shown when API results are thin or missing.
CURATED_IDEAS: dict[str, list[dict]] = {
    "london": [
        {"title": "British Museum", "category": "culture", "notes": "World-class art and history — free entry", "location": "British Museum", "duration_min": 120},
        {"title": "Borough Market", "category": "food", "notes": "Street food, produce, and local specialties", "location": "Borough Market", "duration_min": 90},
        {"title": "Tower of London", "category": "culture", "notes": "Historic castle and Crown Jewels", "location": "Tower of London", "duration_min": 120},
        {"title": "Hyde Park", "category": "activity", "notes": "Picnic, pedal boats, or a relaxed stroll", "location": "Hyde Park", "duration_min": 90},
        {"title": "Westminster Abbey", "category": "culture", "notes": "Gothic abbey and royal coronations", "location": "Westminster Abbey", "duration_min": 90},
        {"title": "Thames riverside walk", "category": "activity", "notes": "Walk the South Bank past bridges and street performers", "location": "South Bank", "duration_min": 75},
        {"title": "Covent Garden", "category": "food", "notes": "Cafés, restaurants, and market halls", "location": "Covent Garden", "duration_min": 90},
        {"title": "Tate Modern", "category": "culture", "notes": "Modern art in a converted power station", "location": "Tate Modern", "duration_min": 90},
        {"title": "Camden Market", "category": "food", "notes": "Eclectic food stalls and vintage shopping", "location": "Camden Market", "duration_min": 90},
        {"title": "St Paul's Cathedral", "category": "culture", "notes": "Iconic dome and city views from the gallery", "location": "St Paul's Cathedral", "duration_min": 90},
        {"title": "Notting Hill", "category": "activity", "notes": "Colorful streets, antiques, and cafés", "location": "Notting Hill", "duration_min": 75},
        {"title": "Afternoon tea", "category": "food", "notes": "Classic British tea service at a local hotel or café", "location": "Mayfair", "duration_min": 90},
    ],
    "paris": [
        {"title": "Louvre Museum", "category": "culture", "notes": "Masterpieces including the Mona Lisa", "location": "Louvre", "duration_min": 150},
        {"title": "Eiffel Tower", "category": "culture", "notes": "Views from the iron lady — book ahead", "location": "Champ de Mars", "duration_min": 120},
        {"title": "Montmartre walk", "category": "activity", "notes": "Artists' square and Sacré-Cœur basilica", "location": "Montmartre", "duration_min": 90},
        {"title": "Seine river cruise", "category": "activity", "notes": "See the city from the water at golden hour", "location": "Seine", "duration_min": 75},
        {"title": "Marché des Enfants Rouges", "category": "food", "notes": "Paris's oldest covered market", "location": "Le Marais", "duration_min": 60},
        {"title": "Musée d'Orsay", "category": "culture", "notes": "Impressionist art in a grand railway station", "location": "Musée d'Orsay", "duration_min": 120},
        {"title": "Latin Quarter lunch", "category": "food", "notes": "Bistros and crêperies near the Sorbonne", "location": "Latin Quarter", "duration_min": 90},
        {"title": "Luxembourg Gardens", "category": "activity", "notes": "Picnic and people-watching in formal gardens", "location": "Jardin du Luxembourg", "duration_min": 75},
    ],
    "lisbon": [
        {"title": "Alfama district walk", "category": "activity", "notes": "Winding alleys, fado bars, and miradouros", "location": "Alfama", "duration_min": 90},
        {"title": "Pastéis de Belém", "category": "food", "notes": "Original custard tarts since 1837", "location": "Belém", "duration_min": 45},
        {"title": "Jerónimos Monastery", "category": "culture", "notes": "Manueline architecture and maritime history", "location": "Belém", "duration_min": 90},
        {"title": "Tram 28 ride", "category": "transport", "notes": "Classic yellow tram through historic neighborhoods", "location": "Graça", "duration_min": 60},
        {"title": "Time Out Market", "category": "food", "notes": "Food hall with top Lisbon chefs", "location": "Cais do Sodré", "duration_min": 90},
        {"title": "LX Factory", "category": "activity", "notes": "Creative hub with shops, street art, and brunch", "location": "Alcântara", "duration_min": 90},
        {"title": "São Jorge Castle", "category": "culture", "notes": "Hilltop castle with panoramic city views", "location": "Castelo", "duration_min": 90},
        {"title": "Sunset at Miradouro da Senhora do Monte", "category": "activity", "notes": "Best viewpoint over the terracotta rooftops", "location": "Graça", "duration_min": 60},
    ],
    "porto": [
        {"title": "Ribeira waterfront", "category": "activity", "notes": "Colorful riverside promenade and boat views", "location": "Ribeira", "duration_min": 75},
        {"title": "Francesinha at Café Santiago", "category": "food", "notes": "Porto's famous stacked sandwich", "location": "Baixa", "duration_min": 60},
        {"title": "Livraria Lello", "category": "culture", "notes": "Stunning bookshop that inspired Harry Potter", "location": "Cedofeita", "duration_min": 45},
        {"title": "Port wine cellar tour", "category": "food", "notes": "Tasting across the river in Vila Nova de Gaia", "location": "Gaia", "duration_min": 90},
        {"title": "São Bento Station", "category": "culture", "notes": "Azulejo tile panels depicting Portuguese history", "location": "São Bento", "duration_min": 30},
        {"title": "Clérigos Tower climb", "category": "sightseeing", "notes": "Baroque tower with 360° city views", "location": "Clérigos", "duration_min": 60},
        {"title": "Mercado do Bolhão", "category": "food", "notes": "Revitalized market for produce and petiscos", "location": "Bolhão", "duration_min": 75},
        {"title": "Foz do Douro beach walk", "category": "activity", "notes": "Atlantic boardwalk and seafood restaurants", "location": "Foz", "duration_min": 90},
    ],
    "barcelona": [
        {"title": "Sagrada Família", "category": "culture", "notes": "Gaudí's unfinished masterpiece — book tickets early", "location": "Eixample", "duration_min": 120},
        {"title": "La Boqueria Market", "category": "food", "notes": "Jamón, fruit juices, and tapas counters", "location": "La Rambla", "duration_min": 75},
        {"title": "Park Güell", "category": "culture", "notes": "Mosaic terraces and city panoramas", "location": "Gràcia", "duration_min": 90},
        {"title": "Gothic Quarter walk", "category": "activity", "notes": "Medieval lanes, plazas, and hidden courtyards", "location": "Barri Gòtic", "duration_min": 90},
        {"title": "Barceloneta beach", "category": "activity", "notes": "Swim, sunbathe, or chiringuito lunch", "location": "Barceloneta", "duration_min": 120},
        {"title": "Picasso Museum", "category": "culture", "notes": "Early works and Blue Period paintings", "location": "El Born", "duration_min": 90},
        {"title": "Tapas crawl in El Born", "category": "food", "notes": "Small plates and vermouth in trendy bars", "location": "El Born", "duration_min": 120},
        {"title": "Montjuïc cable car", "category": "transport", "notes": "Cable car up to castle views and gardens", "location": "Montjuïc", "duration_min": 90},
    ],
    "rome": [
        {"title": "Colosseum", "category": "culture", "notes": "Ancient amphitheatre — reserve skip-the-line tickets", "location": "Colosseo", "duration_min": 120},
        {"title": "Vatican Museums", "category": "culture", "notes": "Sistine Chapel and Renaissance collections", "location": "Vatican City", "duration_min": 150},
        {"title": "Trastevere dinner", "category": "food", "notes": "Cozy trattorias and ivy-covered alleys", "location": "Trastevere", "duration_min": 120},
        {"title": "Trevi Fountain & centro storico", "category": "activity", "notes": "Classic piazzas and gelato stops", "location": "Centro Storico", "duration_min": 90},
        {"title": "Borghese Gallery", "category": "culture", "notes": "Bernini sculptures in a villa gallery", "location": "Villa Borghese", "duration_min": 90},
        {"title": "Campo de' Fiori market", "category": "food", "notes": "Morning market and evening aperitivo spot", "location": "Campo de' Fiori", "duration_min": 60},
        {"title": "Appian Way bike ride", "category": "activity", "notes": "Ancient road through ruins and countryside", "location": "Appia Antica", "duration_min": 120},
        {"title": "Gelato tour", "category": "food", "notes": "Sample Rome's best gelaterias on foot", "location": "Centro", "duration_min": 60},
    ],
    "new york": [
        {"title": "Central Park", "category": "activity", "notes": "Bethesda Terrace, Bow Bridge, and picnics", "location": "Central Park", "duration_min": 120},
        {"title": "Metropolitan Museum of Art", "category": "culture", "notes": "Vast collection spanning millennia", "location": "Upper East Side", "duration_min": 150},
        {"title": "Brooklyn Bridge walk", "category": "activity", "notes": "Skyline views into DUMBO", "location": "Brooklyn Bridge", "duration_min": 75},
        {"title": "Chelsea Market lunch", "category": "food", "notes": "Food hall in a historic factory building", "location": "Chelsea", "duration_min": 90},
        {"title": "High Line stroll", "category": "activity", "notes": "Elevated park on a former rail line", "location": "Chelsea", "duration_min": 75},
        {"title": "Broadway show", "category": "culture", "notes": "Catch a matinee or evening performance", "location": "Times Square", "duration_min": 150},
        {"title": "Staten Island Ferry", "category": "transport", "notes": "Free harbor cruise with Statue of Liberty views", "location": "Whitehall Terminal", "duration_min": 60},
        {"title": "Smorgasburg", "category": "food", "notes": "Weekend food market with dozens of vendors", "location": "Williamsburg", "duration_min": 90},
    ],
    "san francisco": [
        {"title": "Golden Gate Bridge", "category": "activity", "notes": "Walk or bike across with bay views", "location": "Golden Gate Bridge", "duration_min": 90},
        {"title": "Ferry Building Marketplace", "category": "food", "notes": "Artisan food stalls on the waterfront", "location": "Embarcadero", "duration_min": 75},
        {"title": "Alcatraz tour", "category": "culture", "notes": "Historic island prison — book ferries early", "location": "Alcatraz Island", "duration_min": 150},
        {"title": "Mission District murals", "category": "culture", "notes": "Balmy Alley and Clarion Alley street art", "location": "Mission District", "duration_min": 90},
        {"title": "Dolores Park picnic", "category": "activity", "notes": "Sunny hill with skyline views", "location": "Mission Dolores", "duration_min": 90},
        {"title": "Cable car ride", "category": "transport", "notes": "Powell-Hyde line down to Fisherman's Wharf", "location": "Union Square", "duration_min": 45},
        {"title": "Fisherman's Wharf", "category": "food", "notes": "Clam chowder in sourdough and sea lions", "location": "Fisherman's Wharf", "duration_min": 90},
        {"title": "Twin Peaks sunset", "category": "activity", "notes": "Panoramic view over the whole city", "location": "Twin Peaks", "duration_min": 60},
    ],
    "tokyo": [
        {"title": "Senso-ji Temple", "category": "culture", "notes": "Asakusa's oldest temple and Nakamise shopping street", "location": "Asakusa", "duration_min": 90},
        {"title": "Tsukiji Outer Market", "category": "food", "notes": "Fresh sushi, tamagoyaki, and street snacks", "location": "Tsukiji", "duration_min": 90},
        {"title": "Shibuya Crossing", "category": "activity", "notes": "World's busiest intersection and Hachiko statue", "location": "Shibuya", "duration_min": 45},
        {"title": "teamLab Planets", "category": "culture", "notes": "Immersive digital art experience", "location": "Toyosu", "duration_min": 120},
        {"title": "Meiji Shrine", "category": "culture", "notes": "Serene forest shrine in the city center", "location": "Harajuku", "duration_min": 75},
        {"title": "Ramen in Shinjuku", "category": "food", "notes": "Omoide Yokocho alley bars and noodle shops", "location": "Shinjuku", "duration_min": 75},
        {"title": "Akihabara electronics", "category": "activity", "notes": "Anime, gadgets, and arcade culture", "location": "Akihabara", "duration_min": 90},
        {"title": "Day trip to Nikko", "category": "transport", "notes": "Ornate shrines and mountain scenery", "location": "Nikko", "duration_min": 480},
    ],
}

GENERIC_IDEAS = [
    {"title": "City center walking tour", "category": "activity", "notes": "Explore the main squares, streets, and landmarks on foot", "duration_min": 90},
    {"title": "Local food market", "category": "food", "notes": "Sample regional specialties at a busy market", "duration_min": 75},
    {"title": "Main museum or gallery", "category": "culture", "notes": "See the city's flagship collection or exhibition", "duration_min": 120},
    {"title": "Neighborhood café break", "category": "food", "notes": "Coffee and pastries at a popular local spot", "duration_min": 60},
    {"title": "Scenic viewpoint", "category": "activity", "notes": "Sunset or photo stop with a city panorama", "duration_min": 60},
    {"title": "Public park picnic", "category": "activity", "notes": "Relax outdoors with snacks from a nearby shop", "duration_min": 90},
    {"title": "Historic old town", "category": "culture", "notes": "Wander the oldest quarter and its architecture", "duration_min": 90},
    {"title": "Local transit adventure", "category": "transport", "notes": "Ride the metro, tram, or ferry like a local", "duration_min": 60},
]


@dataclass
class ActivitySuggestion:
    title: str
    location: str
    latitude: float | None
    longitude: float | None
    day_number: int
    url: str | None
    notes: str
    duration_min: int
    category: str = "activity"


def location_key(location: str) -> str:
    loc = location.lower().strip()
    keys = (
        ("london", "london"),
        ("paris", "paris"),
        ("lisbon", "lisbon"),
        ("porto", "porto"),
        ("barcelona", "barcelona"),
        ("rome", "rome"),
        ("roma", "rome"),
        ("new york", "new york"),
        ("nyc", "new york"),
        ("san francisco", "san francisco"),
        ("sf", "san francisco"),
        ("tokyo", "tokyo"),
        ("sintra", "lisbon"),
        ("amsterdam", "amsterdam"),
        ("berlin", "berlin"),
        ("madrid", "madrid"),
        ("dublin", "dublin"),
        ("edinburgh", "edinburgh"),
    )
    for needle, key in keys:
        if needle in loc:
            return key
    return loc.split(",")[0].strip() or loc


def _infer_category(title: str, notes: str = "", explicit: str | None = None) -> str:
    if explicit:
        return normalize_category(explicit)
    return activity_category(SimpleNamespace(title=title, notes=notes, location=""))["slug"]


def _curated_suggestions(location: str, num_days: int, per_day: int) -> list[ActivitySuggestion]:
    key = location_key(location)
    ideas = CURATED_IDEAS.get(key, GENERIC_IDEAS)
    num_days = normalize_num_days(num_days)
    target = min(num_days * per_day, MAX_SUGGESTIONS)
    city_label = location.split(",")[0].strip() or location
    suggestions: list[ActivitySuggestion] = []

    for i, idea in enumerate(ideas[:target]):
        day = (i % num_days) + 1
        title = idea["title"]
        notes = idea.get("notes") or f"Popular in {city_label}"
        suggestions.append(
            ActivitySuggestion(
                title=title,
                location=idea.get("location") or city_label,
                latitude=None,
                longitude=None,
                day_number=day,
                url=None,
                notes=notes,
                duration_min=idea.get("duration_min", 60),
                category=_infer_category(title, notes, idea.get("category")),
            )
        )
    return suggestions


def _looks_like_place(title: str) -> bool:
    lower = title.lower()
    if any(hint in lower for hint in PLACE_HINTS):
        return True
    words = title.split()
    if len(words) >= 3:
        return True
    if title.endswith(")") or "," in title:
        return True
    return False


async def _wikipedia_places(lat: float, lng: float, limit: int = 40) -> list[dict]:
    params = {
        "action": "query",
        "generator": "geosearch",
        "ggscoord": f"{lat}|{lng}",
        "ggsradius": 12000,
        "ggslimit": limit,
        "prop": "coordinates|info",
        "inprop": "url",
        "coprop": "type|name",
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as client:
        response = await client.get(WIKI_API, params=params)
        if response.status_code != 200:
            return []
        data = response.json()

    results = []
    for page in data.get("query", {}).get("pages", {}).values():
        title = page.get("title", "").strip()
        if not title or title.lower() in SKIP_TITLES:
            continue
        if len(title) < 4 or not _looks_like_place(title):
            continue
        coords = page.get("coordinates", [{}])[0]
        results.append({
            "title": title,
            "lat": coords.get("lat"),
            "lng": coords.get("lon"),
            "url": page.get("fullurl"),
        })
    return results


async def _overpass_places(lat: float, lng: float, limit: int = 25) -> list[dict]:
    query = f"""
    [out:json][timeout:25];
    (
      node["tourism"~"attraction|museum|gallery|viewpoint|theme_park"](around:8000,{lat},{lng});
      way["tourism"~"attraction|museum|gallery"](around:8000,{lat},{lng});
      node["leisure"="park"]["name"](around:8000,{lat},{lng});
      node["historic"~"castle|ruins"]["name"](around:8000,{lat},{lng});
    );
    out center {limit};
    """
    async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as client:
        response = await client.post(OVERPASS_API, data={"data": query})
        if response.status_code != 200:
            return []
        data = response.json()

    results = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("tourism") or tags.get("leisure")
        if not name or len(name) < 3:
            continue
        plat = el.get("lat") or el.get("center", {}).get("lat")
        plng = el.get("lon") or el.get("center", {}).get("lon")
        results.append({"title": name, "lat": plat, "lng": plng, "url": None})
    return results


def _dedupe_places(places: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique = []
    for p in places:
        key = p["title"].lower().strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def _place_to_suggestion(
    place: dict,
    *,
    day: int,
    city_label: str,
    location: str,
) -> ActivitySuggestion:
    title = place["title"]
    notes = place.get("notes") or f"Popular spot in {city_label}"
    return ActivitySuggestion(
        title=title,
        location=place.get("location") or city_label,
        latitude=place.get("lat"),
        longitude=place.get("lng"),
        day_number=day,
        url=place.get("url"),
        notes=notes,
        duration_min=place.get("duration_min")
        or (90 if any(w in title.lower() for w in ("museum", "gallery", "palace")) else 60),
        category=_infer_category(title, notes, place.get("category")),
    )


async def suggest_activities(
    location: str,
    num_days: int = 1,
    per_day: int = 4,
) -> list[ActivitySuggestion]:
    num_days = normalize_num_days(num_days)
    target = min(num_days * per_day, MAX_SUGGESTIONS)
    city_label = location.split(",")[0].strip() or location

    curated = _curated_suggestions(location, num_days, per_day)
    curated_places = [
        {
            "title": s.title,
            "lat": s.latitude,
            "lng": s.longitude,
            "url": s.url,
            "notes": s.notes,
            "location": s.location,
            "duration_min": s.duration_min,
            "category": s.category,
        }
        for s in curated
    ]

    api_places: list[dict] = []
    geo = await geocode_address(location)
    if geo:
        try:
            wiki = await _wikipedia_places(geo.latitude, geo.longitude, limit=target + 20)
            overpass = await _overpass_places(geo.latitude, geo.longitude, limit=target)
            api_places = _dedupe_places(overpass + wiki)
        except Exception:
            api_places = []

    merged_titles: set[str] = set()
    merged: list[dict] = []
    for place in curated_places + api_places:
        key = place["title"].lower().strip()
        if key in merged_titles:
            continue
        merged_titles.add(key)
        merged.append(place)
        if len(merged) >= target:
            break

    if not merged:
        return curated[:target]

    suggestions: list[ActivitySuggestion] = []
    for i, place in enumerate(merged[:target]):
        day = (i % num_days) + 1
        suggestions.append(
            _place_to_suggestion(place, day=day, city_label=city_label, location=location)
        )
    return suggestions


async def seed_suggested_activities(
    trip,
    member_id: str,
    db,
    *,
    fetch_photos: bool = False,
) -> int:
    """Create Activity rows from location suggestions. Returns count added."""
    from app.models import Activity
    from app.services.place_photos import fetch_place_photo

    try:
        suggestions = await suggest_activities(trip.location, trip.num_days or 1)
    except Exception:
        suggestions = _curated_suggestions(trip.location, trip.num_days or 1, per_day=4)

    if not suggestions:
        return 0

    existing = {
        a.title.lower().strip()
        for a in db.query(Activity).filter(Activity.trip_id == trip.id).all()
    }
    added = 0

    for s in suggestions:
        key = s.title.lower().strip()
        if key in existing:
            continue
        existing.add(key)

        photo_url = None
        if fetch_photos:
            try:
                photo_url = await fetch_place_photo(
                    title=s.title,
                    location=s.location,
                    latitude=s.latitude,
                    longitude=s.longitude,
                    city_context=trip.location,
                )
            except Exception:
                photo_url = None

        db.add(
            Activity(
                trip_id=trip.id,
                title=s.title,
                url=s.url,
                notes=s.notes,
                location=s.location,
                latitude=s.latitude,
                longitude=s.longitude,
                duration_min=s.duration_min,
                day_number=s.day_number,
                category=s.category,
                is_suggested=True,
                photo_url=photo_url,
                proposed_by_id=member_id,
            )
        )
        added += 1

    if added:
        db.commit()
    return added


async def ensure_trip_has_suggestions(
    trip,
    member_id: str,
    db,
    *,
    min_per_day: int = 3,
) -> int:
    """Top up suggested activities when a trip has few or none."""
    from app.models import Activity

    num_days = normalize_num_days(trip.num_days)
    target = min(num_days * min_per_day, MAX_SUGGESTIONS)
    suggested_count = (
        db.query(Activity)
        .filter(Activity.trip_id == trip.id, Activity.is_suggested.is_(True))
        .count()
    )
    if suggested_count >= target:
        return 0
    return await seed_suggested_activities(trip, member_id, db, fetch_photos=False)


async def seed_trip_background(trip_id: str, member_id: str) -> None:
    """Run suggestion seeding outside the request so create stays fast."""
    from app.database import SessionLocal
    from app.models import Trip

    db = SessionLocal()
    try:
        trip = db.query(Trip).filter(Trip.id == trip_id).first()
        if trip:
            await ensure_trip_has_suggestions(trip, member_id, db)
    except Exception:
        pass
    finally:
        db.close()
