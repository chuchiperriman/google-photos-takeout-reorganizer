"""Renombra fotos y vídeos a AAAA-MM-DD_HHMMSS[_descripcion].ext según fecha de toma."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from takeout_reorganizer.dates import (
    format_organizacion_stem,
    has_organizacion_name,
    is_media_file,
    is_takeout_media_sidecar,
    media_path_for_takeout_sidecar,
    resolve_capture_datetime,
    sanitize_description,
    sanitize_stem_for_rename,
    takeout_json_paths,
)

logger = logging.getLogger(__name__)


@dataclass
class RunStats:
    renamed: int = 0
    already_ok: int = 0
    skipped_no_date: int = 0
    sidecars_removed: int = 0
    empty_dirs_removed: int = 0
    errors: int = 0
    skipped_paths: list[Path] = field(default_factory=list)
    error_messages: list[str] = field(default_factory=list)


def build_target_stem(capture_dt: datetime, original_stem: str) -> str:
    description = sanitize_description(sanitize_stem_for_rename(original_stem))
    return format_organizacion_stem(capture_dt, description)


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


def remove_takeout_sidecars(
    media_path: Path,
    dry_run: bool,
    stats: RunStats,
) -> None:
    for json_path in takeout_json_paths(media_path):
        if not json_path.is_file():
            continue
        if dry_run:
            logger.info("  sidecar: borrar %s", json_path)
        else:
            try:
                json_path.unlink()
            except OSError as e:
                stats.errors += 1
                stats.error_messages.append(f"{json_path}: {e}")
                logger.error("Error al borrar sidecar %s: %s", json_path, e)
                continue
        stats.sidecars_removed += 1


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


def handle_takeout_sidecars_after_media(
    old_media_name: str,
    old_media_parent: Path,
    new_media: Path,
    dry_run: bool,
    stats: RunStats,
    remove_sidecars: bool,
) -> None:
    if remove_sidecars:
        remove_takeout_sidecars(old_media_parent / old_media_name, dry_run, stats)
        return
    rename_sidecars_after_media_rename(
        old_media_name, old_media_parent, new_media, dry_run
    )


def cleanup_orphan_takeout_sidecars(
    root: Path,
    dry_run: bool,
    stats: RunStats,
) -> None:
    """Borra JSON de Takeout cuyo medio ya no está en la misma carpeta (p. ej. tras un move)."""
    for path in root.rglob("*"):
        if not path.is_file() or not is_takeout_media_sidecar(path):
            continue
        media = media_path_for_takeout_sidecar(path)
        if media is not None and media.is_file():
            continue
        if dry_run:
            logger.info("  sidecar huérfano: borrar %s", path)
        else:
            try:
                path.unlink()
            except OSError as e:
                stats.errors += 1
                stats.error_messages.append(f"{path}: {e}")
                logger.error("Error al borrar sidecar %s: %s", path, e)
                continue
        stats.sidecars_removed += 1


def remove_empty_directories(
    root: Path,
    dry_run: bool,
    stats: RunStats,
) -> None:
    """Elimina subdirectorios vacíos bajo root (de hoja a raíz); no borra root."""
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        current = Path(dirpath)
        if current == root:
            continue
        if dirnames or filenames:
            continue
        if dry_run:
            logger.info("  directorio vacío: borrar %s", current)
        else:
            try:
                current.rmdir()
            except OSError as e:
                stats.errors += 1
                stats.error_messages.append(f"{current}: {e}")
                logger.error("Error al borrar directorio %s: %s", current, e)
                continue
        stats.empty_dirs_removed += 1


def process_file(
    path: Path,
    dry_run: bool,
    stats: RunStats,
    target_directory: Path | None = None,
    remove_takeout_sidecars_after: bool = False,
) -> None:
    if not is_media_file(path):
        return

    stem = path.stem
    if has_organizacion_name(stem):
        stats.already_ok += 1
        logger.debug("Ya con nombre conforme: %s", path)
        if remove_takeout_sidecars_after:
            remove_takeout_sidecars(path, dry_run, stats)
        return

    capture_dt, source = resolve_capture_datetime(path)
    if capture_dt is None:
        stats.skipped_no_date += 1
        stats.skipped_paths.append(path)
        logger.warning("Sin fecha de toma, omitido: %s", path)
        return

    target_stem = build_target_stem(capture_dt, stem)
    dest_dir = target_directory if target_directory is not None else path.parent
    dest = unique_destination(dest_dir, target_stem, path.suffix)

    if dest.resolve() == path.resolve():
        stats.already_ok += 1
        if remove_takeout_sidecars_after:
            remove_takeout_sidecars(path, dry_run, stats)
        return

    if target_directory is not None and dest_dir != path.parent:
        logger.info(
            "%s -> %s/%s (fuente: %s)",
            path.name,
            dest_dir,
            dest.name,
            source,
        )
    else:
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
        handle_takeout_sidecars_after_media(
            old_name,
            parent,
            dest,
            dry_run=True,
            stats=stats,
            remove_sidecars=remove_takeout_sidecars_after,
        )
        return

    try:
        if target_directory is not None:
            dest_dir.mkdir(parents=True, exist_ok=True)
        path.rename(dest)
        handle_takeout_sidecars_after_media(
            old_name,
            parent,
            dest,
            dry_run=False,
            stats=stats,
            remove_sidecars=remove_takeout_sidecars_after,
        )
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
    if stats.sidecars_removed:
        print(f"JSON Takeout eliminados: {stats.sidecars_removed}")
    if stats.empty_dirs_removed:
        print(f"Directorios vacíos eliminados: {stats.empty_dirs_removed}")
    print(f"Errores: {stats.errors}")
    if stats.error_messages:
        for msg in stats.error_messages:
            print(f"  - {msg}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Renombra fotos y vídeos a AAAA-MM-DD_HHMMSS[_descripcion].ext "
            "usando fecha y hora de toma."
        ),
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
