"""Build a Windows x64 folder + ZIP. Run in the project's virtual environment."""
from pathlib import Path
import importlib.metadata
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def main():
    if os.name != 'nt':
        raise SystemExit('Construye el portable para Windows desde Windows.')
    node = shutil.which('node')
    if not node:
        raise SystemExit('Instala Node.js >= 22 antes de construir. Se incluirá en el portable.')
    major = int(subprocess.check_output([node,'--version'],text=True).strip().lstrip('v').split('.')[0])
    if major < 22:
        raise SystemExit('Se requiere Node.js 22 o posterior.')
    command = [sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
               '--name','Tutuy MP3','--distpath',str(ROOT/'dist'),'--workpath',str(ROOT/'build'),
               '--specpath',str(ROOT/'build'),'--icon',str(ROOT/'web'/'icon.ico'),'--add-data',f'{ROOT / "web"};web',
               '--add-binary',f'{node};tools',
               '--collect-all','yt_dlp','--collect-all','yt_dlp_ejs','--collect-all','imageio_ffmpeg',
               '--collect-all','qrcode','--copy-metadata','yt-dlp','--copy-metadata','yt-dlp-ejs',
               '--copy-metadata','imageio-ffmpeg',str(ROOT/'app.py')]
    subprocess.run(command,cwd=ROOT,check=True)
    output = ROOT/'dist'/'Tutuy MP3'
    shutil.copyfile(ROOT/'LEEME.txt',output/'LEEME.txt')
    shutil.copyfile(ROOT/'README.md',output/'README.md')
    licenses = output/'Licencias'
    licenses.mkdir(exist_ok=True)
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata['Name']
        for file in distribution.files or []:
            if 'license' in file.name.lower() or 'copying' in file.name.lower():
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    destination = licenses/name/file.name
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(source,destination)
    node_license = ROOT/'tools'/'NODE-LICENSE.txt'
    if not node_license.exists():
        raise SystemExit('Falta tools/NODE-LICENSE.txt. Descarga la licencia de la versión de Node incluida antes de distribuir.')
    shutil.copyfile(node_license,licenses/'NODE-LICENSE.txt')
    shutil.copyfile(ROOT/'THIRD_PARTY.md',licenses/'THIRD_PARTY.md')
    release = ROOT/'release'
    release.mkdir(exist_ok=True)
    zip_path = shutil.make_archive(str(release/'Tutuy-MP3-Portable-Windows'),'zip',root_dir=ROOT/'dist',base_dir='Tutuy MP3')
    print(f'PORTABLE: {output / "Tutuy MP3.exe"}')
    print(f'ZIP: {zip_path}')


if __name__ == '__main__':
    main()
