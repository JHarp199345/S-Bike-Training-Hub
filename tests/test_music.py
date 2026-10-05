"""Music account contracts and real HTTP range playback, without personal accounts."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, hashlib, io, json, tempfile, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
import music


class Response(io.BytesIO):
    def __init__(self, data=b'audio', status=200, headers=None):
        super().__init__(data); self.status=status; self.headers=headers or {'Content-Type':'audio/mpeg'}


class MusicTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=music.Store(self.tmp.name)

    def test_subsonic_credentials_and_disconnect(self):
        self.store.configure({'provider':'subsonic','server':'http://127.0.0.1:4533','username':'athlete','password':'unique-private-password'})
        with patch('music.request_json',return_value={'subsonic-response':{'status':'ok','playlists':{'playlist':[{'id':'p','name':'Ride'}]}}}) as call:
            self.assertEqual(self.store.playlists('subsonic')[0]['name'],'Ride')
            params=parse_qs(urlsplit(call.call_args.args[0]).query)
            self.assertNotIn('p',params);self.assertEqual(params['t'][0],hashlib.md5(('unique-private-password'+params['s'][0]).encode()).hexdigest())
        self.assertNotIn('unique-private-password',json.dumps(self.store.public()))
        self.store.tickets['old']=('subsonic',{},time.time()+100)
        self.store.forget('subsonic');self.assertFalse(self.store.tickets)
        self.assertEqual(self.store.file.stat().st_mode & 0o777,0o600)

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

    def test_ibroadcast_refresh_uses_track_id_and_current_token(self):
        self.store.save({'ibroadcast':{'client_id':'app','access_token':'old','refresh_token':'refresh','expires_at':0}})
        lib={'tracks':{'map':{'title':0,'artist_id':1,'length':2,'file':3},'99':['Song',2,60,'/file/song.mp3']},
             'artists':{'map':{'name':0},'2':['Artist']},'playlists':{'map':{'name':0,'tracks':1},'3':['Ride',[99]]},'expires':2000000000}
        def reply(url,headers=None,data=None,form=False):
            if '/token' in url:return {'access_token':'fresh','refresh_token':'next','expires_in':3600}
            self.assertEqual(headers['Authorization'],'Bearer fresh')
            return {'user':{'id':7}} if 'api.ibroadcast' in url else {'library':lib}
        with patch('music.request_json',side_effect=reply):
            tracks=self.store.tracks('ibroadcast','3')['tracks'];self.assertEqual(tracks[0]['title'],'Song')
            with patch('music.open_remote',return_value=Response()) as opened:
                stream=self.store.stream(tracks[0]['url'].split('/')[-1])[2];stream.close()
                q=parse_qs(urlsplit(opened.call_args.args[0]).query)
                self.assertEqual(q['file_id'],['99']);self.assertEqual(q['Signature'],['fresh'])

    def test_auth_qr_expiration_and_poll_interval(self):
        self.store.save({'ibroadcast':{'client_id':'app'}})
        with patch('music.request_json',return_value={'device_code':'secret','verification_uri_complete':'https://www.ibroadcast.com/device?code=ABCD','user_code':'ABCD','expires_in':30,'interval':5}):
            card=self.store.connect('ibroadcast')
            self.assertIn('<svg',card['qr']);self.assertNotIn('device_code',card)
        with patch('music.build_opener') as opener:
            self.assertEqual(self.store.connect_poll('ibroadcast'),{'pending':True});opener.assert_not_called()
        self.store.pending['ibroadcast']['expires_at']=0
        with self.assertRaises(music.MusicError) as err:self.store.connect_poll('ibroadcast')
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
