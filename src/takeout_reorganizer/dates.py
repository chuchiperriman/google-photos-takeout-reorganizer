"""Extracción de fecha de toma desde EXIF, JSON de Takeout o nombre de fichero."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

from PIL import ExifTags, Image

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
    ".webp",
    ".gif",
    ".tif",
    ".tiff",
}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".3gp", ".avi", ".mkv"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

EXIF_DATETIME_TAGS = (
    "DateTimeOriginal",
    "DateTimeDigitized",
    "DateTime",
)

_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")

_FILENAME_DATE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "ymd"),
    (re.compile(r"(\d{4})(\d{2})(\d{2})"), "ymd_compact"),
    (re.compile(r"IMG_(\d{4})(\d{2})(\d{2})"), "ymd_compact"),
    (re.compile(r"PXL_(\d{4})(\d{2})(\d{2})"), "ymd_compact"),
    (re.compile(r"VID_(\d{4})(\d{2})(\d{2})"), "ymd_compact"),
    (re.compile(r"Screenshot_(\d{4})-(\d{2})-(\d{2})"), "ymd"),
    (re.compile(r"WhatsApp Image (\d{4})-(\d{2})-(\d{2})"), "ymd"),
    (re.compile(r"WhatsApp Video (\d{4})-(\d{2})-(\d{2})"), "ymd"),
]


def is_media_file(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_EXTENSIONS


def has_date_prefix(stem: str) -> bool:
    return bool(_DATE_PREFIX_RE.match(stem))


def strip_date_prefix(stem: str) -> str:
    return _DATE_PREFIX_RE.sub("", stem, count=1)


_YMD_IN_NAME_HYPHEN_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_YMD_IN_NAME_COMPACT_RE = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")


def _valid_ymd(y: int, m: int, d: int) -> bool:
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


def sanitize_stem_for_rename(stem: str) -> str:
    """Quita fechas yyyy-mm-dd o yyyymmdd del nombre (el prefijo de toma se añade aparte)."""
    result = strip_date_prefix(stem)

    while True:
        match = _YMD_IN_NAME_HYPHEN_RE.search(result)
        if match:
            y, m, d = (int(x) for x in match.group(0).split("-"))
            if _valid_ymd(y, m, d):
                result = result[: match.start()] + result[match.end() :]
                continue
        match = _YMD_IN_NAME_COMPACT_RE.search(result)
        if match:
            y, m, d = (int(match.group(i)) for i in range(1, 4))
            if _valid_ymd(y, m, d):
                result = result[: match.start()] + result[match.end() :]
                continue
        break

    result = re.sub(r"_+", "_", result)
    result = re.sub(r"-+", "-", result)
    result = result.strip("-_")
    return result if result else "file"


def format_date_prefix(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _parse_exif_datetime(value: str | bytes | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _exif_tag_map(exif) -> dict[str, object]:
    if exif is None:
        return {}
    result: dict[str, object] = {}
    for tag_id, value in exif.items():
        name = ExifTags.TAGS.get(tag_id, tag_id)
        result[name] = value
    if hasattr(exif, "get_ifd"):
        try:
            exif_sub = exif.get_ifd(0x8769)
            for tag_id, value in exif_sub.items():
                name = ExifTags.TAGS.get(tag_id, tag_id)
                result[name] = value
        except (KeyError, TypeError, ValueError):
            pass
    return result


def date_from_image_exif(path: Path) -> date | None:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            tags = _exif_tag_map(exif)
            for tag_name in EXIF_DATETIME_TAGS:
                parsed = _parse_exif_datetime(tags.get(tag_name))
                if parsed is not None:
                    return parsed
    except OSError:
        return None
    return None


def _parse_video_creation_time(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def date_from_video_metadata(path: Path) -> date | None:
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return None

    try:
        audio = MutagenFile(path)
    except OSError:
        return None
    if audio is None:
        return None

    tags = audio.tags
    if tags is None:
        return None

    for key in ("\xa9day", "creation_time", "date"):
        if key in tags:
            raw = tags[key]
            if isinstance(raw, (list, tuple)) and raw:
                raw = raw[0]
            if hasattr(raw, "text") and raw.text:
                raw = raw.text[0]
            parsed = _parse_video_creation_time(str(raw))
            if parsed is not None:
                return parsed

    return None


def date_from_file_metadata(path: Path) -> date | None:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return date_from_image_exif(path)
    if ext in VIDEO_EXTENSIONS:
        return date_from_video_metadata(path)
    return None


def _timestamp_to_date(timestamp: str | int | float) -> date | None:
    try:
        ts = float(timestamp)
    except (TypeError, ValueError):
        return None
    try:
        return datetime.fromtimestamp(ts).date()
    except (OSError, OverflowError, ValueError):
        return None


def _date_from_takeout_json(data: object) -> date | None:
    if not isinstance(data, dict):
        return None

    photo_taken = data.get("photoTakenTime")
    if isinstance(photo_taken, dict):
        ts = photo_taken.get("timestamp")
        if ts is not None:
            parsed = _timestamp_to_date(ts)
            if parsed is not None:
                return parsed

    creation = data.get("creationTime")
    if isinstance(creation, dict):
        ts = creation.get("timestamp")
        if ts is not None:
            parsed = _timestamp_to_date(ts)
            if parsed is not None:
                return parsed

    return None


def takeout_json_paths(media_path: Path) -> list[Path]:
    return [
        media_path.with_suffix(media_path.suffix + ".json"),
        media_path.with_suffix(media_path.suffix + ".supplemental-metadata.json"),
    ]


def date_from_takeout_json(media_path: Path) -> date | None:
    for json_path in takeout_json_paths(media_path):
        if not json_path.is_file():
            continue
        try:
            with json_path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        parsed = _date_from_takeout_json(data)
        if parsed is not None:
            return parsed
    return None


def _groups_to_date(groups: tuple[str, ...], kind: str) -> date | None:
    if kind == "ymd":
        y, m, d = int(groups[0]), int(groups[1]), int(groups[2])
    elif kind == "ymd_compact":
        y, m, d = int(groups[0]), int(groups[1]), int(groups[2])
    else:
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def date_from_filename(path: Path) -> date | None:
    name = path.stem
    if has_date_prefix(name):
        return None
    for pattern, kind in _FILENAME_DATE_PATTERNS:
        match = pattern.search(name)
        if match:
            parsed = _groups_to_date(match.groups(), kind)
            if parsed is not None:
                return parsed
    return None


def resolve_capture_date(path: Path) -> tuple[date | None, str]:
    """Devuelve (fecha, fuente) o (None, '') si no hay fecha."""
    d = date_from_file_metadata(path)
    if d is not None:
        return d, "metadata"

    d = date_from_takeout_json(path)
    if d is not None:
        return d, "takeout-json"

    d = date_from_filename(path)
    if d is not None:
        return d, "filename"

    return None, ""
