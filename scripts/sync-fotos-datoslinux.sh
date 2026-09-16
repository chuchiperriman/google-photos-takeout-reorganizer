#!/bin/sh
# Copia ficheros nuevos de $HOME/Fotos a DatosLinux/Fotos.
# No borra ni sobrescribe nada en el disco externo.

set -eu

SOURCE="${HOME}/Fotos"
DISK_LABEL=DatosLinux
DEST_SUBDIR=Fotos

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) DRY_RUN=1 ;;
    -h|--help)
      echo "Uso: $0 [--dry-run|-n]"
      echo "Copia solo ficheros que aún no existen en ${DISK_LABEL}/${DEST_SUBDIR}."
      exit 0
      ;;
    *)
      echo "Opción desconocida: $arg" >&2
      exit 2
      ;;
  esac
done

if ! command -v rsync >/dev/null 2>&1; then
  echo "No se encuentra rsync en el PATH." >&2
  exit 1
fi

if ! command -v findmnt >/dev/null 2>&1; then
  echo "No se encuentra findmnt (util-linux)." >&2
  exit 1
fi

if [ ! -d "$SOURCE" ]; then
  echo "No existe el directorio origen: $SOURCE" >&2
  exit 1
fi

MOUNTPOINT=$(findmnt -S "LABEL=${DISK_LABEL}" -no TARGET 2>/dev/null || true)
if [ -z "$MOUNTPOINT" ]; then
  echo "El volumen ${DISK_LABEL} no está montado." >&2
  echo "Conecta el disco y vuelve a intentarlo." >&2
  exit 1
fi

DEST="${MOUNTPOINT}/${DEST_SUBDIR}"
mkdir -p "$DEST"

RSYNC_OPTS="-a --human-readable --info=progress2 --stats --ignore-existing --partial"
if [ "$DRY_RUN" -eq 1 ]; then
  RSYNC_OPTS="$RSYNC_OPTS --dry-run"
  echo "Modo simulación (--dry-run): no se escribirá nada en el disco."
fi

echo "Origen:  $SOURCE/"
echo "Destino: $DEST/"
echo

# shellcheck disable=SC2086
rsync $RSYNC_OPTS "$SOURCE/" "$DEST/"
