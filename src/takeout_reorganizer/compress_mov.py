"""Comprime vídeos .MOV y .AVI a .mp4 (H.264 + AAC) con ffmpeg."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SOURCE_EXTENSIONS = {".mov", ".avi"}
DEFAULT_CRF = 23
DEFAULT_PRESET = "medium"
DEFAULT_AUDIO_BITRATE = "128k"


@dataclass
class RunStats:
    converted: int = 0
    skipped_exists: int = 0
    deleted: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)


def collect_source_videos(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS:
            files.append(path)
    return sorted(files)


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def copy_file_times(src: Path, dest: Path) -> None:
    src_stat = src.stat()
    os.utime(dest, (src_stat.st_atime, src_stat.st_mtime))


def compress_one(
    src: Path,
    dest: Path,
    *,
    crf: int,
    preset: str,
    audio_bitrate: str,
) -> None:
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
    subprocess.run(cmd, check=True)


def run(
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
            stats.converted += 1
            if delete_originals:
                logger.info("  se eliminaría el original: %s", src)
            continue

        try:
            compress_one(
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

        try:
            copy_file_times(src, dest)
        except OSError as e:
            logger.warning("No se pudo copiar la fecha de %s: %s", src, e)

        stats.converted += 1
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
    print(f"Convertidos: {stats.converted}")
    print(f"Saltados (mp4 ya existe): {stats.skipped_exists}")
    if stats.deleted:
        print(f"Originales eliminados: {stats.deleted}")
    print(f"Errores: {stats.errors}")
    if stats.error_messages:
        for msg in stats.error_messages:
            print(f"  - {msg}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Comprime vídeos .MOV y .AVI a .mp4 (H.264 + AAC) con ffmpeg.",
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
        help="Borrar el original (.MOV / .AVI) tras una conversión correcta",
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
        "-v",
        "--verbose",
        action="store_true",
        help="Más detalle en el log",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if args.dry_run:
        logger.info("Modo simulación (--dry-run)")

    stats = run(
        args.directory.resolve(),
        args.dry_run,
        delete_originals=args.delete,
        crf=args.crf,
        preset=args.preset,
    )
    print_summary(stats, args.dry_run)

    return 1 if stats.errors else 0


if __name__ == "__main__":
    sys.exit(main())
