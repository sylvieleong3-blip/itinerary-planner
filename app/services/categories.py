"""Activity category labels and helpers (mockup-style tags)."""

from __future__ import annotations

import re
from typing import TypedDict


class ActivityCategory(TypedDict):
    slug: str
    label: str


VALID_CATEGORIES = frozenset({"transport", "culture", "food", "activity", "sightseeing"})

ACTIVITY_CATEGORIES: list[ActivityCategory] = [
    {"slug": "transport", "label": "TRANSPORT"},
    {"slug": "culture", "label": "CULTURE"},
    {"slug": "food", "label": "FOOD"},
    {"slug": "activity", "label": "ACTIVITY"},
    {"slug": "sightseeing", "label": "SIGHTSEEING"},
]

_LABEL_BY_SLUG = {c["slug"]: c["label"] for c in ACTIVITY_CATEGORIES}

_INFERENCE_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "food",
        re.compile(
            r"\b(food|eat|lunch|dinner|breakfast|brunch|picnic|cafe|coffee|restaurant|"
            r"bakery|bar|tapas|wine|tasting|market|bistro|lunchtime|francesinha)\b",
            re.I,
        ),
    ),
    (
        "transport",
        re.compile(
            r"\b(train|bus|taxi|uber|lyft|metro|subway|tram|ferry|boat|flight|"
            r"drive|car|shuttle|transfer|airport|station|express)\b",
            re.I,
        ),
    ),
    (
        "sightseeing",
        re.compile(
            r"\b(sightseeing|viewpoint|lookout|tower climb|observation|panorama|"
            r"scenic|photo stop|skyline|miradouro|overlook|climb.*tower|"
            r"city views?|rooftop views?)\b",
            re.I,
        ),
    ),
    (
        "culture",
        re.compile(
            r"\b(palace|museum|tour|castle|church|cathedral|monument|gallery|"
            r"plaza|square|landmark|culture|historic|architecture|bookshop|livraria)\b",
            re.I,
        ),
    ),
    (
        "activity",
        re.compile(
            r"\b(park|garden|beach|hike|trail|view|explore|visit|walk|stroll|"
            r"boat|cruise|kayak|surf|bike|swim|hotel|hostel|stay)\b",
            re.I,
        ),
    ),
]


def normalize_category(value: str | None) -> str:
    slug = (value or "").strip().lower()
    if slug in VALID_CATEGORIES:
        return slug
    return "activity"


def activity_category(activity) -> ActivityCategory:
    stored = getattr(activity, "category", None)
    if stored:
        slug = normalize_category(stored)
        return {"slug": slug, "label": _LABEL_BY_SLUG[slug]}

    haystack = " ".join(
        part
        for part in (
            getattr(activity, "title", "") or "",
            getattr(activity, "notes", "") or "",
            getattr(activity, "location", "") or "",
        )
        if part
    )
    for slug, pattern in _INFERENCE_RULES:
        if pattern.search(haystack):
            return {"slug": slug, "label": _LABEL_BY_SLUG[slug]}
    return {"slug": "activity", "label": "ACTIVITY"}
