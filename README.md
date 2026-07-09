# Itinerary Planner

A collaborative web app for friend groups to plan day trips together. Everyone proposes activities with locations and links, rates each idea 1–5, and the group gets a shared day-of itinerary with distances between stops.

Built with **Python + FastAPI**, Jinja templates, and **Tailwind CSS** (Play CDN).

## Features

- **Create & share trips** — generate a short invite code/link
- **Multiple trips** — manage several friend groups from one browser; your trip list is saved locally (no account needed)
- **Propose activities** — title, link, location, suggested time, duration, notes (photos auto-fetched)
- **Location geocoding** — addresses geocoded via OpenStreetMap Nominatim
- **1–5 voting** — rate enthusiasm; any `1` triggers a **veto**
- **Veto rule** — vetoed activities blocked from auto-inclusion; creator can override with a note
- **Status buckets** — Likely in / Maybe / Vetoed / Unlikely
- **Itinerary builder** — reorder stops, set times, handle vetoes
- **Published plan** — mobile-friendly timeline with map links and **distance/travel time between stops**

## Quick start

**Prerequisites:** Python 3.11+

```bash
cd ~/Projects/group-day-planner
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Open [http://localhost:8000](http://localhost:8000)

Or with uvicorn directly:

```bash
uvicorn app.main:app --reload --port 8000
```

## How it works

### Voting (1–5)

| Rating | Meaning |
|--------|---------|
| 1 | Strong no (**veto**) |
| 2 | Probably not |
| 3 | Neutral / flexible |
| 4 | Probably yes |
| 5 | Definitely yes |

**Veto:** Any `1` moves the activity to "Needs discussion." Creator must remove, replace, or override with a note.

### Photos

- Photos are **auto-fetched from Wikipedia / Wikimedia Commons** when you add a location or title
- Uses coordinates (from geocoding) or place name search — no upload or API key needed
- Works best for landmarks, parks, museums, and well-known venues
- Photos appear on the trip board, itinerary builder, and published day plan

### Location & distance

- Each activity can include a location (address or place name)
- On save, the app geocodes against the trip's city/area
- Published plan shows **distance and estimated travel time** between consecutive stops
- Tap **Directions** for Google Maps walking routes

### Links

| Link | Path | Purpose |
|------|------|---------|
| Invite | `/t/{code}/join` | Join, propose, vote |
| Board | `/t/{code}` | Trip dashboard |
| Plan | `/t/{code}/plan` | Published read-only itinerary |

## Tech stack

- **FastAPI** — web framework & API
- **SQLAlchemy** + SQLite — database (zero-config)
- **Jinja2** — server-rendered HTML templates
- **httpx** — async geocoding requests
- **OpenStreetMap Nominatim** — address → coordinates

## Project structure

```
app/
  main.py              # FastAPI app entry
  models.py            # SQLAlchemy models
  database.py          # DB engine & session
  routers/pages.py     # All routes (HTML + form handlers)
  services/
    scoring.py         # Vote summaries & status buckets
    distance.py        # Haversine distance & travel time
    geocode.py           # Address geocoding
    place_photos.py      # Wikipedia / Wikimedia location photos
    photos.py            # Photo display URL helpers
    trip.py              # Trip enrichment with distances
  templates/           # Jinja2 HTML templates (Tailwind via Play CDN)
  static/trips.js      # Client-side trip list (localStorage)
run.py                 # Dev server launcher
requirements.txt
```

## API overview

All interaction is via HTML forms. Key routes:

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Landing page |
| POST | `/create` | Create a new trip |
| POST | `/join` | Join by code from landing |
| GET | `/t/{code}` | Trip board |
| POST | `/t/{code}/activities` | Add activity |
| POST | `/t/{code}/vote/{id}` | Cast vote (1–5) |
| GET | `/t/{code}/build` | Itinerary builder |
| POST | `/t/{code}/build` | Save/publish itinerary |
| GET | `/t/{code}/plan` | Published day plan |

Member identity is stored in a cookie per trip (30-day expiry). Trips you create or join are listed on the home page via browser `localStorage` (`gdp_trips`); removing a trip from the list is local only and does not delete the trip from the database.

## Deploying

For production:

1. Switch SQLite to PostgreSQL (update `DATABASE_URL` in `app/database.py`)
2. Run behind a reverse proxy (nginx) with HTTPS
3. Use gunicorn + uvicorn workers:

```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## License

MIT
