"""Photo URL helpers for activities."""

from pathlib import Path

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads"


def activity_photo_url(activity) -> str | None:
    if getattr(activity, "photo_path", None):
        return activity.photo_path
    if getattr(activity, "photo_url", None):
        return activity.photo_url
    return None


def delete_photo_file(photo_path: str | None) -> None:
    """Remove legacy uploaded files when an activity is deleted."""
    if not photo_path or not photo_path.startswith("/static/uploads/"):
        return
    filename = photo_path.removeprefix("/static/uploads/")
    file_path = UPLOAD_DIR / filename
    if file_path.is_file():
        file_path.unlink()
