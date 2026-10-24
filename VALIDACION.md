# Validación de la entrega · 24 de octubre de 2026

- **7 pruebas automáticas aprobadas** (`python -m unittest discover -s tests -v`). Incluyen codificación MP3 real con FFmpeg, etiquetas ID3, bitrate, persistencia SQLite, respuesta HTTP parcial para reproducción, errores de conexión, selección caducada, autenticación, cancelación, recuperación tras interrupción y QR.
- Comprobación de sintaxis de JavaScript y compilación de los archivos Python: aprobadas.
- Búsqueda real de artista en YouTube: 20 resultados visibles, con nombres, artistas y casillas de selección. Se comprobó selección múltiple.
- Búsqueda real por género en SoundCloud: 20 resultados visibles.
- Descarga real en la interfaz desde YouTube: grabación histórica «Scott Joplin - Original Rags (1916)», completada a MP3 de 192 kbps y disponible en biblioteca.
- Descarga y conversión por enlace directo del tráiler público Sintel de W3C: completada, 51,96 segundos, 192 kbps. Una solicitud posterior recibió un bloqueo 403 de Cloudflare; se conserva este límite de disponibilidad de las plataformas, sin intentar eludirlo.
- **Prueba del ejecutable compilado**: arranque, autenticación, página web, comprobación de Internet, motores FFmpeg y Node incluidos, búsqueda y descarga real desde YouTube a MP3 de 320 kbps, duración de 197 segundos, respuesta HTTP Range y cierre limpio. Se eliminó Python y Node del PATH del proceso para comprobar que utiliza los motores incluidos.
- La dirección IPv4 de red local respondió correctamente al servidor del ejecutable. No se conectó un teléfono físico durante la validación.
- Interfaz revisada en navegador a 1440 × 1050 y 390 × 844. Sin desbordamiento horizontal. QR visible y sin errores de JavaScript observados.
- Compilación PyInstaller para Windows x64 y ZIP portable completados. No se ha probado en otro computador ni se ha firmado digitalmente el ejecutable.

Capturas: `artifacts/tutuy-escritorio.jpg` y `artifacts/tutuy-movil.jpg`.

Los archivos de prueba se mantienen fuera del paquete portable, en `.test-data/`. El ZIP para el usuario no contiene claves de conexión, historial ni música de prueba. La aplicación crea su carpeta `data/` al abrirla por primera vez.

## Preparación del repositorio para Vercel

Se añadió una compilación de la interfaz estática, avisos cuando falta la API y documentación del backend persistente necesario. Una prueba adicional verifica que un origen HTTPS configurado puede conectarse y que no obtiene permisos de escritorio a través de un proxy. La suite pasa ahora 8 pruebas. No se ha desplegado el proyecto en Vercel ni se ha validado un backend alojado externo.
