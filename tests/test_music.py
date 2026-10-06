"""Music account contracts and real HTTP range playback, without personal accounts."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, io, json, tempfile, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch
import music


class Response(io.BytesIO):
    def __init__(self, data=b'audio', status=200, headers=None):
        super().__init__(data); self.status=status; self.headers=headers or {'Content-Type':'audio/mpeg'}


class MusicTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=music.Store(self.tmp.name)

    def test_plex_credentials_and_disconnect(self):
        self.store.configure({'provider':'plex','server':'http://127.0.0.1:32400','token':'unique-private-token'})
        self.assertTrue(self.store.public()['providers']['plex']['connected'])
        self.assertNotIn('unique-private-token',json.dumps(self.store.public()))
        self.store.tickets['old']=('plex',{},time.time()+100)
        self.store.forget('plex');self.assertFalse(self.store.tickets)
        if sys.platform != "win32":
            self.assertEqual(self.store.file.stat().st_mode & 0o777,0o600)
        else:
            self.assertTrue(self.store.file.is_file(), "Windows must persist credentials; Unix permission bits do not represent its ACLs")

    def test_only_apple_music_and_plex_are_offered(self):
        self.assertEqual(set(self.store.public()['providers']),{'apple','plex'})
        for gone in ('ibroadcast','subsonic'):
            with self.assertRaises(music.MusicError):self.store.configure({'provider':gone,'server':'https://music.example.com'})

    def test_plex_video_browsing_does_not_start_rides_or_accept_paths(self):
        self.store.save({'plex':{'server':'http://localhost:32400','token':'private'}})
        with patch.object(self.store,'plex',return_value={'Metadata':[
            {'type':'episode','ratingKey':'4','title':'Episode','duration':120000,'Media':[{'container':'mp4','videoCodec':'h264','Part':[{'key':'/library/parts/4/video.mp4'}]}]},
            {'type':'episode','ratingKey':'5','title':'Needs conversion','Media':[{'container':'mkv','Part':[{'key':'/library/parts/5/video.mkv'}]}]},
            {'type':'show','ratingKey':'6','title':'Show'}]}) as call:
            data=self.store.video('section:1')
            self.assertEqual(data['items'][0]['duration'],120)
            self.assertTrue(data['items'][0]['url'].startswith('/api/music/stream/'))
            self.assertIn('unavailable',data['items'][1]);self.assertTrue(data['items'][2]['folder'])
            self.assertNotIn('private',json.dumps(data))
            with self.assertRaises(music.MusicError):self.store.video('item:../../etc/passwd')
        with patch('music.open_remote',return_value=Response(b'video',206,{'Content-Type':'video/mp4','Content-Range':'bytes 0-4/5'})) as opened:
            ticket=data['items'][0]['url'].split('/')[-1];code,mime,stream,headers=self.store.stream(ticket,'bytes=0-4')
            self.assertEqual(code,206);self.assertEqual(mime,'video/mp4');self.assertEqual(stream.read(),b'video');stream.close()
            self.assertEqual(opened.call_args.args[1]['Range'],'bytes=0-4')
            self.assertNotIn('private',opened.call_args.args[0])

    def test_auth_qr_expiration_and_poll_interval(self):
        with patch('music.request_json',return_value={'id':42,'code':'ABCD','expiresIn':30}):
            card=self.store.connect('plex')
            self.assertIn('<svg',card['qr']);self.assertTrue(card['url'].startswith('https://app.plex.tv/'))
        with patch('music.request_json') as call:
            self.assertEqual(self.store.connect_poll('plex'),{'pending':True});call.assert_not_called()
        self.store.pending['plex']['expires_at']=0
        with self.assertRaises(music.MusicError) as err:self.store.connect_poll('plex')
        self.assertEqual(err.exception.code,410)
        with self.assertRaises(music.MusicError):music.Store.connection_card('https://evil.example/signin','',3,'plex')

    def test_api_denies_remote_setup_and_cross_site_writes(self):
        bridge=SimpleNamespace(csv_path=pathlib.Path(self.tmp.name)/'rides'/'fake.csv')
        async def call(peer,headers):return await music.handle(bridge,b'POST','/api/music/settings',b'{"provider":"plex"}','localhost:8729',headers,peer)
        self.assertEqual(asyncio.run(call(('192.168.1.2',20),{}))[0],403)
        self.assertEqual(asyncio.run(call(('127.0.0.1',20),{b'origin':b'https://evil.example'}))[0],403)

    def test_redirects_and_invalid_streams_never_leak_or_forward_credentials(self):
        self.assertIsNone(music.NoRedirect().redirect_request(None,None,302,'',{ },'https://elsewhere.example'))
        self.store.save({'plex':{'server':'http://localhost:32400','token':'private'}})
        self.store.tickets['t']=('plex',{'resource':'/library/parts/1/audio.mp3'},time.time()+100)
        response=Response(headers={'Content-Type':'text/html'})
        with patch('music.open_remote',return_value=response):
            with self.assertRaises(music.MusicError):self.store.stream('t')
        self.assertTrue(response.closed)
        with self.assertRaises(music.MusicError):self.store.stream('t','bytes=0-1,9-10')

    def test_real_http_range_stream_keeps_status_responsive(self):
        import panel
        content=b'x'*200000;seen=[]
        class Upstream(BaseHTTPRequestHandler):
            def do_GET(inner):
                seen.append((inner.headers.get('X-Plex-Token'),inner.headers.get('Range')))
                inner.send_response(206);inner.send_header('Content-Type','video/mp4');inner.send_header('Content-Length',str(len(content)));inner.send_header('Content-Range','bytes 0-199999/200000');inner.end_headers();inner.wfile.write(content)
            def log_message(*args):pass
        upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream);thread=threading.Thread(target=upstream.serve_forever,daemon=True);thread.start()
        self.addCleanup(upstream.server_close);self.addCleanup(upstream.shutdown)
        bridge=SimpleNamespace(csv_path=pathlib.Path(self.tmp.name)/'rides'/'fake.csv',status=lambda:{'power':123})
        store=music.store_for(bridge);store.save({'plex':{'server':'http://127.0.0.1:'+str(upstream.server_port),'token':'private'}})
        store.tickets['ticket']=('plex',{'resource':'/library/parts/1/video.mp4','video':True},time.time()+100)
        async def run():
            server=await panel.serve(bridge,port=0,lan=False);port=server.sockets[0].getsockname()[1]
            async def get(path,range_header=''):
                r,w=await asyncio.open_connection('127.0.0.1',port);w.write(f'GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n{range_header}\r\n'.encode());await w.drain();raw=await asyncio.wait_for(r.read(),5);w.close();await w.wait_closed();return raw
            try:
                stream,state=await asyncio.gather(get('/api/music/stream/ticket','Range: bytes=0-199999\r\n'),get('/status'))
                self.assertIn(b'206 Partial Content',stream);self.assertEqual(stream.split(b'\r\n\r\n',1)[1],content)
                self.assertIn(b'123',state);self.assertNotIn(b'private',stream.split(b'\r\n\r\n')[0])
            finally:server.close();await server.wait_closed()
        asyncio.run(run());self.assertEqual(seen,[('private','bytes=0-199999')])


if __name__=='__main__':unittest.main()
