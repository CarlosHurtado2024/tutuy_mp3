# Componentes de terceros

Tutuy MP3 incluye software independiente de terceros; no está afiliado a las plataformas consultadas.

- **yt-dlp**: Unlicense; componentes adicionales de sus dependencias tienen sus propias licencias. https://github.com/yt-dlp/yt-dlp
- **yt-dlp-ejs**: scripts de resolución y sus avisos de terceros, incluidos en la distribución. https://github.com/yt-dlp/ejs
- **FFmpeg**: el binario distribuido por imageio-ffmpeg puede incluir componentes GPL. Conserva los avisos y consulta su compilación con `ffmpeg -L` y `ffmpeg -buildconf`. Código y versiones: https://ffmpeg.org/download.html y https://github.com/imageio/imageio-ffmpeg . Se ejecuta como proceso separado.
- **Node.js**: MIT y avisos de componentes adicionales, copiados como `Licencias/NODE-LICENSE.txt`. Código: https://github.com/nodejs/node . Se ejecuta como proceso separado.
- **Flask, Werkzeug, Jinja2, itsdangerous, Click, MarkupSafe, Blinker**: licencias BSD/MIT correspondientes, recogidas de sus distribuciones.
- **Waitress**: Zope Public License 2.1.
- **qrcode**: BSD.
- **Python**: Python Software Foundation License.
- **PyInstaller**: GPL con excepción para distribuir aplicaciones compiladas; no cambia por sí sola la licencia de la aplicación.

Las licencias encontradas en los paquetes de la compilación se copian a `Licencias/`. El script de compilación y el código fuente de la app se entregan en el proyecto. Para redistribución pública, conserva también las condiciones y disponibilidad de código que correspondan a los binarios de terceros.
