"""Detect overlapping scheduled activities on the same day."""

from dataclasses import dataclass

from app.services.distance import normalize_time_24


@dataclass
class TimeConflict:
    day: int
    activity_a_id: str
    activity_a_title: str
    activity_b_id: str
    activity_b_title: str


def _to_minutes(time_24: str | None) -> int | None:
    normalized = normalize_time_24(time_24, default="")
    if not normalized:
        return None
    hour, minute = map(int, normalized.split(":"))
    return hour * 60 + minute


def _activity_window(activity) -> tuple[int, int] | None:
    start = _to_minutes(activity.suggested_time)
    if start is None:
        return None
    duration = activity.duration_min or 0
    if duration <= 0:
        duration = 60
    return start, start + duration


def detect_day_conflicts(activities: list) -> list[TimeConflict]:
    """Find overlapping confirmed activities that have a start time."""
    conflicts: list[TimeConflict] = []
    by_day: dict[int, list] = {}
    for act in activities:
        if getattr(act, "is_suggested", False):
            continue
        day = act.day_number or 1
        by_day.setdefault(day, []).append(act)

    for day, day_acts in by_day.items():
        scheduled = []
        for act in day_acts:
            window = _activity_window(act)
            if window:
                scheduled.append((act, window))
        scheduled.sort(key=lambda item: item[1][0])
        for i, (a, (a_start, a_end)) in enumerate(scheduled):
            for b, (b_start, b_end) in scheduled[i + 1 :]:
                if b_start < a_end and a_start < b_end:
                    conflicts.append(
                        TimeConflict(
                            day=day,
                            activity_a_id=a.id,
                            activity_a_title=a.title,
                            activity_b_id=b.id,
                            activity_b_title=b.title,
                        )
                    )
    return conflicts
