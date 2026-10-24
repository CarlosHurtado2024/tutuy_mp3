/** Build only the public interface; never package desktop binaries or user data. */
import { copyFile, mkdir, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const source = join(root, 'web');
const output = join(root, 'web-dist');
await mkdir(join(output, 'static'), { recursive: true });

for (const file of ['index.html', 'manifest.webmanifest', 'sw.js']) {
  await copyFile(join(source, file), join(output, file));
}
for (const file of ['app.css', 'app.js', 'icon.svg', 'icon.ico']) {
  await copyFile(join(source, file), join(output, 'static', file));
}
// This is deliberately public configuration. It contains no pairing key or secrets.
await writeFile(join(output, 'deployment.json'), JSON.stringify({ mode: 'hosted' }) + '\n');
console.log('Interfaz web generada en web-dist/. Configura el servidor de descargas antes de usar /api/.');
