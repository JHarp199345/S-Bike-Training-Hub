"""Local file readers, source preservation and failed-reader isolation."""
import sys,pathlib,tempfile,io,base64,subprocess,json
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import workout_imports as wi
from PIL import Image,ImageDraw,ImageFont

def text_pdf():
 objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 400] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
 stream=b'BT /F1 18 Tf 40 320 Td (Warm-up 200 yards freestyle) Tj 0 -30 Td (Main set 4 x 50 free @ 1:10) Tj ET'
 objects.append(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream')
 output=b'%PDF-1.4\n';offsets=[0]
 for i,obj in enumerate(objects,1):offsets.append(len(output));output+=str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n'
 xref=len(output);output+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{n:010d} 00000 n \n'.encode() for n in offsets[1:])+f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode();return output

with tempfile.TemporaryDirectory() as tmp:
 base=pathlib.Path(tmp)
 raw=text_pdf();doc=wi.upload(base,{'name':'swim.pdf','data':base64.b64encode(raw).decode()})
 assert '200 yards' in doc['text'] and len(doc['pages'])==1
 assert wi.get_page(base,doc['id'],1).startswith(b'\x89PNG')
 assert wi.source(base,doc['id'])==(raw,'application/pdf')
 image=Image.new('RGB',(1100,400),'white');draw=ImageDraw.Draw(image);font=ImageFont.load_default(size=36)
 draw.text((50,45),'WARM-UP 200 yards',fill='black',font=font)
 draw.text((50,115),'200 free easy',fill='black',font=font)
 draw.text((50,185),'MAIN SET 400 yards',fill='black',font=font)
 draw.text((50,255),'4 x 100 free @ 2:00',fill='black',font=font)
 buf=io.BytesIO();image.save(buf,format='PNG');png=wi.read_file(buf.getvalue(),'typed.png')
 assert '200' in png['text'] and '2:00' in png['text'],png['text']
 # The same content in a scanned PDF must use OCR rather than an empty text layer.
 buf=io.BytesIO();image.save(buf,format='PDF');pdf=wi.read_file(buf.getvalue(),'scan.pdf')
 assert '200' in pdf['text'] and '2:00' in pdf['text'],pdf['text']
 for raw,name in [(b'nope','bad.pdf'),(b'nope','bad.png'),(b'hello','bad.exe'),(b'\xff','bad.txt')]:
  before=list(wi.folder(base).glob('*'))
  try:wi.upload(base,{'name':name,'data':base64.b64encode(raw).decode()})
  except ValueError:pass
  else:raise AssertionError(name)
  assert list(wi.folder(base).glob('*'))==before
 with patch.object(wi.subprocess,'run',return_value=subprocess.CompletedProcess([], -11, '', 'native crash')):
  try:wi.read_file(b'image','image.png')
  except ValueError as e:assert 'Hub is still running' in str(e)
  else:raise AssertionError('Native crash escaped isolation')
 with patch.object(wi.subprocess,'run',side_effect=subprocess.TimeoutExpired([],120)):
  try:wi.read_file(b'image','image.png')
  except ValueError as e:assert 'too long' in str(e)
  else:raise AssertionError('Reader timeout unhandled')
 print('PASS image OCR, text PDF, scanned PDF, preserved sources, malformed files and reader crash/timeout isolation')
