# Itinerary Planner

A collaborative web app for friend groups to plan day trips together. Everyone proposes activities with locations and links, rates each idea 1–5, and the group gets a shared day-of itinerary with distances between stops.

Built with **Python + FastAPI**, Jinja templates, and **Tailwind CSS** (Play CDN).

## Features

- **Create & share trips** — generate a short invite code/link
- **Multiple trips** — manage several friend groups from one browser; your trip list is saved locally (no account needed)
- **Propose activities** — title, link, location, suggested time, duration, notes (photos auto-fetched)
- **Location geocoding** — addresses geocoded via OpenStreetMap; **free location typeahead** on location fields (no API key needed)
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

By default the app uses a local SQLite file (`group_day_planner.db`). To use [Turso](https://turso.tech) instead, copy `.env.example` to `.env` and set your credentials:

```bash
cp .env.example .env
# Create a Turso database (requires Turso CLI: https://docs.turso.tech/cli)
turso db create group-day-planner
turso db show group-day-planner --url      # → TURSO_DATABASE_URL
turso db tokens create group-day-planner    # → TURSO_AUTH_TOKEN
```

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
- **SQLAlchemy** + SQLite or **Turso** (libSQL) — database
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

1. Create a Turso database and set `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN` (see `.env.example`). The app auto-detects these and uses Turso instead of local SQLite.
2. Set a strong `SECRET_KEY` environment variable.
3. Run behind a reverse proxy (nginx) with HTTPS.
4. Use gunicorn + uvicorn workers:

```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Turso configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `TURSO_DATABASE_URL` | Yes (for Turso) | From `turso db show <name> --url` |
| `TURSO_AUTH_TOKEN` | Yes (for Turso) | From `turso db tokens create <name>` |
| `TURSO_LOCAL_PATH` | No | Local replica file path for faster reads |
| `DATABASE_PATH` | No | Local SQLite file when Turso is not configured |

When both `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` are set, the app uses Turso automatically. Leave them unset to keep using local SQLite.

To copy an existing local SQLite database into Turso:

```bash
turso db shell group-day-planner < group_day_planner.db.sql   # after .dump export
# or use turso db import / sqlite3 .dump piped into turso db shell
```

## License

MIT
