"""Renombra fotos y vídeos a yyyy-mm-dd-nombre.ext según fecha de toma."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from takeout_reorganizer.dates import (
    format_date_prefix,
    has_date_prefix,
    is_media_file,
    resolve_capture_date,
    sanitize_stem_for_rename,
    takeout_json_paths,
)

logger = logging.getLogger(__name__)


@dataclass
class RunStats:
    renamed: int = 0
    already_ok: int = 0
    skipped_no_date: int = 0
    errors: int = 0
    skipped_paths: list[Path] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)


def build_target_stem(capture_date, original_stem: str) -> str:
    base = sanitize_stem_for_rename(original_stem)
    prefix = format_date_prefix(capture_date)
    return f"{prefix}-{base}"


def unique_destination(directory: Path, stem: str, suffix: str) -> Path:
    candidate = directory / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = directory / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def rename_sidecars_after_media_rename(
    old_media_name: str,
    old_media_parent: Path,
    new_media: Path,
    dry_run: bool,
) -> None:
    old_media = old_media_parent / old_media_name
    for old_json in takeout_json_paths(old_media):
        if not old_json.is_file():
            continue
        extra = old_json.name[len(old_media_name) :]
        new_json = new_media.parent / (new_media.name + extra)
        if dry_run:
            logger.info("  sidecar: %s -> %s", old_json.name, new_json.name)
        else:
            old_json.rename(new_json)


def process_file(path: Path, dry_run: bool, stats: RunStats) -> None:
    if not is_media_file(path):
        return

    stem = path.stem
    if has_date_prefix(stem):
        stats.already_ok += 1
        logger.debug("Ya con prefijo de fecha: %s", path)
        return

    capture_date, source = resolve_capture_date(path)
    if capture_date is None:
        stats.skipped_no_date += 1
        stats.skipped_paths.append(path)
        logger.warning("Sin fecha de toma, omitido: %s", path)
        return

    target_stem = build_target_stem(capture_date, stem)
    dest = unique_destination(path.parent, target_stem, path.suffix)

    if dest.resolve() == path.resolve():
        stats.already_ok += 1
        return

    logger.info(
        "%s -> %s (fuente: %s)",
        path.name,
        dest.name,
        source,
    )

    old_name = path.name
    parent = path.parent

    if dry_run:
        stats.renamed += 1
        rename_sidecars_after_media_rename(old_name, parent, dest, dry_run=True)
        return

    try:
        path.rename(dest)
        rename_sidecars_after_media_rename(old_name, parent, dest, dry_run=False)
    except OSError as e:
        stats.errors += 1
        stats.error_messages.append(f"{path}: {e}")
        logger.error("Error al renombrar %s: %s", path, e)
        return

    stats.renamed += 1


def collect_media_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and is_media_file(path):
            files.append(path)
    return sorted(files)


def run(root: Path, dry_run: bool) -> RunStats:
    stats = RunStats()
    if not root.is_dir():
        logger.error("No es un directorio: %s", root)
        stats.errors += 1
        stats.error_messages.append(f"No es un directorio: {root}")
        return stats

    for path in collect_media_files(root):
        process_file(path, dry_run, stats)

    return stats


def print_summary(stats: RunStats, dry_run: bool) -> None:
    mode = " (simulación)" if dry_run else ""
    print(f"\n--- Resumen{mode} ---")
    print(f"Renombrados: {stats.renamed}")
    print(f"Ya correctos: {stats.already_ok}")
    print(f"Omitidos (sin fecha): {stats.skipped_no_date}")
    print(f"Errores: {stats.errors}")
    if stats.error_messages:
        for msg in stats.error_messages:
            print(f"  - {msg}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Renombra fotos y vídeos a yyyy-mm-dd-nombre.ext usando fecha de toma.",
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directorio raíz del Takeout (se recorre recursivamente)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostrar cambios sin renombrar ficheros",
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

    stats = run(args.directory.resolve(), args.dry_run)
    print_summary(stats, args.dry_run)

    return 1 if stats.errors else 0


if __name__ == "__main__":
    sys.exit(main())
