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
    "kuala lumpur": [
        {"title": "Petronas Twin Towers", "category": "culture", "notes": "Skybridge and views from Malaysia's iconic towers", "location": "KLCC", "duration_min": 120},
        {"title": "Batu Caves", "category": "culture", "notes": "Rainbow stairs and Hindu temple inside limestone caves", "location": "Batu Caves", "duration_min": 90},
        {"title": "Jalan Alor street food", "category": "food", "notes": "Open-air hawker stalls and late-night bites", "location": "Jalan Alor", "duration_min": 90},
        {"title": "Merdeka Square", "category": "culture", "notes": "Historic colonial core and independence landmarks", "location": "Merdeka Square", "duration_min": 60},
        {"title": "KLCC Park", "category": "activity", "notes": "Shaded paths and fountains beneath the towers", "location": "KLCC Park", "duration_min": 75},
        {"title": "Central Market", "category": "food", "notes": "Handicrafts and Malaysian snacks under one roof", "location": "Central Market", "duration_min": 75},
        {"title": "Bukit Bintang", "category": "activity", "notes": "Shopping, cafés, and the city's busy nightlife strip", "location": "Bukit Bintang", "duration_min": 90},
        {"title": "Thean Hou Temple", "category": "culture", "notes": "Ornate six-tier Chinese temple with city views", "location": "Thean Hou Temple", "duration_min": 60},
    ],
    "malacca": [
        {"title": "Dutch Square (Red Square)", "category": "culture", "notes": "Terracotta Dutch buildings and trishaw photo spot", "location": "Dutch Square", "duration_min": 60},
        {"title": "Jonker Street night market", "category": "food", "notes": "Weekend street food, antiques, and local desserts", "location": "Jonker Walk", "duration_min": 90},
        {"title": "A Famosa & St Paul's Hill", "category": "culture", "notes": "Portuguese fortress ruins overlooking the strait", "location": "A Famosa", "duration_min": 75},
        {"title": "Malacca River cruise", "category": "activity", "notes": "Evening boat ride past murals and riverside cafés", "location": "Melaka River", "duration_min": 45},
        {"title": "Cheng Hoon Teng Temple", "category": "culture", "notes": "Oldest functioning Chinese temple in Malaysia", "location": "Cheng Hoon Teng", "duration_min": 45},
        {"title": "Baba Nyonya Heritage Museum", "category": "culture", "notes": "Peranakan townhouse museum in the old quarter", "location": "Heeren Street", "duration_min": 60},
    ],
    "george town": [
        {"title": "George Town street art walk", "category": "activity", "notes": "Famous murals and heritage shophouses in the UNESCO core", "location": "George Town", "duration_min": 90},
        {"title": "Kek Lok Si Temple", "category": "culture", "notes": "Hilltop Buddhist temple complex above Ayer Itam", "location": "Kek Lok Si", "duration_min": 90},
        {"title": "Penang Hill funicular", "category": "activity", "notes": "Ride up for rainforest views over the island", "location": "Penang Hill", "duration_min": 120},
        {"title": "Clan Jetties", "category": "culture", "notes": "Stilt-house waterfront villages and photo walks", "location": "Chew Jetty", "duration_min": 60},
        {"title": "Gurney Drive hawkers", "category": "food", "notes": "Classic Penang char kway teow, laksa, and cendol", "location": "Gurney Drive", "duration_min": 90},
        {"title": "Cheong Fatt Tze Mansion", "category": "culture", "notes": "Indigo-blue heritage mansion and guided tour", "location": "Leith Street", "duration_min": 60},
        {"title": "Little India lunch", "category": "food", "notes": "Banana leaf rice and spice markets on Queen Street", "location": "Little India", "duration_min": 75},
    ],
    "hat yai": [
        {"title": "Kim Yong Market", "category": "food", "notes": "Bustling market for southern Thai snacks and produce", "location": "Kim Yong Market", "duration_min": 75},
        {"title": "Ton Nga Chang Waterfall", "category": "activity", "notes": "Seven-tier waterfall park outside the city", "location": "Ton Nga Chang", "duration_min": 150},
        {"title": "ASEAN Night Bazaar", "category": "food", "notes": "Street food, shopping, and live music after dark", "location": "ASEAN Night Bazaar", "duration_min": 90},
        {"title": "Hat Yai Municipal Park", "category": "activity", "notes": "Cable car, standing Buddha, and city viewpoints", "location": "Municipal Park", "duration_min": 90},
        {"title": "Wat Hat Yai Nai", "category": "culture", "notes": "Giant reclining Buddha visible across town", "location": "Wat Hat Yai Nai", "duration_min": 45},
        {"title": "Lee Garden Plaza area", "category": "activity", "notes": "Central malls, cafés, and easy first-day orientation", "location": "Lee Garden", "duration_min": 75},
    ],
    "bangkok": [
        {"title": "Grand Palace", "category": "culture", "notes": "Ornate royal complex and Temple of the Emerald Buddha", "location": "Grand Palace", "duration_min": 150},
        {"title": "Wat Pho", "category": "culture", "notes": "Reclining Buddha and traditional massage school", "location": "Wat Pho", "duration_min": 90},
        {"title": "Chatuchak Weekend Market", "category": "food", "notes": "Massive market for food, fashion, and souvenirs", "location": "Chatuchak", "duration_min": 120},
        {"title": "Chao Phraya river ferry", "category": "transport", "notes": "Hop on/off past temples and riverside neighborhoods", "location": "Chao Phraya", "duration_min": 90},
        {"title": "Chinatown street food", "category": "food", "notes": "Yaowarat neon eats after sunset", "location": "Yaowarat", "duration_min": 90},
        {"title": "Jim Thompson House", "category": "culture", "notes": "Thai silk heritage home and garden museum", "location": "Jim Thompson House", "duration_min": 75},
    ],
    "corsica": [
        {"title": "Bonifacio cliffs", "category": "activity", "notes": "Limestone citadel town perched above turquoise straits", "location": "Bonifacio", "lat": 41.3874, "lng": 9.1592, "duration_min": 120},
        {"title": "Calvi citadel", "category": "culture", "notes": "Genoese fortress and cobbled lanes above the bay", "location": "Calvi", "lat": 42.5686, "lng": 8.7572, "duration_min": 90},
        {"title": "Lavezzi Islands boat trip", "category": "activity", "notes": "Granite islets and crystal water off the south coast", "location": "Bonifacio", "lat": 41.3874, "lng": 9.1592, "duration_min": 180},
        {"title": "Scandola Nature Reserve", "category": "activity", "notes": "UNESCO sea cliffs and red-rock coves by boat", "location": "Porto", "lat": 42.2598, "lng": 8.7028, "duration_min": 240},
        {"title": "Ajaccio old town", "category": "culture", "notes": "Napoleon's birthplace, market square, and harbor stroll", "location": "Ajaccio", "lat": 41.9267, "lng": 8.7369, "duration_min": 90},
        {"title": "Corte & Restonica Valley", "category": "activity", "notes": "Mountain heartland with river pools and hiking trails", "location": "Corte", "lat": 42.3092, "lng": 9.1492, "duration_min": 180},
        {"title": "Porto beach & Genoese tower", "category": "activity", "notes": "Sandy cove beneath dramatic red cliffs", "location": "Porto", "lat": 42.2598, "lng": 8.7028, "duration_min": 120},
        {"title": "Bastia vieux-port", "category": "food", "notes": "Harbor promenade and Corsican charcuterie cafés", "location": "Bastia", "lat": 42.6976, "lng": 9.4509, "duration_min": 75},
        {"title": "Désert des Agriates", "category": "activity", "notes": "Wild scrubland drive to remote Saleccia beach", "location": "Saint-Florent", "lat": 42.6811, "lng": 9.3031, "duration_min": 180},
        {"title": "Corsican wine tasting", "category": "food", "notes": "Vermentino and Niellucciu at a hillside domaine", "location": "Patrimonio", "lat": 42.5547, "lng": 9.3611, "duration_min": 90},
        {"title": "GR20 segment hike", "category": "activity", "notes": "Sample Europe's famous trail with a day-hike section", "location": "Vizzavona", "lat": 42.1636, "lng": 9.1619, "duration_min": 240},
        {"title": "Propriano coastal walk", "category": "activity", "notes": "Sunset stroll along the Valinco Gulf", "location": "Propriano", "lat": 41.6764, "lng": 8.9031, "duration_min": 75},
    ],
    "nice": [
        {"title": "Promenade des Anglais", "category": "activity", "notes": "Classic seafront walk from the Old Town to Castle Hill", "location": "Nice", "duration_min": 90},
        {"title": "Old Town (Vieux Nice)", "category": "culture", "notes": "Pastel alleys, Cours Saleya market, and baroque churches", "location": "Vieux Nice", "duration_min": 90},
        {"title": "Castle Hill panorama", "category": "activity", "notes": "Climb or elevator up for bay views", "location": "Colline du Château", "duration_min": 60},
        {"title": "Marc Chagall Museum", "category": "culture", "notes": "Largest public collection of the artist's biblical works", "location": "Cimiez", "duration_min": 90},
    ],
    "lyon": [
        {"title": "Vieux Lyon traboules", "category": "culture", "notes": "Hidden Renaissance passageways in the old quarter", "location": "Vieux Lyon", "duration_min": 90},
        {"title": "Les Halles de Lyon Paul Bocuse", "category": "food", "notes": "Iconic covered market for pralines and saucisson", "location": "Part-Dieu", "duration_min": 75},
        {"title": "Fourvière basilica", "category": "culture", "notes": "Hilltop church overlooking the city and rivers", "location": "Fourvière", "duration_min": 90},
        {"title": "Presqu'île riverside", "category": "activity", "notes": "Saône and Rhône confluence stroll at golden hour", "location": "Presqu'île", "duration_min": 75},
    ],
}

# Map alternate spellings and sub-cities to curated keys.
CITY_ALIASES: dict[str, str] = {
    alias: canonical.lower()
    for alias, canonical in (
        ("corscia", "corsica"),
        ("corse", "corsica"),
        ("ajaccio", "corsica"),
        ("bastia", "corsica"),
        ("bonifacio", "corsica"),
        ("calvi", "corsica"),
        ("porto", "corsica"),
        ("corte", "corsica"),
        ("propriano", "corsica"),
        ("saint-florent", "corsica"),
        ("melaka", "malacca"),
        ("georgetown", "george town"),
        ("penang", "george town"),
        ("kl", "kuala lumpur"),
        ("roma", "rome"),
        ("nyc", "new york"),
        ("sf", "san francisco"),
        ("saigon", "ho chi minh"),
    )
}

GENERIC_IDEA_TEMPLATES = [
    ("{city} walking tour", "activity", "Explore the main squares, streets, and landmarks on foot", 90),
    ("{city} food market", "food", "Sample regional specialties at a busy local market", 75),
    ("{city} museum or gallery", "culture", "See the city's flagship collection or exhibition", 120),
    ("Café break in {city}", "food", "Coffee and pastries at a popular neighborhood spot", 60),
    ("{city} scenic viewpoint", "activity", "Sunset or photo stop with a city panorama", 60),
    ("Park picnic in {city}", "activity", "Relax outdoors with snacks from a nearby shop", 90),
    ("Historic quarter of {city}", "culture", "Wander the oldest streets and local architecture", 90),
    ("Getting around {city}", "transport", "Ride the local metro, tram, or ferry like a resident", 60),
]

GENERIC_TITLES = frozenset(
    idea["title"].lower().strip()
    for idea in [
        {"title": "City center walking tour"},
        {"title": "Local food market"},
        {"title": "Main museum or gallery"},
        {"title": "Neighborhood café break"},
        {"title": "Scenic viewpoint"},
        {"title": "Public park picnic"},
        {"title": "Historic old town"},
        {"title": "Local transit adventure"},
    ]
)


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
    first = loc.split(",")[0].strip()
    if first in CITY_ALIASES:
        return CITY_ALIASES[first]
    keys = (
        ("london", "london"),
        ("paris", "paris"),
        ("lisbon", "lisbon"),
        ("porto", "porto"),
        ("barcelona", "barcelona"),
        ("rome", "rome"),
        ("new york", "new york"),
        ("san francisco", "san francisco"),
        ("tokyo", "tokyo"),
        ("sintra", "lisbon"),
        ("amsterdam", "amsterdam"),
        ("berlin", "berlin"),
        ("madrid", "madrid"),
        ("dublin", "dublin"),
        ("edinburgh", "edinburgh"),
        ("kuala lumpur", "kuala lumpur"),
        ("malacca", "malacca"),
        ("george town", "george town"),
        ("hat yai", "hat yai"),
        ("bangkok", "bangkok"),
        ("chiang mai", "chiang mai"),
        ("phuket", "phuket"),
        ("hanoi", "hanoi"),
        ("ho chi minh", "ho chi minh"),
        ("singapore", "singapore"),
        ("corsica", "corsica"),
        ("nice", "nice"),
        ("lyon", "lyon"),
        ("marseille", "marseille"),
        ("bordeaux", "bordeaux"),
        ("florence", "florence"),
        ("venice", "venice"),
        ("milan", "milan"),
        ("munich", "munich"),
        ("vienna", "vienna"),
        ("prague", "prague"),
        ("budapest", "budapest"),
        ("athens", "athens"),
        ("istanbul", "istanbul"),
        ("dubai", "dubai"),
        ("sydney", "sydney"),
        ("melbourne", "melbourne"),
        ("seoul", "seoul"),
        ("taipei", "taipei"),
        ("hong kong", "hong kong"),
        ("bali", "bali"),
        ("marrakech", "marrakech"),
        ("cairo", "cairo"),
        ("cape town", "cape town"),
    )
    for needle, key in keys:
        if needle in loc:
            return key
    return first or loc


def _city_label(location: str) -> str:
    return _canonical_city_name(location).split(",")[0].strip() or location


def _format_suggestion_location(
    idea: dict,
    city_label: str,
    country_code: str | None = None,
) -> str:
    """Build a geocodable location string for map pins."""
    from app.services.destinations import country_label

    loc = (idea.get("location") or city_label).strip()
    if city_label and city_label.lower() not in loc.lower():
        loc = f"{loc}, {city_label}"
    if country_code:
        country = country_label(country_code)
        if country and country.lower() not in loc.lower():
            loc = f"{loc}, {country}"
    return loc


def _coords_from_idea(idea: dict) -> tuple[float | None, float | None]:
    lat = idea.get("latitude", idea.get("lat"))
    lng = idea.get("longitude", idea.get("lng"))
    if lat is None or lng is None:
        return None, None
    try:
        return float(lat), float(lng)
    except (TypeError, ValueError):
        return None, None


def _suggestion_from_idea(
    idea: dict,
    *,
    day: int,
    city_label: str,
    country_code: str | None = None,
) -> ActivitySuggestion:
    title = idea["title"]
    notes = idea.get("notes") or f"Popular in {city_label}"
    lat, lng = _coords_from_idea(idea)
    return ActivitySuggestion(
        title=title,
        location=_format_suggestion_location(idea, city_label, country_code),
        latitude=lat,
        longitude=lng,
        day_number=day,
        url=idea.get("url"),
        notes=notes,
        duration_min=idea.get("duration_min", 60),
        category=_infer_category(title, notes, idea.get("category")),
    )


def _generic_ideas_for_city(city_label: str) -> list[dict]:
    city = city_label.strip() or "this city"
    return [
        {
            "title": template[0].format(city=city),
            "category": template[1],
            "notes": template[2],
            "duration_min": template[3],
        }
        for template in GENERIC_IDEA_TEMPLATES
    ]


def _canonical_city_name(location: str) -> str:
    from app.services.destinations import canonical_destination_name

    return canonical_destination_name(location)


def _search_location(city_name: str, country_code: str | None = None) -> str:
    from app.services.destinations import country_label

    city = _canonical_city_name(city_name)
    if not city:
        return city_name or ""
    if country_code:
        country = country_label(country_code)
        if country and country.lower() not in city.lower():
            return f"{city}, {country}"
    return city


def _city_day_groups(trip) -> list[dict]:
    from app.services.day_plan import day_plan_entries

    groups: list[dict] = []
    for index, entry in enumerate(day_plan_entries(trip)):
        day = index + 1
        if (
            groups
            and groups[-1]["full_name"] == entry.full_name
            and groups[-1]["country_code"] == entry.country_code
        ):
            groups[-1]["end_day"] = day
            groups[-1]["days"] += 1
        else:
            groups.append(
                {
                    "full_name": entry.full_name,
                    "city": entry.city,
                    "country_code": entry.country_code,
                    "start_day": day,
                    "end_day": day,
                    "days": 1,
                }
            )
    return groups


def _suggestion_key(title: str, location: str, day_number: int) -> tuple[str, str, int]:
    return (title.lower().strip(), (location or "").lower().strip(), day_number or 1)


def _matches_generic_template(title: str) -> bool:
    normalized = title.lower().strip()
    for template, _, _, _ in GENERIC_IDEA_TEMPLATES:
        if "{city}" not in template:
            if normalized == template.lower():
                return True
            continue
        prefix, suffix = template.split("{city}", 1)
        if normalized.startswith(prefix.lower()) and normalized.endswith(suffix.lower()):
            middle = normalized[len(prefix) : len(normalized) - len(suffix) if suffix else len(normalized)]
            if middle.strip():
                return True
    return False


def _is_generic_only(activities) -> bool:
    suggested = [a for a in activities if getattr(a, "is_suggested", False)]
    if not suggested:
        return False
    for activity in suggested:
        title = (activity.title or "").lower().strip()
        if title not in GENERIC_TITLES and not _matches_generic_template(activity.title or ""):
            return False
    return True


def _infer_category(title: str, notes: str = "", explicit: str | None = None) -> str:
    if explicit:
        return normalize_category(explicit)
    return activity_category(SimpleNamespace(title=title, notes=notes, location=""))["slug"]


def _curated_suggestions(
    location: str,
    num_days: int,
    per_day: int,
    *,
    country_code: str | None = None,
) -> list[ActivitySuggestion]:
    key = location_key(location)
    city_label = _city_label(location)
    curated = list(CURATED_IDEAS.get(key) or [])
    generic = _generic_ideas_for_city(city_label)

    seen_titles: set[str] = set()
    pool: list[dict] = []
    for idea in curated + generic:
        title_key = idea["title"].lower().strip()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        pool.append(idea)

    num_days = normalize_num_days(num_days)
    per_day = max(1, per_day)
    suggestions: list[ActivitySuggestion] = []
    pool_idx = 0

    for day in range(1, num_days + 1):
        for _ in range(per_day):
            if pool_idx >= len(pool):
                break
            idea = pool[pool_idx]
            pool_idx += 1
            suggestions.append(
                _suggestion_from_idea(
                    idea,
                    day=day,
                    city_label=city_label,
                    country_code=country_code,
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


async def resolve_suggestion_coordinates(
    title: str,
    location: str,
    trip,
    *,
    day_number: int | None = None,
    country_code: str | None = None,
    cache: dict[str, tuple[float | None, float | None, str | None]] | None = None,
) -> tuple[float | None, float | None, str | None]:
    """Geocode a suggestion title/location for map pins. Returns lat, lng, display location."""
    from app.services.day_plan import day_plan_entries
    from app.services.geocode import geocode_for_trip, get_trip_anchors

    cache_key = f"{title}|{location}|{day_number}".lower()
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    day_entry = None
    if day_number:
        entries = day_plan_entries(trip)
        if 1 <= day_number <= len(entries):
            day_entry = entries[day_number - 1]

    city_context = (day_entry.full_name if day_entry else "") or ""
    country = country_code or (day_entry.country_code if day_entry else None)

    queries: list[str] = []
    seen: set[str] = set()

    def add_query(text: str) -> None:
        key = text.strip().lower()
        if key and key not in seen:
            seen.add(key)
            queries.append(text.strip())

    if title and location:
        add_query(f"{title}, {location}")
    if title and city_context:
        add_query(f"{title}, {city_context}")
    if location:
        add_query(location)
    if title:
        add_query(title)

    anchors = await get_trip_anchors(trip)
    anchor = anchors[0] if anchors else None

    for query in queries:
        try:
            geo = await geocode_for_trip(query, trip, anchor=anchor)
        except Exception:
            geo = None
        if geo:
            display = geo.display_name
            if country and display:
                from app.services.destinations import country_label

                country_name = country_label(country)
                if country_name.lower() not in display.lower():
                    display = f"{display}, {country_name}"
            result = (geo.latitude, geo.longitude, display)
            if cache is not None:
                cache[cache_key] = result
            return result

    result = (None, None, None)
    if cache is not None:
        cache[cache_key] = result
    return result


async def enrich_suggestion_coordinates(
    suggestion: ActivitySuggestion,
    trip,
    *,
    country_code: str | None = None,
    cache: dict[str, tuple[float | None, float | None, str | None]] | None = None,
) -> ActivitySuggestion:
    if suggestion.latitude is not None and suggestion.longitude is not None:
        return suggestion
    lat, lng, display = await resolve_suggestion_coordinates(
        suggestion.title,
        suggestion.location,
        trip,
        day_number=suggestion.day_number,
        country_code=country_code,
        cache=cache,
    )
    if lat is not None and lng is not None:
        suggestion.latitude = lat
        suggestion.longitude = lng
        if display:
            suggestion.location = display
    return suggestion


async def geocode_trip_suggestions(trip_id: str, *, limit: int = 40) -> int:
    """Background geocoding for suggested activities missing map coordinates."""
    import asyncio

    from app.database import SessionLocal
    from app.models import Activity, Trip
    from app.services.day_plan import day_plan_entries
    from sqlalchemy.orm import joinedload

    db = SessionLocal()
    try:
        trip = (
            db.query(Trip)
            .options(joinedload(Trip.destinations))
            .filter(Trip.id == trip_id)
            .first()
        )
        if not trip:
            return 0

        missing = (
            db.query(Activity)
            .filter(
                Activity.trip_id == trip.id,
                Activity.is_suggested.is_(True),
                Activity.latitude.is_(None),
            )
            .order_by(Activity.day_number, Activity.created_at)
            .limit(limit)
            .all()
        )
        if not missing:
            return 0

        entries = day_plan_entries(trip)
        pending = [
            {
                "id": activity.id,
                "title": activity.title,
                "location": activity.location or "",
                "day": activity.day_number or 1,
                "country_code": (
                    entries[(activity.day_number or 1) - 1].country_code
                    if 1 <= (activity.day_number or 1) <= len(entries)
                    else None
                ),
            }
            for activity in missing
        ]
        db.expunge(trip)
        for destination in trip.destinations:
            db.expunge(destination)
    finally:
        db.close()

    cache: dict[str, tuple[float | None, float | None, str | None]] = {}
    updates: list[tuple[str, float, float, str | None]] = []

    for item in pending:
        lat, lng, display = await resolve_suggestion_coordinates(
            item["title"],
            item["location"],
            trip,
            day_number=item["day"],
            country_code=item["country_code"],
            cache=cache,
        )
        if lat is not None and lng is not None:
            updates.append((item["id"], lat, lng, display))
        await asyncio.sleep(1.05)

    if not updates:
        return 0

    db = SessionLocal()
    try:
        for activity_id, lat, lng, display in updates:
            activity = db.query(Activity).filter(Activity.id == activity_id).first()
            if not activity:
                continue
            activity.latitude = lat
            activity.longitude = lng
            if display:
                activity.location = display
        db.commit()
        return len(updates)
    except Exception:
        db.rollback()
        return 0
    finally:
        db.close()


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
    *,
    country_code: str | None = None,
    use_api: bool = True,
) -> list[ActivitySuggestion]:
    num_days = normalize_num_days(num_days)
    per_day = max(1, per_day)
    target = min(num_days * per_day, MAX_SUGGESTIONS)
    city_label = _city_label(location)
    search_location = _search_location(location, country_code)

    curated = _curated_suggestions(search_location, num_days, per_day, country_code=country_code)
    if not use_api:
        return curated[:target]

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
    geo = await geocode_address(search_location, countrycodes=country_code)
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

    groups = _city_day_groups(trip)
    if not groups:
        num_days = normalize_num_days(trip.num_days)
        groups = [
            {
                "full_name": trip.location,
                "city": _city_label(trip.location),
                "country_code": None,
                "start_day": 1,
                "end_day": num_days,
                "days": num_days,
            }
        ]

    num_days = normalize_num_days(trip.num_days)
    per_city = min(4, max(2, (4 * num_days) // max(1, len(groups))))
    suggestions: list[ActivitySuggestion] = []

    for group in groups:
        city_name = group["full_name"]
        city_days = group["days"]
        start_day = group["start_day"]
        country_code = group.get("country_code")
        try:
            city_suggestions = await suggest_activities(
                city_name,
                city_days,
                per_day=per_city,
                country_code=country_code,
                use_api=False,
            )
        except Exception:
            city_suggestions = _curated_suggestions(
                city_name, city_days, per_day=per_city, country_code=country_code
            )
        for s in city_suggestions:
            suggestions.append(
                ActivitySuggestion(
                    title=s.title,
                    day_number=min(num_days, start_day + (s.day_number - 1)),
                    latitude=s.latitude,
                    longitude=s.longitude,
                    location=s.location,
                    url=s.url,
                    notes=s.notes,
                    duration_min=s.duration_min,
                    category=s.category,
                )
            )

    if not suggestions:
        return 0

    existing = {
        _suggestion_key(a.title, a.location or "", a.day_number or 1)
        for a in db.query(Activity).filter(Activity.trip_id == trip.id).all()
    }
    added = 0

    for s in suggestions:
        key = _suggestion_key(s.title, s.location or "", s.day_number)
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
                    city_context=s.location or trip.location,
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
    suggested = (
        db.query(Activity)
        .filter(Activity.trip_id == trip.id, Activity.is_suggested.is_(True))
        .all()
    )

    if suggested and _is_generic_only(suggested):
        for activity in suggested:
            db.delete(activity)
        db.commit()
        return await seed_suggested_activities(trip, member_id, db, fetch_photos=False)

    counts: dict[int, int] = {}
    for activity in suggested:
        day = activity.day_number or 1
        counts[day] = counts.get(day, 0) + 1

    needs_more = not suggested
    if not needs_more:
        for day in range(1, num_days + 1):
            if counts.get(day, 0) < min_per_day:
                needs_more = True
                break

    if not needs_more:
        return 0
    return await seed_suggested_activities(trip, member_id, db, fetch_photos=False)


async def seed_trip_background(trip_id: str, member_id: str) -> None:
    """Run suggestion seeding outside the request so create stays fast."""
    from app.database import SessionLocal
    from app.models import Trip
    from sqlalchemy.orm import joinedload

    db = SessionLocal()
    try:
        trip = (
            db.query(Trip)
            .options(joinedload(Trip.destinations))
            .filter(Trip.id == trip_id)
            .first()
        )
        if trip:
            await ensure_trip_has_suggestions(trip, member_id, db)
            await geocode_trip_suggestions(trip.id, limit=40)
    except Exception:
        pass
    finally:
        db.close()
