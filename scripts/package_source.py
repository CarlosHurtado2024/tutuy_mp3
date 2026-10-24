"""Package only project source and notices; exclude dependencies and private data."""
from pathlib import Path
import hashlib
import zipfile

root = Path(__file__).resolve().parent.parent
release = root/'release'
release.mkdir(exist_ok=True)
archive = release/'Tutuy-MP3-Codigo-Fuente.zip'
files = ['app.py','.gitignore','requirements.txt','requirements-build.txt','README.md','LEEME.txt',
         'THIRD_PARTY.md','VALIDACION.md','Iniciar Tutuy.cmd','tools/NODE-LICENSE.txt']
for directory in ['tutuy','web','scripts','tests']:
    files.extend(str(file.relative_to(root)) for file in (root/directory).rglob('*') if file.is_file() and '__pycache__' not in file.parts)
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as output:
    for file in files:
        output.write(root/file,arcname=f'Tutuy-MP3-Codigo-Fuente/{file}')
checksums = []
for file in sorted(release.glob('*.zip')):
    with file.open('rb') as stream:
        checksum = hashlib.file_digest(stream,'sha256').hexdigest()
    checksums.append(f'{checksum}  {file.name}')
(release/'SHA256SUMS.txt').write_text('\n'.join(checksums)+'\n',encoding='utf-8')
print(archive)
print('\n'.join(checksums))
