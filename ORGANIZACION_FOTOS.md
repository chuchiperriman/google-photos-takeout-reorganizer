# Guía de Organización y Nomenclatura de Fotos Digitales

Esta guía define la estructura lógica, las convenciones de nomenclatura y las buenas prácticas para organizar una colección fotográfica personal a largo plazo (2005–Presente).

---

## 1. Principios Basicos

1. **Estabilidad y Portabilidad:** La estructura debe ser comprensible y legible por cualquier sistema operativo (Windows, macOS, Linux, NAS) sin depender de software propietario.
2. **Criterio Estándar ISO 8601:** Las fechas siempre siguen el formato `AAAA-MM-DD` (Año-Mes-Día) para garantizar que los archivos y carpetas se ordenen cronológicamente de forma automática.
3. **Limpieza de Caracteres:** Evitar espacios, tildes, símbolos (`?`, `!`, `&`, `%`) y la letra `ñ`. En su lugar, utilizar guiones bajos (`_`) como separadores de campos y guiones medios (`-`) para subpalabras o fechas.

---

## 2. Estructura de Directorios (Modelo Híbrido)

La fototeca se organiza por **Año**, con carpetas de evento opcionales para agrupaciones con muchas fotos. Las fotos cotidianas o sueltas viven **directamente en la carpeta del año**, sin subcarpeta mensual.

```text
Fotos/
├── 2005/
│   ├── 2005-08-12_184510_torre_eiffel.jpg
│   ├── 2005-08-12_190022.jpg
│   └── 2005-08_Viaje_Paris/
│       └── ...
├── 2015/
│   ├── 2015-05-02_131500.jpg
│   ├── 2015-05_Boda_Carlos/
│   └── 2015-08_Vacaciones_Asturias/
└── 2024/
    ├── 2024-03-15_101530.jpg
    ├── 2024-07_Vacaciones_Menorca/
    └── 2024-12_Navidades/
```

### Reglas de Carpetas

* **Carpeta Raíz del Año:** 4 dígitos (`AAAA`). Aquí se guardan las fotos y vídeos sueltos de ese año (capturas cotidianas, pocos archivos de un mes, etc.).
* **Carpetas de Eventos:** `AAAA/AAAA-MM_NombreEvento`
  * Se crean únicamente para viajes, celebraciones, escapadas o proyectos con un número representativo de fotos.
  * *Evita crear subcarpetas por día para 1 o 2 fotos; esos archivos pueden quedarse en la raíz del año.*

---

## 3. Nomenclatura de Archivos

Cada archivo de imagen o vídeo debe renombrarse incorporando la fecha y hora exacta extraída de los metadatos EXIF. Esto evita colisiones de nombres (ej. `IMG_0001.JPG`) y conserva el orden si la foto se extrae de su carpeta.

### Formato Estándar
`AAAA-MM-DD_HHMMSS_DescripcionCorta.ext`

### Componentes

| Componente | Formato | Ejemplo | Descripción |
| :--- | :--- | :--- | :--- |
| **Fecha** | `AAAA-MM-DD` | `2024-07-15` | Año, mes y día de captura. |
| **Hora** | `HHMMSS` | `143022` | Hora, minuto y segundo (evita duplicados en ráfagas). |
| **Descripción** *(Opcional)* | `Texto_Breve` | `playa_cala_macarella` | Breve contexto en minúsculas (sin espacios). |

### Ejemplos de Archivos

* `2005-08-12_184510_torre_eiffel.jpg`
* `2015-05-02_131500.jpg` *(Sin descripción si el contexto lo da la carpeta)*
* `2024-07-20_210533_atardecer.mov`

---

## 4. Reglas de Mantenimiento y Buenas Prácticas

1. **Evitar la Profundidad Excesiva:** No crees subcarpetas dentro de los eventos (ej. `/2024/2024-07_Menorca/Dia1/Fotos/`). Mantén todos los archivos del evento en el mismo nivel.
2. **Archivos RAW + JPG:** Si utilizas cámara DSLR/mirrorless, mantén los pares de archivos (`.CR2`/`.NEF` + `.JPG`) con el mismo nombre en la misma carpeta, o crea una subcarpeta interna llamada únicamente `RAW/`.
3. **Manejo de Vídeos:** Guarda los vídeos grabados con la cámara o móvil en la misma carpeta que las fotos correspondientes, utilizando la misma regla de nomenclatura.
4. **Automatización:** Se recomienda utilizar herramientas en lote para el renombra masivo basándose en metadatos EXIF:
   * **Gratuitas/Open Source:** *DigiKam*, *ExifTool*, *Advanced Renamer*.
   * **Visores/Organizadores:** *Adobe Lightroom*, *Immich* (para servidores/NAS), *FastStone Image Viewer*.

---

## 5. Estrategia de Copias de Seguridad (Regla 3-2-1)

* **3 Copias del contenido:** 1 primaria + 2 copias de respaldo.
* **2 Medios distintos:** Ej. Disco SSD externo + Servidor NAS / Disco duro interno.
* **1 Copia fuera de la ubicación principal (Offsite):** Almacenamiento en la nube (Backblaze, Google Drive, Proton Drive) o un disco duro en casa de un familiar.
