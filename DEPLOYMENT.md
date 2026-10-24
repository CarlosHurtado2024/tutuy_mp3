# GitHub y despliegue en Vercel

Repositorio: https://github.com/CarlosHurtado2024/tutuy_mp3

Esta entrega conserva la aplicación portable y prepara **la interfaz web** para Vercel. El motor de búsqueda y descargas necesita un proceso persistente con Python, Node, FFmpeg y un directorio de datos. No se ha desplegado ningún servicio en una cuenta de Vercel.

## 1. Importar la interfaz

1. En Vercel, crea un proyecto e importa `CarlosHurtado2024/tutuy_mp3`.
2. Selecciona la rama `main` y deja el directorio raíz en la raíz del repositorio.
3. Usa el preset **Other**. `vercel.json` configura la instalación, el comando `npm run build` y la salida `web-dist`.
4. Despliega la interfaz. No requiere claves ni dependencias de npm.

El proceso de compilación solo copia HTML, CSS, JavaScript, iconos y manifiesto. `.vercelignore` excluye el motor Python, ejecutables, datos, entornos virtuales y archivos de prueba. Antes de vincular una API, se muestra **Motor de descargas pendiente** y se desactiva la búsqueda; la publicación estática por sí sola no descarga ni convierte canciones.

## 2. Ejecutar el motor en un servidor persistente

La cola usa hilos de trabajo, el historial SQLite y los MP3 se guardan en disco. Un despliegue directo de este diseño en funciones sin estado perdería esas garantías. Vercel documenta las diferencias del sistema de archivos y los límites de sus funciones:

- https://vercel.com/kb/guide/why-does-my-serverless-function-work-locally-but-not-when-deployed
- https://vercel.com/docs/functions/limitations

Usa un servidor privado de confianza con almacenamiento persistente y HTTPS. Instala Python 3.11 o posterior, Node.js 22 o posterior y las dependencias de `requirements.txt`. Ejecuta **una sola instancia** del motor sobre el mismo directorio de datos. No compartas esta base de datos entre varios procesos de la aplicación.

Ejemplo de arranque en Linux, ajustando la ruta a tu volumen persistente:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export TUTUY_PUBLIC_ORIGIN="https://tu-proyecto.vercel.app"
.venv/bin/python app.py --no-browser --host 0.0.0.0 --port 8765 --data-dir /var/lib/tutuy
```

Configura un supervisor para mantener el proceso activo y un proxy HTTPS delante del puerto 8765. `TUTUY_PUBLIC_ORIGIN` admite exclusivamente el origen HTTPS completo de tu interfaz, sin ruta. Permite ese origen en las peticiones JSON, activa cookies Secure y **deshabilita** las acciones de escritorio, QR y cierre remoto, incluso si el proxy se conecta por localhost.

Esta es una biblioteca compartida por los dispositivos autorizados con la clave del servidor. El proyecto no incluye cuentas individuales ni aislamiento entre usuarios. Mantén el servicio privado y no lo conviertas en un descargador público sin añadir controles de acceso y recursos.

## 3. Vincular Vercel al motor

Cuando tengas una dirección pública HTTPS para tu propio servidor de descargas, agrega una regla a `vercel.json`, conservando los campos existentes:

```json
"rewrites": [
  {
    "source": "/api/:path*",
    "destination": "https://TU-SERVIDOR-DE-DESCARGAS/api/:path*"
  }
]
```

El texto `TU-SERVIDOR-DE-DESCARGAS` es un marcador: debes reemplazarlo por el dominio real del servidor. No uses `localhost`, una IP privada ni el enlace del QR en esta configuración. Vercel no puede acceder a la red Wi-Fi de tu computador. La dirección se fija en la configuración del proyecto; no se toma de parámetros proporcionados por visitantes.

Las solicitudes `/api/` se envían al motor y el navegador mantiene el mismo origen para cookies, reproducción y descarga. El motor responde con `Cache-Control: no-store`. Documentación de las reglas externas: https://vercel.com/docs/routing/rewrites . Vuelve a desplegar tras cambiar la regla y comprueba que `/api/health` responde con `app: "Tutuy MP3"`.

Para conectar tu navegador, lee **en tu propio servidor** la clave generada en `/var/lib/tutuy/conexion.json` y abre `https://tu-proyecto.vercel.app/#key=TU_CLAVE`. El cliente retira el fragmento al iniciar sesión. La clave no se incluye en Git, en variables públicas de JavaScript ni en el ZIP portable. Es un secreto de acceso a la biblioteca, así que compártela solo con tus dispositivos.

## 4. Verificación antes de usarlo

- Confirmar que `/api/health` llega al motor y que las peticiones del origen Vercel elegido funcionan; otros orígenes deben seguir rechazados.
- Descargar un audio autorizado, verificar su progreso y guardar el MP3 desde el navegador.
- Reiniciar el motor y comprobar que los MP3 y el historial permanecen.
- Confirmar que otro dispositivo sin la clave no puede consultar `/api/downloads` y que las acciones de escritorio no están disponibles en modo alojado.
- Comprobar cookies, respuesta `Cache-Control: no-store`, reproducción con HTTP Range, tamaño de archivos y tiempos del proxy con el alojamiento elegido.

Esta configuración se compila y prueba localmente; el enrutamiento entre Vercel y un backend real queda pendiente de proporcionar ese servidor y desplegar ambos componentes.

## Código y paquetes

Git incluye código, pruebas, documentación y capturas de la interfaz. Los MP3, registros, credenciales de conexión, entornos virtuales y paquetes compilados no se suben al repositorio. El portable se genera con `scripts/build_portable.py`; los binarios grandes se deben distribuir como artefactos o GitHub Releases, no dentro del historial Git.
