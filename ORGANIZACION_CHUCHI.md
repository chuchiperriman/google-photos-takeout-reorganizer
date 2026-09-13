# Organización mía personal

## Estructura

La estructura de directorios para las fotos es la que se describe en
[la guía de organización y nomenclatura de fotos](ORGANIZACION_FOTOS.md).

## Descarga anual de fotos de Google Photos con Google Takeout

* Generamos el backup en Google Takeout
* Descargamos el takeout por ejemplo en /tmp/takeout
* Primero ejecutaremos https://github.com/Xentraxx/GooglePhotosTakeoutHelper_Neo para que nos mezcle los datos json con los metadatos de los ficheros.
* Luego ejecutaremos el reorganizador para que nos renombre y coloque los ficheros como dice nuestra guía:

      python3 src/takeout_reorganizer/organize_photos.py /tmp/takeout/resultado-gpth

* Cuando tengamos todos los ficheros organizados por año bien los copiamos en el SSD en la carpeta Fotos

