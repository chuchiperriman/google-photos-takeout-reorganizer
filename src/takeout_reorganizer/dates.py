"""Extracción de fecha de toma desde EXIF, JSON de Takeout o nombre de fichero."""

from __future__ import annotations

import json
import re
import unicodedata
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
    # RAW (pares con JPG en la misma carpeta según ORGANIZACION_FOTOS.md)
    ".cr2",
    ".cr3",
    ".nef",
    ".nrw",
    ".arw",
    ".dng",
    ".orf",
    ".rw2",
    ".raf",
    ".pef",
    ".x3f",
}
VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".3gp",
    ".avi",
    ".mkv",
    ".mts",
    ".m2ts",
    ".mp",  # Motion Photo (vídeo asociado en Google Pixel / Takeout)
}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

EXIF_DATETIME_TAGS = (
    "DateTimeOriginal",
    "DateTimeDigitized",
    "DateTime",
)

_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")
_ORGANIZACION_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}(_.*)?$")
_YEAR_DIR_RE = re.compile(r"^\d{4}$")

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

_FILENAME_YEAR_PREFIX_RE = re.compile(r"^(\d{4})-(?!\d{2}-\d{2})")
_ALBUM_FOLDER_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

_FILENAME_DATETIME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})"), "ymd_hms"),
    (re.compile(r"IMG_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})"), "ymd_hms_compact"),
    (re.compile(r"PXL_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})"), "ymd_hms_compact"),
    (re.compile(r"VID_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})"), "ymd_hms_compact"),
]


def is_media_file(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_EXTENSIONS


def has_date_prefix(stem: str) -> bool:
    return bool(_DATE_PREFIX_RE.match(stem))


def has_organizacion_name(stem: str) -> bool:
    return bool(_ORGANIZACION_NAME_RE.match(stem))


def is_year_directory_name(name: str) -> bool:
    return bool(_YEAR_DIR_RE.fullmatch(name))


def strip_date_prefix(stem: str) -> str:
    return _DATE_PREFIX_RE.sub("", stem, count=1)


def strip_organizacion_prefix(stem: str) -> str:
    match = re.match(r"^\d{4}-\d{2}-\d{2}_\d{6}", stem)
    if not match:
        return stem
    rest = stem[match.end() :]
    if rest.startswith("_"):
        rest = rest[1:]
    return rest


_YMD_IN_NAME_HYPHEN_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_YMD_IN_NAME_COMPACT_RE = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")
_HMS_UNDERSCORE_RE = re.compile(r"(?<![0-9])(\d{2})(\d{2})(\d{2})(?![0-9])")


def _valid_ymd(y: int, m: int, d: int) -> bool:
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


def _valid_hms(h: int, mi: int, s: int) -> bool:
    return 0 <= h <= 23 and 0 <= mi <= 59 and 0 <= s <= 59


def sanitize_stem_for_rename(stem: str) -> str:
    """Quita prefijos y fechas/horas del nombre (el stem conforme al doc se añade aparte)."""
    result = strip_organizacion_prefix(stem)
    result = strip_date_prefix(result)

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
        match = _HMS_UNDERSCORE_RE.search(result)
        if match:
            h, mi, s = (int(match.group(i)) for i in range(1, 4))
            if _valid_hms(h, mi, s):
                result = result[: match.start()] + result[match.end() :]
                continue
        break

    result = re.sub(r"_+", "_", result)
    result = re.sub(r"-+", "-", result)
    result = result.strip("-_")
    return result if result else "file"


_FORBIDDEN_DESC_CHARS = re.compile(r"[?!&%\s]+")


def sanitize_description(text: str) -> str | None:
    """Normaliza texto para el sufijo opcional del nombre (minúsculas, sin tildes ni ñ)."""
    if not text or text == "file":
        return None
    normalized = unicodedata.normalize("NFD", text)
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    normalized = normalized.replace("ñ", "n").replace("Ñ", "n")
    normalized = normalized.lower()
    normalized = re.sub(r"[^\w.-]+", "_", normalized, flags=re.ASCII)
    normalized = _FORBIDDEN_DESC_CHARS.sub("_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_.")
    return normalized if normalized else None


def format_date_prefix(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def format_organizacion_stem(capture_dt: datetime, description: str | None = None) -> str:
    base = f"{capture_dt.strftime('%Y-%m-%d')}_{capture_dt.strftime('%H%M%S')}"
    if description:
        return f"{base}_{description}"
    return base


def _parse_exif_datetime(value: str | bytes | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
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


def datetime_from_image_exif(path: Path) -> datetime | None:
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


def date_from_image_exif(path: Path) -> date | None:
    dt = datetime_from_image_exif(path)
    return dt.date() if dt else None


def _parse_video_creation_time(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def datetime_from_video_metadata(path: Path) -> datetime | None:
    try:
        from mutagen import File as MutagenFile
        from mutagen import MutagenError
    except ImportError:
        return None

    try:
        audio = MutagenFile(path)
    except (OSError, MutagenError):
        return None
    except Exception:
        # Mutagen a veces elige un parser incorrecto (p. ej. WAVE para .m4v).
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


def date_from_video_metadata(path: Path) -> date | None:
    dt = datetime_from_video_metadata(path)
    return dt.date() if dt else None


def datetime_from_file_metadata(path: Path) -> datetime | None:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return datetime_from_image_exif(path)
    if ext in VIDEO_EXTENSIONS:
        return datetime_from_video_metadata(path)
    return None


def date_from_file_metadata(path: Path) -> date | None:
    dt = datetime_from_file_metadata(path)
    return dt.date() if dt else None


def _timestamp_to_datetime(timestamp: str | int | float) -> datetime | None:
    try:
        ts = float(timestamp)
    except (TypeError, ValueError):
        return None
    try:
        return datetime.fromtimestamp(ts)
    except (OSError, OverflowError, ValueError):
        return None


def _datetime_from_takeout_json(data: object) -> datetime | None:
    if not isinstance(data, dict):
        return None

    photo_taken = data.get("photoTakenTime")
    if isinstance(photo_taken, dict):
        ts = photo_taken.get("timestamp")
        if ts is not None:
            parsed = _timestamp_to_datetime(ts)
            if parsed is not None:
                return parsed

    creation = data.get("creationTime")
    if isinstance(creation, dict):
        ts = creation.get("timestamp")
        if ts is not None:
            parsed = _timestamp_to_datetime(ts)
            if parsed is not None:
                return parsed

    return None


def takeout_json_paths(media_path: Path) -> list[Path]:
    return [
        media_path.with_suffix(media_path.suffix + ".json"),
        media_path.with_suffix(media_path.suffix + ".supplemental-metadata.json"),
    ]


def is_takeout_media_sidecar(path: Path) -> bool:
    name = path.name
    if name.endswith(".supplemental-metadata.json"):
        return True
    if path.suffix.lower() != ".json":
        return False
    return Path(path.stem).suffix.lower() in MEDIA_EXTENSIONS


def media_path_for_takeout_sidecar(sidecar: Path) -> Path | None:
    name = sidecar.name
    if name.endswith(".supplemental-metadata.json"):
        base = name[: -len(".supplemental-metadata.json")]
        return sidecar.parent / base
    if sidecar.suffix.lower() == ".json" and is_takeout_media_sidecar(sidecar):
        return sidecar.parent / sidecar.stem
    return None


def datetime_from_takeout_json(media_path: Path) -> datetime | None:
    for json_path in takeout_json_paths(media_path):
        if not json_path.is_file():
            continue
        try:
            with json_path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        parsed = _datetime_from_takeout_json(data)
        if parsed is not None:
            return parsed
    return None


def date_from_takeout_json(media_path: Path) -> date | None:
    dt = datetime_from_takeout_json(media_path)
    return dt.date() if dt else None


def _groups_to_date(groups: tuple[str, ...], kind: str) -> date | None:
    if kind in ("ymd", "ymd_compact"):
        y, m, d = int(groups[0]), int(groups[1]), int(groups[2])
    else:
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _groups_to_datetime(groups: tuple[str, ...], kind: str) -> datetime | None:
    if kind == "ymd_hms":
        y, m, d = int(groups[0]), int(groups[1]), int(groups[2])
        h, mi, s = int(groups[3]), int(groups[4]), int(groups[5])
    elif kind == "ymd_hms_compact":
        y, m, d = int(groups[0]), int(groups[1]), int(groups[2])
        h, mi, s = int(groups[3]), int(groups[4]), int(groups[5])
    else:
        return None
    try:
        return datetime(y, m, d, h, mi, s)
    except ValueError:
        return None


def _stem_has_standardized_prefix(name: str) -> bool:
    return has_organizacion_name(name) or has_date_prefix(name)


def datetime_from_filename(path: Path) -> datetime | None:
    name = path.stem
    if _stem_has_standardized_prefix(name):
        return None
    for pattern, kind in _FILENAME_DATETIME_PATTERNS:
        match = pattern.search(name)
        if match:
            parsed = _groups_to_datetime(match.groups(), kind)
            if parsed is not None:
                return parsed
    for pattern, kind in _FILENAME_DATE_PATTERNS:
        match = pattern.search(name)
        if match:
            parsed = _groups_to_date(match.groups(), kind)
            if parsed is not None:
                return datetime.combine(parsed, datetime.min.time())
    match = _FILENAME_YEAR_PREFIX_RE.match(name)
    if match:
        y = int(match.group(1))
        if _valid_ymd(y, 1, 1):
            return datetime(y, 1, 1)
    return None


def datetime_from_album_folder(path: Path) -> datetime | None:
    """Año en el nombre de la carpeta padre (p. ej. «Photos from 2013»)."""
    match = _ALBUM_FOLDER_YEAR_RE.search(path.parent.name)
    if not match:
        return None
    y = int(match.group(1))
    if _valid_ymd(y, 1, 1):
        return datetime(y, 1, 1)
    return None


def date_from_filename(path: Path) -> date | None:
    dt = datetime_from_filename(path)
    return dt.date() if dt else None


def resolve_capture_datetime(path: Path) -> tuple[datetime | None, str]:
    """Devuelve (fecha-hora, fuente) o (None, '') si no hay fecha."""
    dt = datetime_from_file_metadata(path)
    if dt is not None:
        return dt, "metadata"

    dt = datetime_from_takeout_json(path)
    if dt is not None:
        return dt, "takeout-json"

    dt = datetime_from_filename(path)
    if dt is not None:
        source = "filename"
        if dt.time() == datetime.min.time() and dt.day == 1 and dt.month == 1:
            # Solo año en el nombre (p. ej. 2013-MOVIE).
            if _FILENAME_YEAR_PREFIX_RE.match(path.stem):
                source = "filename-year-only"
            else:
                source = "filename-date-only"
        elif dt.time() == datetime.min.time():
            dt = dt.replace(hour=0, minute=0, second=0)
            source = "filename-date-only"
        return dt, source

    dt = datetime_from_album_folder(path)
    if dt is not None:
        return dt, "album-folder-year-only"

    return None, ""


def resolve_capture_date(path: Path) -> tuple[date | None, str]:
    """Devuelve (fecha, fuente) o (None, '') si no hay fecha."""
    dt, source = resolve_capture_datetime(path)
    if dt is None:
        return None, ""
    return dt.date(), source
