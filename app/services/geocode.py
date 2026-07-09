from dataclasses import dataclass

import httpx


@dataclass
class GeocodeResult:
    latitude: float
    longitude: float
    display_name: str


async def geocode_address(address: str) -> GeocodeResult | None:
    address = address.strip()
    if not address:
        return None

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address, "format": "json", "limit": 1}
    headers = {
        "User-Agent": "ItineraryPlanner/1.0 (friend itinerary app)",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params, headers=headers)
        if response.status_code != 200:
            return None
        data = response.json()
        if not data:
            return None

        item = data[0]
        display = ", ".join(item["display_name"].split(",")[:3]).strip()
        return GeocodeResult(
            latitude=float(item["lat"]),
            longitude=float(item["lon"]),
            display_name=display,
        )
