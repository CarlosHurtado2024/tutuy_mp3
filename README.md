# Tutuy MP3

Aplicación portable para Windows, con interfaz web adaptable a computador, celular y tablet. Busca por artista, canción o género, permite seleccionar varios resultados y convierte a MP3 con FFmpeg. No necesita claves de API.

## GitHub y Vercel

Repositorio: [CarlosHurtado2024/tutuy_mp3](https://github.com/CarlosHurtado2024/tutuy_mp3).

La interfaz está preparada para Vercel mediante `vercel.json` y `npm run build`. El motor de descargas requiere un servidor persistente: no funciona solo con publicar archivos estáticos. Consulta [DEPLOYMENT.md](DEPLOYMENT.md) para importar el repositorio, ejecutar el motor y conectar la API. La interfaz avisa cuando todavía falta conectar ese motor.

## Uso del portable

Extrae **release/Tutuy-MP3-Portable-Windows.zip** y abre **Tutuy MP3/Tutuy MP3.exe**. Conserva toda la carpeta, incluido `_internal`. El programa abre una ventana de aplicación de Edge o Chrome; si no están disponibles, usa el navegador predeterminado. No instala servicios ni requiere Python en el equipo de destino. Windows puede mostrar la advertencia habitual de un ejecutable sin firma digital.

Los MP3, el historial SQLite y los registros se guardan en `data/` junto al ejecutable. Pon la app en una carpeta con permiso de escritura; evita `Archivos de programa`. Para salir del servicio usa **Preferencias → Cerrar Tutuy en este computador**. Cerrar solo la ventana permite seguir usando la interfaz desde el celular.

## Qué incluye

- Búsqueda por texto en YouTube o SoundCloud; el género se añade a la consulta, sin asumir que sea una clasificación verificada.
- Enlaces públicos de otras plataformas compatibles con yt-dlp y listas limitadas a 10, 20 o 40 entradas. Las transmisiones en vivo se excluyen.
- Selección múltiple, filtro, orden y conversión a MP3 a 128, 192 o 320 kbps. Un bitrate alto no mejora una fuente de baja calidad.
- Dos descargas simultáneas, cola, progreso, cancelación, reintento e historial persistente (hasta 500 entradas recientes visibles).
- Biblioteca, reproducción y descarga al dispositivo que abre el navegador.
- Comprobación HTTPS de conectividad en el computador, antes de cada búsqueda y cada lote. Durante el uso se actualiza cada 15 segundos, con caché de 12 segundos. La accesibilidad de una plataforma concreta puede diferir.
- Aviso separado si se pierde la comunicación entre navegador y computador.
- Enlace de conexión privado y QR para la red local. Las acciones para abrir carpetas o cerrar el programa solo se admiten desde el propio computador.
- Sin fuentes tipográficas, analítica ni bibliotecas de interfaz remotas. Las miniaturas se solicitan directamente a su plataforma.

## Celular y web

Conecta ambos dispositivos a la misma Wi-Fi. En el computador pulsa **Conectar dispositivo** y escanea el QR. Mantén la app abierta y el computador encendido. Si Windows lo solicita, permite acceso en redes privadas; no hace falta abrir puertos en el router. En el celular, descarga cada MP3 terminado desde **Mi biblioteca**. La conversión se ejecuta en el computador.

Es una interfaz web local, no una app nativa de Android/iOS ni un servidor alojado en Internet. Un enlace `localhost` solo sirve en el computador que lo ejecuta. La dirección del QR utiliza la IP local y puede cambiar al cambiar de Wi-Fi. Algunas redes de invitados impiden que los dispositivos se comuniquen.

El manifiesto y el service worker están incluidos. La caché de la interfaz solo funciona en contextos seguros (localhost o HTTPS); la instalación como PWA depende del navegador. El acceso HTTP por Wi-Fi funciona en el navegador sin necesitar PWA. Los MP3 ya guardados se reproducen sin Internet mientras siga accesible el computador; los archivos guardados directamente en el celular se pueden reproducir sin él.

## Desarrollo

Requiere Python 3.11 o posterior y Node.js 22 o posterior para los desafíos JavaScript de YouTube.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Si `ensurepip` no está disponible en una distribución de Python, se puede usar `python -m pip --python .\.venv\Scripts\python.exe install -r requirements-build.txt` con el pip del sistema. No es necesario activar el entorno.

Opciones:

```powershell
.\.venv\Scripts\python.exe app.py --port 8765 --no-browser
.\.venv\Scripts\python.exe app.py --host 127.0.0.1 --data-dir .\mis-datos
```

`--host 127.0.0.1` limita el uso al propio equipo. El valor predeterminado `0.0.0.0` permite la red local. La clave del enlace se guarda en `data/conexion.json`; cuida esa carpeta y comparte el QR solo con dispositivos de confianza. La sesión usa una cookie HttpOnly, SameSite=Strict; los enlaces usan un fragmento que se retira al conectar. El servidor no habilita CORS y rechaza peticiones de otros orígenes. Está pensado para una red privada de confianza: no lo expongas directamente a Internet. La validación de URL bloquea destinos locales iniciales, pero los extractores necesitan acceder a red y seguir redirecciones de plataformas.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check web/app.js
```

La suite genera un WAV de prueba y ejecuta **FFmpeg real** para verificar el MP3, bitrate, etiquetas, descarga HTTP parcial, persistencia, cancelación, errores de conexión, autenticación y restricciones de origen/red. La obtención de medios se sustituye en las pruebas automáticas para no depender de una plataforma externa. Las restricciones o cambios de cada servicio requieren además verificación manual en Internet.

## Generar el portable

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
New-Item -ItemType Directory -Force tools
# Guarda en tools/NODE-LICENSE.txt la licencia de la versión de Node incluida.
.\.venv\Scripts\python.exe scripts/build_portable.py
```

El script usa PyInstaller, incluye Python, el motor de yt-dlp, sus scripts EJS, FFmpeg y Node, copia licencias y crea el ZIP. Se construye para la arquitectura del Windows que lo compila (esta entrega: x64). No se ha firmado el ejecutable. Incluye el código fuente de esta carpeta al redistribuir o modificar el programa y revisa `THIRD_PARTY.md` para las licencias de los componentes incluidos.

Para actualizar yt-dlp cuando cambie una plataforma, actualiza la versión fijada en `requirements.txt`, instala de nuevo y vuelve a construir. La actualización del motor necesita una nueva compilación; no se descarga ni ejecuta código de actualización automáticamente.

## Límites de las plataformas

La app utiliza [yt-dlp](https://github.com/yt-dlp/yt-dlp), su [lista de fuentes](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) y los [scripts EJS](https://github.com/yt-dlp/yt-dlp/wiki/EJS). «Compatible» no garantiza que todos los enlaces de un servicio estén disponibles. YouTube y otras fuentes pueden exigir sesión, limitar solicitudes o bloquear descargas. No se elude DRM, pago ni acceso privado. Descarga únicamente contenido propio, de dominio público o autorizado.

El servidor utiliza Flask + Waitress; la interfaz es HTML/CSS/JavaScript sin proceso de compilación. La conversión llama al FFmpeg incluido por [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg); la conversión directa evita necesitar ffprobe.
