"""Private-folder streams release their response on disconnect; no playback ticket registry remains."""
import io,pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import music
source=io.BytesIO(b'x'*100000);stream=music.StreamBody(source)
assert len(stream.read())==65536 and len(stream.read())==34464 and stream.read()==b''
stream.close();assert source.closed
stream.close();assert source.closed
assert not hasattr(music,'Store')
print('PASS bounded media reads, end of stream, idempotent disconnect cleanup and removed ticket registry')
