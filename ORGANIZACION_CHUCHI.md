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

# Copias de seguridad

Mantener varias copias de seguridad:

* En el PC principal
* En el HDD externo gris
* En el SSD externo PNY

Para sincronizarlos, podemos meter las fotos nuevas en el PC y luego lanzar nu rsync para sincronizar el PC con los discos externos

    TODO: Pendientes de crear un script de sincronización

