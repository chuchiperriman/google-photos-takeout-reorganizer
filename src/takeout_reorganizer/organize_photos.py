"""Ubica fotos en Fotos/AAAA/ y renombra delegando en rename_by_date."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from takeout_reorganizer.dates import is_year_directory_name, resolve_capture_datetime
from takeout_reorganizer.rename_by_date import (
    RunStats,
    cleanup_orphan_takeout_sidecars,
    collect_media_files,
    print_summary,
    process_file,
    remove_empty_directories,
)

logger = logging.getLogger(__name__)


def path_under_year_tree(path: Path, scan_root: Path) -> bool:
    try:
        relative = path.parent.relative_to(scan_root)
    except ValueError:
        return False
    return any(is_year_directory_name(part) for part in relative.parts)


def path_under_photos_year_tree(path: Path, photos_root: Path) -> bool:
    """El medio ya está bajo photos_root/AAAA/ (o subcarpeta de evento)."""
    try:
        relative = path.parent.relative_to(photos_root.resolve())
    except ValueError:
        return False
    if not relative.parts:
        return False
    return is_year_directory_name(relative.parts[0])


def resolve_target_directory(
    path: Path,
    scan_root: Path,
    photos_root: Path,
    year: int,
) -> Path | None:
    photos_root = photos_root.resolve()
    scan_root = scan_root.resolve()
    target = photos_root / str(year)

    if path_under_photos_year_tree(path, photos_root):
        return None

    # Mismo árbol: no reubicar lo que ya vive en .../AAAA/ bajo el escaneo.
    if photos_root == scan_root and path_under_year_tree(path, scan_root):
        return None

    return target


def run(
    scan_root: Path,
    photos_root: Path,
    dry_run: bool,
) -> RunStats:
    stats = RunStats()
    if not scan_root.is_dir():
        logger.error("No es un directorio: %s", scan_root)
        stats.errors += 1
        stats.error_messages.append(f"No es un directorio: {scan_root}")
        return stats

    photos_root = photos_root.resolve()
    scan_root = scan_root.resolve()

    for path in collect_media_files(scan_root):
        capture_dt, _ = resolve_capture_datetime(path)
        target_dir: Path | None = None
        if capture_dt is not None:
            target_dir = resolve_target_directory(
                path,
                scan_root,
                photos_root,
                capture_dt.year,
            )
        process_file(
            path,
            dry_run,
            stats,
            target_directory=target_dir,
            remove_takeout_sidecars_after=True,
        )

    cleanup_orphan_takeout_sidecars(scan_root, dry_run, stats)
    remove_empty_directories(scan_root, dry_run, stats)

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Organiza fotos y vídeos en Fotos/AAAA/ (volcados planos) y renombra "
            "según ORGANIZACION_FOTOS.md."
        ),
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directorio a escanear (p. ej. Takeout o Fotos)",
    )
    parser.add_argument(
        "--photos-root",
        type=Path,
        default=None,
        help="Raíz de la fototeca (por defecto: el mismo directorio)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostrar cambios sin modificar ficheros",
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

    photos_root = (args.photos_root or args.directory).resolve()
    scan_root = args.directory.resolve()

    if args.dry_run:
        logger.info("Modo simulación (--dry-run)")

    stats = run(scan_root, photos_root, args.dry_run)
    print_summary(stats, args.dry_run)

    return 1 if stats.errors else 0


if __name__ == "__main__":
    sys.exit(main())
