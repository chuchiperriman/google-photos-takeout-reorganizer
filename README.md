# Google Photos Takeout Reorganizer

¡¡¡¡EN DESARROLLO!!!!

Scripts en Python para modificar y reorganizar fotos y vídeos exportados con [Google Takeout](https://takeout.google.com/), siguiendo la guía [ORGANIZACION_FOTOS.md](ORGANIZACION_FOTOS.md).

## Requisitos

- Python 3.11 o superior
- [ffmpeg](https://ffmpeg.org/) en el PATH (vídeos en `compress-mov`)
- [LibRaw](https://www.libraw.org/) en el sistema para exportar RAW con `--raw-to-jpeg` (p. ej. en Debian/Ubuntu: `libraw-dev`)

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -e .
```

## Scripts

### `rename-by-date`

Recorre de forma **recursiva** un directorio y renombra imágenes y vídeos al formato:

`AAAA-MM-DD_HHMMSS[_descripcion].ext`

La fecha y hora se obtienen en este orden:

1. Metadatos del fichero (EXIF en fotos; etiquetas de creación en vídeos)
2. JSON de Takeout junto al archivo (`*.json` o `*.supplemental-metadata.json`)
3. Fecha u hora presentes en el nombre del archivo (p. ej. `PXL_20200315_…`, `IMG_20200101_120000`)
4. Carpetas en la ruta: `.../yyyy/mm/dd/` o `.../yyyy/mm/` (día 1 si solo hay año y mes)
5. Año en el nombre de la carpeta contenedora (p. ej. `Photos from 2013`)
6. Si no hay fecha: el archivo **no se renombra** y se registra un aviso (salvo con `--fallback-oldest-date`; ver abajo)

Si solo hay fecha (sin hora) en la fuente, se usa `000000` como hora.

Los JSON sidecar de Takeout se renomban junto al medio para mantener la asociación (solo en este paso).

**Uso:**

```bash
rename-by-date /ruta/al/takeout
rename-by-date /ruta/al/takeout --dry-run
rename-by-date /ruta/al/takeout -v
```

- `--dry-run`: muestra qué cambios se harían sin modificar ficheros.
- `--fallback-oldest-date`: si el orden habitual no da fecha de toma, renombra usando la **más antigua** entre todas las fechas detectables (EXIF, JSON Takeout, nombre, carpetas, `mtime`/`ctime`/`atime`/creación del fichero). En el log la fuente aparece como `oldest-…`.
- `-v` / `--verbose`: más detalle en el log.

**Comportamiento adicional:**

- Si el nombre ya cumple `AAAA-MM-DD_HHMMSS[_descripcion]`, no se vuelve a renombrar.
- Los nombres antiguos `yyyy-mm-dd-...` se migran al formato nuevo usando metadatos.
- Al renombrar, se limpian del nombre original fechas y horas redundantes.
- Si el nombre destino ya existe, se añade `-2`, `-3`, etc.
- Extensiones tratadas: imágenes (`jpg`, `jpeg`, `png`, `heic`, `webp`, `gif`, `tif`, `tiff`, RAW `cr2`, `cr3`, `nef`, `arw`, `dng`, …), vídeo (`mp4`, `mov`, `m4v`, `mpg`, `mpeg`, `mts`, `m2ts`, `3gp`, `avi`, `mkv`, `mp` Motion Photo de Pixel).

### `organize-photos`

Combina **renombrado** (misma lógica que `rename-by-date`) con **ubicación** en la fototeca:

- Volcados **planos** (sin carpeta de año `AAAA` en la ruta): mueve cada medio a `{photos-root}/{AAAA}/`.
- Archivos ya bajo `.../AAAA/` o `.../AAAA/AAAA-MM_Evento/`: solo renombra, sin cambiar de carpeta.
- **Elimina** los JSON de Takeout (`*.json`, `*.supplemental-metadata.json`) asociados a cada medio procesado; no se copian a la fototeca. Al final borra sidecars huérfanos en el directorio escaneado (p. ej. tras mover el archivo).
- **Elimina** subcarpetas que queden completamente vacías bajo el directorio escaneado (p. ej. álbumes de Takeout ya vacíos).

**Uso:**

```bash
organize-photos /ruta/al/takeout --photos-root /ruta/Fotos
organize-photos /ruta/Fotos --dry-run
organize-photos /ruta/al/takeout -v
```

- `--photos-root`: raíz de la fototeca (por defecto, el mismo directorio que se escanea). Si es distinto del directorio escaneado, todo lo que no esté ya bajo `destino/AAAA/` se mueve allí (también si en el origen había carpetas `AAAA/`).
- `--dry-run`, `--fallback-oldest-date`, `-v`: igual que en `rename-by-date`.

No crea carpetas de evento automáticamente.

### `compress-mov`

Recorre de forma **recursiva** un directorio:

- Por defecto convierte cada `.MOV` / `.AVI` a `.mp4` (H.264 + AAC) junto al original.
- Con `--raw-to-jpeg` exporta RAW (`.ARW`, `.CR2`, `.NEF`, `.DNG`, …; misma lista que en `rename-by-date`) a `.jpg` con balance de blancos de cámara.

Deja el fichero de origen intacto salvo que pidas `--delete`.

**Uso:**

```bash
compress-mov /ruta/Fotos
compress-mov /ruta/Fotos --dry-run
compress-mov /ruta/Fotos --delete --crf 23
compress-mov /ruta/Fotos --raw-to-jpeg --dry-run
compress-mov /ruta/Fotos --raw-to-jpeg --skip-video
compress-mov /ruta/Fotos -v
```

- `--dry-run`: muestra qué se convertiría sin tocar ficheros.
- `--delete`: borra el original solo si la conversión termina sin errores. En vídeo, si ffmpeg muestra errores de decodificación, se conserva el `.MOV`/`.AVI` y el `.mp4`.
- `--raw-to-jpeg`: exporta RAW a `.jpg` (salta si ya hay `.jpg`/`.jpeg` con el mismo nombre).
- `--skip-video`: no comprime vídeos (solo tiene sentido junto a `--raw-to-jpeg`).
- `--crf`: calidad x264 (18 más calidad/peso, 28 más pequeño; por defecto `23`).
- `--preset`: velocidad/compresión x264 (`ultrafast`…`veryslow`; por defecto `medium`).
- `--jpeg-quality`: calidad al exportar RAW (1–100; por defecto `92`).
- `-v` / `--verbose`: más detalle en el log.

Si ya existe el fichero destino (`.mp4` o `.jpg`), se salta. Copia la fecha de modificación del fichero. No forma parte de `organize-photos`: conviene usarlo sobre la fototeca cuando quieras reducir peso o generar JPEG desde RAW.

## Limitaciones

- No modifica metadatos EXIF en renombrado; `rename-by-date` y `organize-photos` solo renombran y mueven en disco. `compress-mov` reencodea vídeo con ffmpeg y exporta RAW a JPEG sin copiar EXIF al JPEG (la fecha de fichero sí se conserva).
- La fecha de vídeo depende de lo que exporte el contenedor; no todos los archivos incluyen fecha de creación.
- Archivos sin fecha en metadatos, JSON ni nombre quedan sin cambiar (o se usa `--fallback-oldest-date`).
- Las fechas **anteriores a 1980** o **posteriores a hoy** se descartan (p. ej. `1970` en EXIF o relojes mal configurados).

## Desarrollo

El paquete vive en `src/takeout_reorganizer/`.

## Pasos a seguir para un correcto backup

1. Descargar el backup desde Google Takeout.
2. Usar [GooglePhotosTakeoutHelper_Neo](https://github.com/Xentraxx/GooglePhotosTakeoutHelper_Neo) para colocar ficheros y corregir EXIF.
3. Renombrar y organizar en la fototeca:

   ```bash
   organize-photos ~/Descargas/takeout-... --photos-root /ruta/Fotos --dry-run
   organize-photos ~/Descargas/takeout-... --photos-root /ruta/Fotos
   ```

   O solo renombrar in situ:

   ```bash
   rename-by-date ~/Descargas/takeout-...
   ```

4. (Opcional) Comprimir `.MOV` y `.AVI` a `.mp4` en la fototeca:

   ```bash
   compress-mov /ruta/Fotos --dry-run
   compress-mov /ruta/Fotos
   ```

5. Copiar `Fotos/` al disco de backup.
