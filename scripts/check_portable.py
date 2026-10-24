"""Exercise the compiled EXE with Python/Node removed from PATH."""
from pathlib import Path
import http.cookiejar
import json
import os
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

ROOT = Path(__file__).resolve().parent.parent
PORT = 8766
BASE = f'http://127.0.0.1:{PORT}'


def main():
    executable = ROOT/'dist'/'Tutuy MP3'/'Tutuy MP3.exe'
    data_dir = ROOT/'.test-data'/'portable'
    environment = os.environ.copy()
    environment['PATH'] = str(Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32')
    environment.pop('PYTHONPATH',None)
    environment.pop('IMAGEIO_FFMPEG_EXE',None)
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def api(path, data=None):
        request = Request(BASE+path, data=None if data is None else json.dumps(data).encode(), headers={} if data is None else {'Content-Type':'application/json'})
        with opener.open(request,timeout=90) as response:
            return json.load(response)
    process = subprocess.Popen([str(executable),'--no-browser','--port',str(PORT),'--data-dir',str(data_dir)],env=environment,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            try:
                health = api('/api/health')
                break
            except OSError:
                if process.poll() is not None:
                    raise RuntimeError(f'Portable exited: {process.returncode}')
                time.sleep(.2)
        else:
            raise RuntimeError('Portable did not start in 30 seconds')
        print('EXE:',health,flush=True)
        with urlopen(BASE,timeout=10) as response:
            assert b'Tutuy MP3' in response.read()
        key = json.loads((data_dir/'conexion.json').read_text(encoding='utf-8'))['key']
        api('/api/connect',{'key':key})
        status = api('/api/status')
        print('BUNDLED RUNTIMES:',{k:status[k] for k in ('online','ffmpeg','youtube_runtime')},flush=True)
        assert status['ffmpeg'] and status['youtube_runtime']
        pair = api('/api/pair')
        for paired_url in pair['urls']:
            address = paired_url.split('/#')[0]
            with urlopen(address+'/api/health',timeout=5) as response:
                assert json.load(response)['ready']
            print('LAN:',address,'OK',flush=True)
        # Historical 1916 recording, or an explicitly supplied authorized test URL.
        test_url = sys.argv[1] if len(sys.argv)>1 else 'https://www.youtube.com/watch?v=4kQJYc-L6jw'
        result = api('/api/search',{'query':test_url,'mode':'url','limit':10})
        assert result['songs']
        created = api('/api/downloads',{'ids':[result['songs'][0]['id']],'quality':320})
        identifier = created['ids'][0]
        deadline = time.monotonic()+120
        while time.monotonic()<deadline:
            job = next(job for job in api('/api/downloads')['jobs'] if job['id']==identifier)
            if job['status'] not in {'queued','downloading','converting'}:
                print('FROZEN DOWNLOAD:',{k:job[k] for k in ('status','duration','size','quality','error')},flush=True)
                assert job['status']=='completed',job['error']
                break
            time.sleep(.25)
        else:
            raise RuntimeError('Portable download timed out')
        with opener.open(Request(BASE+f'/api/downloads/{identifier}/file',headers={'Range':'bytes=0-127'}),timeout=10) as response:
            assert response.status==206 and len(response.read())==128
        api('/api/shutdown',{})
        process.wait(timeout=15)
        assert process.returncode==0
        print('START / SEARCH / MP3 320 / LAN / RANGE / SHUTDOWN: OK',flush=True)
        return 0
    finally:
        if process.poll() is None:
            try:
                api('/api/shutdown',{})
                process.wait(timeout=10)
            except Exception:
                process.terminate()
                process.wait(timeout=5)


if __name__=='__main__':
    raise SystemExit(main())
