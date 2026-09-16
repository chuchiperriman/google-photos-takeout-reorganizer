#!/bin/sh
# Copia ficheros nuevos de $HOME/Fotos a Fotos/ en discos externos de backup.
# No borra ni sobrescribe nada en el destino.

set -eu

SOURCE="${HOME}/Fotos"
DEST_SUBDIR=Fotos

# Etiquetas de volumen (findmnt LABEL=...). Añade aquí otros discos de backup.
BACKUP_LABELS="
DatosLinux
PNY ELITE P
"

DRY_RUN=0
ONLY=""

usage() {
  echo "Uso: $0 [--dry-run|-n] [--only ETIQUETA]"
  echo
  echo "Sincroniza ~/Fotos con ${DEST_SUBDIR}/ en cada disco montado."
  echo "Solo copia ficheros que aún no existen en el destino (--ignore-existing)."
  echo "Si un disco no está conectado, se omite y se continúa con el resto."
  echo
  echo "Discos configurados:"
  printf '%s\n' "$BACKUP_LABELS" | sed '/^[[:space:]]*$/d' | sed 's/^/  - /'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run|-n) DRY_RUN=1 ;;
    --only)
      shift
      if [ $# -eq 0 ]; then
        echo "Falta la etiqueta tras --only." >&2
        exit 2
      fi
      ONLY=$1
      ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Opción desconocida: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
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

RSYNC_OPTS="-a --human-readable --info=progress2 --stats --ignore-existing --partial"
if [ "$DRY_RUN" -eq 1 ]; then
  RSYNC_OPTS="$RSYNC_OPTS --dry-run"
  echo "Modo simulación (--dry-run): no se escribirá nada en los discos."
  echo
fi

SYNCED=0
SKIPPED=0
FAILED=0

# shellcheck disable=SC2034
while IFS= read -r label || [ -n "$label" ]; do
  label=$(printf '%s' "$label" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  [ -z "$label" ] && continue

  if [ -n "$ONLY" ] && [ "$label" != "$ONLY" ]; then
    continue
  fi

  MOUNTPOINT=$(findmnt -S "LABEL=${label}" -no TARGET 2>/dev/null || true)
  if [ -z "$MOUNTPOINT" ]; then
    if [ -n "$ONLY" ]; then
      echo "El volumen «${label}» no está montado." >&2
      exit 1
    fi
    echo "«${label}»: no montado, omitido."
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  DEST="${MOUNTPOINT}/${DEST_SUBDIR}"
  mkdir -p "$DEST"

  echo "========== ${label} =========="
  echo "Origen:  ${SOURCE}/"
  echo "Destino: ${DEST}/"
  echo

  if rsync $RSYNC_OPTS "${SOURCE}/" "${DEST}/"; then
    SYNCED=$((SYNCED + 1))
  else
    echo "Error al sincronizar con «${label}»." >&2
    FAILED=$((FAILED + 1))
  fi
  echo
done <<EOF
$BACKUP_LABELS
EOF

if [ "$FAILED" -gt 0 ]; then
  exit 1
fi

if [ "$SYNCED" -eq 0 ]; then
  if [ -n "$ONLY" ]; then
    exit 1
  fi
  echo "Ningún disco de backup estaba montado; no se copió nada." >&2
  exit 1
fi

if [ "$SKIPPED" -gt 0 ]; then
  echo "Listo. Sincronizado en ${SYNCED} volumen(es); ${SKIPPED} omitido(s) (no montados)."
else
  echo "Listo. Sincronizado en ${SYNCED} volumen(es)."
fi
