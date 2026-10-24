"""Optional live check using the CC-BY Sintel trailer hosted by W3C."""
from pathlib import Path
import json
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from tutuy.engine import Engine


def main():
    engine = Engine(Path(__file__).resolve().parent.parent/'.test-data'/'live-network')
    try:
        print('INTERNET:',engine.internet(force=True),flush=True)
        songs = engine.search('https://media.w3.org/2010/05/sintel/trailer.mp4',mode='url',limit=10)
        print('EXTRACT:',json.dumps([{k:s[k] for k in ('title','artist','duration','platform')} for s in songs],ensure_ascii=True),flush=True)
        if not songs:
            raise RuntimeError('No result from test clip')
        identifier = engine.enqueue([songs[0]['id']],192)[0]
        deadline = time.monotonic()+120
        while time.monotonic()<deadline:
            job = engine.get(identifier)
            if job['status'] not in {'queued','downloading','converting'}:
                print('DOWNLOAD:',json.dumps({k:job[k] for k in ('status','error','size','filename')}),flush=True)
                if job['status'] != 'completed':
                    return 1
                from mutagen.mp3 import MP3
                audio = MP3(engine.file(identifier))
                print('MP3:',round(audio.info.length,2),'seconds',audio.info.bitrate,'bps',flush=True)
                return 0
            time.sleep(.5)
        print('TIMEOUT',flush=True)
        return 1
    finally:
        engine.close()


if __name__=='__main__':
    raise SystemExit(main())
