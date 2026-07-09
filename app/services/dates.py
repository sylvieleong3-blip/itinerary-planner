"""Date helpers for multi-day trips."""

from datetime import datetime, timedelta


def _short_month_day(dt: datetime) -> str:
    return f"{dt.strftime('%b')} {dt.day}"


def format_day_date(start_date: str, day_number: int) -> str:
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        day = start + timedelta(days=day_number - 1)
        return f"{day.strftime('%a')}, {_short_month_day(day)}"
    except ValueError:
        return f"Day {day_number}"


def trip_date_range(start_date: str, num_days: int) -> str:
    if num_days <= 1:
        try:
            return datetime.strptime(start_date, "%Y-%m-%d").strftime("%b %d, %Y")
        except ValueError:
            return start_date
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = start + timedelta(days=num_days - 1)
        if start.year == end.year:
            return f"{_short_month_day(start)} – {_short_month_day(end)}, {end.year}"
        return f"{_short_month_day(start)}, {start.year} – {_short_month_day(end)}, {end.year}"
    except ValueError:
        return start_date
