"""Comprime vídeos y exporta RAW a JPEG."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import rawpy
from PIL import Image

from takeout_reorganizer.dates import RAW_EXTENSIONS

logger = logging.getLogger(__name__)

SOURCE_EXTENSIONS = {".mov", ".avi", ".mts"}
DEFAULT_CRF = 23
DEFAULT_PRESET = "medium"
DEFAULT_AUDIO_BITRATE = "128k"
DEFAULT_JPEG_QUALITY = 92
JPEG_SUFFIXES = {".jpg", ".jpeg"}


@dataclass
class RunStats:
    videos_converted: int = 0
    raw_converted: int = 0
    skipped_exists: int = 0
    skipped_jpeg_pair: int = 0
    deleted: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)


def merge_stats(into: RunStats, other: RunStats) -> None:
    into.videos_converted += other.videos_converted
    into.raw_converted += other.raw_converted
    into.skipped_exists += other.skipped_exists
    into.skipped_jpeg_pair += other.skipped_jpeg_pair
    into.deleted += other.deleted
    into.errors += other.errors
    into.error_messages.extend(other.error_messages)


def collect_source_videos(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS:
            files.append(path)
    return sorted(files)


def collect_raw_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in RAW_EXTENSIONS:
            files.append(path)
    return sorted(files)


def has_jpeg_sibling(raw_path: Path) -> bool:
    stem = raw_path.with_suffix("")
    for suffix in JPEG_SUFFIXES:
        if stem.with_suffix(suffix).is_file():
            return True
    return False


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def copy_file_times(src: Path, dest: Path) -> None:
    src_stat = src.stat()
    os.utime(dest, (src_stat.st_atime, src_stat.st_mtime))


def ffmpeg_had_errors(stderr: str) -> bool:
    """True si ffmpeg escribió algo que no sea la línea de progreso (-stats)."""
    for raw in stderr.replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("frame=") or line.startswith("size="):
            continue
        return True
    return False


def compress_one(
    src: Path,
    dest: Path,
    *,
    crf: int,
    preset: str,
    audio_bitrate: str,
) -> str:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-stats",
        "-y",
        "-i",
        str(src),
        "-map_metadata",
        "0",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        audio_bitrate,
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    process = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stderr is not None
    chunks: list[str] = []
    while True:
        chunk = process.stderr.read(1024)
        if not chunk:
            break
        chunks.append(chunk)
        sys.stderr.write(chunk)
        sys.stderr.flush()
    returncode = process.wait()
    stderr = "".join(chunks)
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, cmd, stderr=stderr)
    return stderr


def export_raw_to_jpeg(src: Path, dest: Path, *, quality: int) -> None:
    with rawpy.imread(str(src)) as raw:
        rgb = raw.postprocess(use_camera_wb=True, output_bps=8)
    Image.fromarray(rgb).save(dest, "JPEG", quality=quality, optimize=True)


def run_videos(
    root: Path,
    dry_run: bool,
    *,
    delete_originals: bool = False,
    crf: int = DEFAULT_CRF,
    preset: str = DEFAULT_PRESET,
    audio_bitrate: str = DEFAULT_AUDIO_BITRATE,
) -> RunStats:
    stats = RunStats()
    if not root.is_dir():
        logger.error("No es un directorio: %s", root)
        stats.errors += 1
        stats.error_messages.append(f"No es un directorio: {root}")
        return stats

    if not dry_run and not ffmpeg_available():
        logger.error("ffmpeg no está en el PATH")
        stats.errors += 1
        stats.error_messages.append("ffmpeg no está en el PATH")
        return stats

    for src in collect_source_videos(root):
        dest = src.with_suffix(".mp4")
        if dest.exists():
            logger.info("Salto (ya existe): %s", dest)
            stats.skipped_exists += 1
            continue

        logger.info("Comprimir: %s -> %s", src, dest)
        if dry_run:
            stats.videos_converted += 1
            if delete_originals:
                logger.info("  se eliminaría el original: %s", src)
            continue

        stderr = ""
        try:
            stderr = compress_one(
                src,
                dest,
                crf=crf,
                preset=preset,
                audio_bitrate=audio_bitrate,
            )
        except (subprocess.CalledProcessError, OSError) as e:
            stats.errors += 1
            stats.error_messages.append(f"{src}: {e}")
            logger.error("Error al comprimir %s: %s", src, e)
            dest.unlink(missing_ok=True)
            continue

        if not dest.is_file() or dest.stat().st_size == 0:
            dest.unlink(missing_ok=True)
            stats.errors += 1
            stats.error_messages.append(f"{src}: ffmpeg no generó un mp4 válido")
            logger.error("Error al comprimir %s: ffmpeg no generó un mp4 válido", src)
            continue

        try:
            copy_file_times(src, dest)
        except OSError as e:
            logger.warning("No se pudo copiar la fecha de %s: %s", src, e)

        stats.videos_converted += 1
        if ffmpeg_had_errors(stderr):
            stats.errors += 1
            stats.error_messages.append(
                f"{src}: ffmpeg reportó errores de decodificación; se conserva el original"
            )
            logger.error(
                "ffmpeg reportó errores; se conserva el original: %s",
                src,
            )
            continue

        if delete_originals:
            try:
                src.unlink()
            except OSError as e:
                stats.errors += 1
                stats.error_messages.append(f"{src}: {e}")
                logger.error("Error al borrar original %s: %s", src, e)
                continue
            stats.deleted += 1
            logger.info("Eliminado original: %s", src)

    return stats


def run_raw_to_jpeg(
    root: Path,
    dry_run: bool,
    *,
    delete_originals: bool = False,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> RunStats:
    stats = RunStats()
    if not root.is_dir():
        logger.error("No es un directorio: %s", root)
        stats.errors += 1
        stats.error_messages.append(f"No es un directorio: {root}")
        return stats

    for src in collect_raw_files(root):
        dest = src.with_suffix(".jpg")
        if has_jpeg_sibling(src):
            logger.info("Salto (ya hay JPEG): %s", src)
            stats.skipped_jpeg_pair += 1
            continue
        if dest.exists():
            logger.info("Salto (ya existe): %s", dest)
            stats.skipped_exists += 1
            continue

        logger.info("Exportar RAW: %s -> %s", src, dest)
        if dry_run:
            stats.raw_converted += 1
            if delete_originals:
                logger.info("  se eliminaría el original: %s", src)
            continue

        try:
            export_raw_to_jpeg(src, dest, quality=jpeg_quality)
        except (rawpy.LibRawFileUnsupportedError, OSError, ValueError) as e:
            stats.errors += 1
            stats.error_messages.append(f"{src}: {e}")
            logger.error("Error al exportar %s: %s", src, e)
            dest.unlink(missing_ok=True)
            continue

        if not dest.is_file() or dest.stat().st_size == 0:
            dest.unlink(missing_ok=True)
            stats.errors += 1
            stats.error_messages.append(f"{src}: no se generó un JPEG válido")
            logger.error("Error al exportar %s: no se generó un JPEG válido", src)
            continue

        try:
            copy_file_times(src, dest)
        except OSError as e:
            logger.warning("No se pudo copiar la fecha de %s: %s", src, e)

        stats.raw_converted += 1
        if delete_originals:
            try:
                src.unlink()
            except OSError as e:
                stats.errors += 1
                stats.error_messages.append(f"{src}: {e}")
                logger.error("Error al borrar original %s: %s", src, e)
                continue
            stats.deleted += 1
            logger.info("Eliminado original: %s", src)

    return stats


def print_summary(stats: RunStats, dry_run: bool) -> None:
    mode = " (simulación)" if dry_run else ""
    print(f"\n--- Resumen{mode} ---")
    if stats.videos_converted:
        print(f"Vídeos convertidos: {stats.videos_converted}")
    if stats.raw_converted:
        print(f"RAW exportados a JPEG: {stats.raw_converted}")
    if stats.skipped_exists:
        print(f"Saltados (destino ya existe): {stats.skipped_exists}")
    if stats.skipped_jpeg_pair:
        print(f"Saltados (ya hay JPEG del mismo nombre): {stats.skipped_jpeg_pair}")
    if stats.deleted:
        print(f"Originales eliminados: {stats.deleted}")
    print(f"Errores: {stats.errors}")
    if stats.error_messages:
        for msg in stats.error_messages:
            print(f"  - {msg}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Comprime vídeos .MOV/.AVI/.MTS a .mp4 (ffmpeg) y, con --raw-to-jpeg, "
            "exporta RAW (.ARW, .CR2, …) a .jpg (rawpy)."
        ),
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directorio a escanear (se recorre recursivamente)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostrar qué se haría sin convertir ficheros",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Borrar el original solo si la conversión termina sin errores",
    )
    parser.add_argument(
        "--raw-to-jpeg",
        action="store_true",
        help="Exportar ficheros RAW a .jpg (mismas extensiones que en rename-by-date)",
    )
    parser.add_argument(
        "--skip-video",
        action="store_true",
        help="No comprimir vídeos (útil solo con --raw-to-jpeg)",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=DEFAULT_CRF,
        help=f"Calidad x264 (18 más calidad, 28 más pequeño; por defecto {DEFAULT_CRF})",
    )
    parser.add_argument(
        "--preset",
        default=DEFAULT_PRESET,
        help=f"Preset x264 (ultrafast…veryslow; por defecto {DEFAULT_PRESET})",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=DEFAULT_JPEG_QUALITY,
        help=f"Calidad JPEG al exportar RAW (1-100; por defecto {DEFAULT_JPEG_QUALITY})",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Más detalle en el log",
    )
    args = parser.parse_args(argv)

    if not args.skip_video and not args.raw_to_jpeg:
        pass  # solo vídeo (comportamiento por defecto)
    elif args.skip_video and not args.raw_to_jpeg:
        parser.error("usa --raw-to-jpeg con --skip-video, o quita --skip-video")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if args.dry_run:
        logger.info("Modo simulación (--dry-run)")

    root = args.directory.resolve()
    stats = RunStats()

    if not args.skip_video:
        merge_stats(
            stats,
            run_videos(
                root,
                args.dry_run,
                delete_originals=args.delete,
                crf=args.crf,
                preset=args.preset,
            ),
        )

    if args.raw_to_jpeg:
        merge_stats(
            stats,
            run_raw_to_jpeg(
                root,
                args.dry_run,
                delete_originals=args.delete,
                jpeg_quality=args.jpeg_quality,
            ),
        )

    print_summary(stats, args.dry_run)

    return 1 if stats.errors else 0


if __name__ == "__main__":
    sys.exit(main())
