# Google Photos Takeout Reorganizer

Scripts en Python para modificar y reorganizar fotos y vídeos exportados con [Google Takeout](https://takeout.google.com/).

## Requisitos

- Python 3.11 o superior

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -e .
```

## Scripts

### `rename-by-date`

Recorre de forma **recursiva** un directorio de Takeout y renombra imágenes y vídeos al formato:

`yyyy-mm-dd-nombrefichero.extensión`

La fecha se obtiene en este orden:

1. Metadatos del fichero (EXIF en fotos; etiquetas de creación en vídeos)
2. JSON de Takeout junto al archivo (`*.json` o `*.supplemental-metadata.json`)
3. Fecha presente en el nombre del archivo (p. ej. `PXL_20200315_…`, `IMG_20200101_…`, `WhatsApp Image 2020-01-01 …`)
4. Si no hay fecha: el archivo **no se renombra** y se registra un aviso

Los JSON sidecar se renomban junto al medio para mantener la asociación.

**Uso:**

```bash
rename-by-date /ruta/al/takeout
rename-by-date /ruta/al/takeout --dry-run
rename-by-date /ruta/al/takeout -v
```

- `--dry-run`: muestra qué cambios se harían sin modificar ficheros.
- `-v` / `--verbose`: más detalle en el log.

**Comportamiento adicional:**

- Si el nombre ya empieza por `yyyy-mm-dd-`, no se vuelve a prefijar.
- Al renombrar, se eliminan del nombre original otras fechas en formato `yyyy-mm-dd` o `yyyymmdd` (p. ej. `IMG_20210601_120000` → `2021-06-01-IMG_120000`).
- Si el nombre destino ya existe, se añade `-2`, `-3`, etc.
- Extensiones tratadas: `jpg`, `jpeg`, `png`, `heic`, `webp`, `gif`, `tif`, `tiff`, `mp4`, `mov`, `m4v`, `3gp`, `avi`, `mkv`.

## Limitaciones (primer script)

- No modifica metadatos EXIF; solo renombra en disco.
- La fecha de vídeo depende de lo que exporte el contenedor; no todos los archivos incluyen fecha de creación.
- Archivos sin fecha en metadatos, JSON ni nombre quedan sin cambiar.

## Desarrollo

El paquete vive en `src/takeout_reorganizer/`.
