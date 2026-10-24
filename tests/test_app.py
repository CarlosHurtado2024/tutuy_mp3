"""Offline contract tests, including real FFmpeg encoding and MP3 metadata."""
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import wave

from mutagen.mp3 import MP3

from tutuy.engine import AppError, Engine, validate_url
from tutuy.server import create_app


PUBLIC_DNS = [(2, 1, 6, '', ('93.184.216.34', 0))]
SONG = {"id": "result-1", "title": "Prueba de audio", "artist": "Tutuy", "url": "https://example.org/audio.wav", "thumbnail": "", "duration": 2, "platform": "Prueba"}


class FakeExtractor:
    """Copies generated local audio, preserving the downloader's real contract."""
    sample = None
    options = None

    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def extract_info(self, url, download=False):
        if download:
            output = self.options['outtmpl'].replace('%(ext)s', 'wav')
            shutil.copyfile(self.sample, output)
            for hook in self.options.get('progress_hooks', []):
                hook({'status': 'finished', 'downloaded_bytes': 32000, 'total_bytes': 32000})
        return {"title": "Prueba de audio", "artist": "Tutuy", "duration": 2, "ext": "wav", "webpage_url": SONG['url']}

    def prepare_filename(self, info):
        return self.options['outtmpl'].replace('%(ext)s', 'wav')


class AppTests(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parent.parent / '.test-data'
        test_root.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='tutuy-tests-', dir=test_root)
        self.directory = Path(self.temporary.name)
        self.app = create_app(self.directory)
        self.engine = self.app.extensions['engine']
        self.client = self.app.test_client()

    def tearDown(self):
        self.engine.close()
        self.engine.pool.shutdown(wait=True, cancel_futures=True)
        self.temporary.cleanup()

    def login(self):
        response = self.client.post('/api/connect', json={'key': self.app.extensions['pairing_key']})
        self.assertEqual(response.status_code, 200)
        return response

    def wait_job(self, identifier):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            job = self.engine.get(identifier)
            if job['status'] not in {'queued', 'downloading', 'converting'}:
                return job
            time.sleep(.03)
        self.fail('Download did not finish')

    def test_authentication_origin_and_lan_privileges(self):
        with self.client.get('/') as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/downloads').status_code, 401)
        self.assertEqual(self.client.post('/api/connect', json={'key':'invalid'}).status_code, 401)
        response = self.login()
        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', response.headers['Set-Cookie'])
        self.assertEqual(self.client.get('/api/downloads').status_code, 200)
        self.assertEqual(self.client.post('/api/downloads',json={'ids':['test']},headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/pair', environ_overrides={'REMOTE_ADDR':'192.168.1.7'}).status_code,403)
        self.assertEqual(self.client.post('/api/shutdown',json={},environ_overrides={'REMOTE_ADDR':'192.168.1.7'}).status_code,403)

    def test_network_failure_prevents_new_downloads(self):
        self.login()
        with patch.object(self.engine, 'internet', return_value=False):
            response = self.client.post('/api/search',json={'query':'Jazz','mode':'genre'})
            self.assertEqual(response.status_code,503)
            self.assertIn('Internet',response.json['error'])
            response = self.client.post('/api/downloads',json={'ids':['result-1']})
            self.assertEqual(response.status_code,503)
            self.assertEqual(self.engine.jobs(),[])
            self.assertFalse(self.client.get('/api/status').json['online'])

    def test_hosted_origin_does_not_grant_desktop_privileges(self):
        with patch.dict('os.environ', {'TUTUY_PUBLIC_ORIGIN': 'https://tutuy.example.com'}):
            hosted = create_app(self.directory / 'hosted')
        try:
            client = hosted.test_client()
            headers = {'Origin': 'https://tutuy.example.com'}
            response = client.post('/api/connect', json={'key': hosted.extensions['pairing_key']}, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertIn('Secure', response.headers['Set-Cookie'])
            self.assertEqual(client.get('/api/pair').status_code, 403)
            self.assertEqual(client.post('/api/shutdown', json={}, headers=headers).status_code, 403)
            self.assertEqual(client.post('/api/open-folder', json={}, headers=headers).status_code, 403)
            self.assertEqual(client.post('/api/connect', json={'key': hosted.extensions['pairing_key']}, headers={'Origin':'https://evil.example'}).status_code, 403)
            with patch.object(hosted.extensions['engine'], 'internet', return_value=True):
                self.assertFalse(client.get('/api/status').json['local'])
        finally:
            hosted.extensions['engine'].close()
        with patch.dict('os.environ', {'TUTUY_PUBLIC_ORIGIN': 'https://tutuy.example.com/path'}):
            with self.assertRaises(ValueError):
                create_app(self.directory / 'invalid')

    def test_public_urls_only_and_invalid_inputs(self):
        for url in ('file:///c:/windows/file','ytsearch10:test','http://localhost/a','https://host:bad/a','https://a:9000/a'):
            with self.assertRaises(AppError):
                validate_url(url)
        with patch('tutuy.engine.socket.getaddrinfo',return_value=[(2,1,6,'',('192.168.1.1',0))]):
            with self.assertRaises(AppError):
                validate_url('https://example.org/a')
        with patch('tutuy.engine.socket.getaddrinfo',return_value=PUBLIC_DNS):
            self.assertEqual(validate_url(SONG['url']),SONG['url'])
        self.login()
        self.assertEqual(self.client.post('/api/downloads',json={'ids':[{'url':SONG['url']}]}).status_code,400)
        self.assertEqual(self.client.post('/api/downloads',json={'ids':['result-1'],'quality':999}).status_code,400)

    def test_search_returns_selectable_ids_and_expired_selection_is_rejected(self):
        self.login()
        with patch.object(self.engine,'internet',return_value=True), patch('tutuy.engine.YoutubeDL',FakeExtractor), patch('tutuy.engine.socket.getaddrinfo',return_value=PUBLIC_DNS):
            response = self.client.post('/api/search',json={'query':'Tutuy','mode':'artist','provider':'youtube','limit':10})
            self.assertEqual(response.status_code,200)
            songs = response.json['songs']
            self.assertEqual(len(songs),1)
            self.assertIn(songs[0]['id'],self.engine.search_cache)
            response = self.client.post('/api/downloads',json={'ids':['unknown']})
            self.assertEqual(response.status_code,409)
            self.engine.search_cache[songs[0]['id']] = (time.monotonic()-3601,songs[0])
            self.assertEqual(self.client.post('/api/downloads',json={'ids':[songs[0]['id']]}).status_code,409)

    def test_full_download_real_mp3_metadata_range_and_persistence(self):
        sample = self.directory / 'input.wav'
        with wave.open(str(sample),'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b'\x00\x00' * 32000)
        FakeExtractor.sample = sample
        self.login()
        self.engine.search_cache['result-1'] = (time.monotonic(),SONG)
        with patch.object(self.engine,'internet',return_value=True), patch('tutuy.engine.YoutubeDL',FakeExtractor), patch('tutuy.engine.socket.getaddrinfo',return_value=PUBLIC_DNS):
            response = self.client.post('/api/downloads',json={'ids':['result-1'],'quality':192})
            self.assertEqual(response.status_code,202)
            identifier = response.json['ids'][0]
            job = self.wait_job(identifier)
        self.assertEqual(job['status'],'completed',job['error'])
        path = self.engine.file(identifier)
        audio = MP3(path)
        self.assertGreater(audio.info.length,1.8)
        self.assertAlmostEqual(audio.info.bitrate,192000,delta=100)
        self.assertEqual(str(audio.tags['TIT2']),'Prueba de audio')
        self.assertEqual(str(audio.tags['TPE1']),'Tutuy')
        response = self.client.get(f'/api/downloads/{identifier}/file',headers={'Range':'bytes=0-99'})
        self.assertEqual(response.status_code,206)
        self.assertEqual(response.content_type,'audio/mpeg')
        self.assertEqual(len(response.data),100)
        response.close()
        response = self.client.get(f'/api/downloads/{identifier}/file?save=1')
        self.assertIn('attachment',response.headers['Content-Disposition'])
        response.close()
        self.engine.close()
        other = Engine(self.directory)
        try:
            self.assertEqual(other.get(identifier)['status'],'completed')
            self.assertTrue(other.file(identifier).is_file())
        finally:
            other.close()

    def test_cancellation_and_interrupted_recovery(self):
        # Simulate an interrupted app without depending on network or timing.
        identifier = 'a' * 32
        with self.engine.connect() as db:
            db.execute("INSERT INTO jobs(id,title,status,created) VALUES(?,?,?,?)",(identifier,'Test','queued',time.time()))
        self.engine.events[identifier] = threading.Event()
        self.engine.cancel(identifier)
        self.assertTrue(self.engine.events[identifier].is_set())
        self.assertEqual(self.engine.get(identifier)['status'],'cancelled')
        with self.assertRaises(AppError):
            self.engine.file(identifier)
        self.engine.events.clear()
        self.engine.update(identifier,status='converting')
        other = Engine(self.directory)
        try:
            self.assertEqual(other.get(identifier)['status'],'error')
            self.assertIn('cerró',other.get(identifier)['error'])
        finally:
            other.close()

    def test_metadata_is_not_rendered_as_html_in_server_and_qr_is_private(self):
        self.login()
        with patch('tutuy.server.lan_addresses',return_value=['http://192.168.1.10:8765']):
            pair = self.client.get('/api/pair')
            self.assertIn('#key=',pair.json['urls'][0])
            qr = self.client.get('/api/qr?address=http://192.168.1.10:8765')
            self.assertEqual(qr.status_code,200)
            self.assertEqual(qr.content_type,'image/svg+xml; charset=utf-8')
            self.assertIn(b'<svg',qr.data)
            self.assertEqual(self.client.get('/api/qr?address=http://evil.example').status_code,400)


if __name__ == '__main__':
    unittest.main()
