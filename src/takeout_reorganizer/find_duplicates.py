"""Detecta archivos con contenido idéntico dentro de la misma carpeta (hash SHA-256)."""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024


@dataclass
class DuplicateGroup:
    directory: Path
    digest: str
    size: int
    paths: list[Path]


@dataclass
class RunStats:
    directories_scanned: int = 0
    files_hashed: int = 0
    duplicate_groups: list[DuplicateGroup] = field(default_factory=list)
    deleted: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def files_in_directory(directory: Path) -> list[Path]:
    files: list[Path] = []
    try:
        entries = list(directory.iterdir())
    except OSError as e:
        raise OSError(f"{directory}: {e}") from e
    for entry in entries:
        if entry.is_file():
            files.append(entry)
    return sorted(files)


def find_duplicates_in_directory(directory: Path, stats: RunStats) -> list[DuplicateGroup]:
    files = files_in_directory(directory)
    if len(files) < 2:
        return []

    by_size: dict[int, list[Path]] = defaultdict(list)
    for path in files:
        try:
            size = path.stat().st_size
        except OSError as e:
            stats.errors += 1
            stats.error_messages.append(f"{path}: {e}")
            logger.error("No se pudo leer tamaño de %s: %s", path, e)
            continue
        by_size[size].append(path)

    groups: list[DuplicateGroup] = []
    for size, candidates in by_size.items():
        if len(candidates) < 2:
            continue
        by_digest: dict[str, list[Path]] = defaultdict(list)
        for path in candidates:
            try:
                digest = sha256_file(path)
            except OSError as e:
                stats.errors += 1
                stats.error_messages.append(f"{path}: {e}")
                logger.error("No se pudo hashear %s: %s", path, e)
                continue
            stats.files_hashed += 1
            by_digest[digest].append(path)
        for digest, paths in by_digest.items():
            if len(paths) >= 2:
                groups.append(
                    DuplicateGroup(
                        directory=directory,
                        digest=digest,
                        size=size,
                        paths=sorted(paths),
                    )
                )
    return groups


def iter_directories(root: Path) -> list[Path]:
    root = root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    dirs = [root]
    dirs.extend(path for path in sorted(root.rglob("*")) if path.is_dir())
    return dirs


def path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return float("inf")


def choose_keeper(paths: list[Path]) -> Path:
    """Fichero a conservar: mtime más antigua; empate por nombre."""
    return min(paths, key=lambda p: (path_mtime(p), p.name.lower()))


def remove_duplicate_copies(
    groups: list[DuplicateGroup],
    stats: RunStats,
    *,
    dry_run: bool,
) -> None:
    for group in groups:
        keeper = choose_keeper(group.paths)
        for path in group.paths:
            if path == keeper:
                continue
            if dry_run:
                logger.info("  borrar %s (conservar %s)", path.name, keeper.name)
                stats.deleted += 1
                continue
            try:
                path.unlink()
            except OSError as e:
                stats.errors += 1
                stats.error_messages.append(f"{path}: {e}")
                logger.error("No se pudo borrar %s: %s", path, e)
                continue
            stats.deleted += 1
            logger.info("Borrado %s (conservado %s)", path, keeper)


def run(root: Path) -> RunStats:
    stats = RunStats()
    root = root.resolve()
    try:
        directories = iter_directories(root)
    except (NotADirectoryError, OSError) as e:
        stats.errors += 1
        stats.error_messages.append(str(e))
        logger.error("%s", e)
        return stats

    for directory in directories:
        stats.directories_scanned += 1
        try:
            label = directory.relative_to(root)
        except ValueError:
            label = directory
        print(f"Escaneando: {label}", flush=True)
        try:
            groups = find_duplicates_in_directory(directory, stats)
        except OSError as e:
            stats.errors += 1
            stats.error_messages.append(str(e))
            logger.error("%s", e)
            continue
        stats.duplicate_groups.extend(groups)

    return stats


def print_report(
    stats: RunStats,
    *,
    show_deletion_plan: bool,
) -> None:
    total_dup_files = sum(len(g.paths) for g in stats.duplicate_groups)
    extra_copies = sum(len(g.paths) - 1 for g in stats.duplicate_groups)

    if not stats.duplicate_groups:
        print("No se encontraron duplicados (mismo contenido en la misma carpeta).")
    else:
        print(
            f"Grupos de duplicados: {len(stats.duplicate_groups)} "
            f"({total_dup_files} ficheros, {extra_copies} copias de más)."
        )
        for i, group in enumerate(stats.duplicate_groups, start=1):
            print()
            print(f"[{i}] {group.directory}")
            print(f"    SHA-256: {group.digest}")
            print(f"    Tamaño:  {group.size} bytes")
            keeper = choose_keeper(group.paths)
            for path in sorted(group.paths, key=lambda p: p.name.lower()):
                if show_deletion_plan and path == keeper:
                    print(f"    - {path.name} (conservar)")
                elif show_deletion_plan:
                    print(f"    - {path.name} (borrar)")
                else:
                    print(f"    - {path.name}")

    print()
    print(
        f"Carpetas analizadas: {stats.directories_scanned}; "
        f"ficheros hasheados: {stats.files_hashed}."
    )
    if stats.errors:
        print(f"Errores: {stats.errors}")
        for msg in stats.error_messages:
            print(f"  - {msg}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Busca archivos con contenido idéntico dentro de la misma carpeta "
            "(comparación por SHA-256). Recorre el árbol de subcarpetas: en cada "
            "directorio solo compara ficheros de ese nivel."
        ),
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directorio raíz a analizar (recursivo)",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help=(
            "Borrar copias duplicadas en cada grupo (conserva el fichero con la "
            "fecha de modificación más antigua)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Con --delete, mostrar qué se borraría sin eliminar ficheros",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Más detalle en el log",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO if args.delete else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    if args.dry_run:
        logger.info("Modo simulación (--dry-run)")

    stats = run(args.directory.resolve())
    print()
    print_report(stats, show_deletion_plan=args.delete)

    if args.delete and stats.duplicate_groups:
        remove_duplicate_copies(stats.duplicate_groups, stats, dry_run=args.dry_run)
        if stats.deleted:
            if args.dry_run:
                print(f"Ficheros que se borrarían: {stats.deleted}.")
            else:
                print(f"Ficheros borrados: {stats.deleted}.")

    if stats.errors:
        return 2
    if stats.duplicate_groups and not (args.delete and not args.dry_run):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
