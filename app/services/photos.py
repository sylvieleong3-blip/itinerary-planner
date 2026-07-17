"""Photo URL helpers for activities."""

import uuid
from pathlib import Path

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads"
ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO_BYTES = 5 * 1024 * 1024


def _detect_image_type(data: bytes) -> str | None:
    if len(data) < 12:
        return None
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def ensure_upload_dir(trip_id: str) -> Path:
    path = UPLOAD_DIR / trip_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_trip_photo(trip_id: str, data: bytes, content_type: str) -> str:
    detected = _detect_image_type(data)
    if not detected or detected not in ALLOWED_PHOTO_TYPES:
        raise ValueError("Unsupported image type")
    if content_type not in ALLOWED_PHOTO_TYPES:
        raise ValueError("Unsupported image type")
    if detected != content_type:
        raise ValueError("Image content does not match declared type")
    if len(data) > MAX_PHOTO_BYTES:
        raise ValueError("Image too large (max 5MB)")
    ext = ".jpg" if detected == "image/jpeg" else ".png" if detected == "image/png" else ".webp"
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = ensure_upload_dir(trip_id) / filename
    dest.write_bytes(data)
    return f"/static/uploads/{trip_id}/{filename}"


def activity_photo_url(activity) -> str | None:
    if getattr(activity, "photo_path", None):
        return activity.photo_path
    if getattr(activity, "photo_url", None):
        return activity.photo_url
    return None


def delete_photo_file(photo_path: str | None) -> None:
    """Remove uploaded files when an activity or photo is deleted."""
    if not photo_path or not photo_path.startswith("/static/uploads/"):
        return
    relative = photo_path.removeprefix("/static/uploads/")
    file_path = UPLOAD_DIR / relative
    if file_path.is_file():
        file_path.unlink()
