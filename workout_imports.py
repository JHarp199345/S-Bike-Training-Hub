"""Local document reading for prescription drafts, separate from completed activity imports."""
import base64, io, json, re, threading, uuid, subprocess, sys
from pathlib import Path
MAX_BYTES=10_000_000
MAX_PAGES=6
_lock=threading.Lock();_engine=None

def folder(base):return Path(base)/'workout-imports'
def identifier(v):
 if not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{32}',v):raise ValueError('Invalid workout import ID')
 return v

def vision_ocr(image):
 import Vision, Foundation
 data=io.BytesIO();image.convert('RGB').save(data,format='PNG')
 ns=Foundation.NSData.dataWithBytes_length_(data.getvalue(),len(data.getvalue()))
 request=Vision.VNRecognizeTextRequest.alloc().init()
 request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
 request.setRecognitionLanguages_(['en-US']);request.setUsesLanguageCorrection_(False)
 handler=Vision.VNImageRequestHandler.alloc().initWithData_options_(ns,{})
 ok,error=handler.performRequests_error_([request],None)
 if not ok:raise ValueError('Native OCR could not read this image')
 items=[]
 for result in request.results() or []:
  candidates=result.topCandidates_(1)
  if not candidates:continue
  c=candidates[0];box=result.boundingBox()
  items.append({'x':box.origin.x*image.width,'y':(1-box.origin.y-box.size.height/2)*image.height,'height':box.size.height*image.height,'text':str(c.string()),'confidence':round(float(c.confidence()),3)})
 return ordered_lines(items)

def ordered_lines(items):
 rows=[]
 for item in sorted(items,key=lambda i:i['y']):
  if rows and abs(rows[-1]['y']-item['y'])<=max(7,min(rows[-1]['height'],item['height'])*.45):rows[-1]['items'].append(item)
  else:rows.append({'y':item['y'],'height':item['height'],'items':[item]})
 lines=[{'text':' '.join(i['text'] for i in sorted(row['items'],key=lambda i:i['x'])),'confidence':min(i['confidence'] for i in row['items'])} for row in rows]
 return '\n'.join(x['text'] for x in lines),lines

def ocr(image):
 global _engine
 if sys.platform=='darwin':
  try:return vision_ocr(image)
  except (ImportError,ValueError):pass
 from PIL import Image
 import numpy as np
 from rapidocr import RapidOCR
 import rapidocr, onnxruntime
 onnxruntime.disable_telemetry_events()
 with _lock:
  if _engine is None:
   models=Path(rapidocr.__file__).parent/'models'
   # Explicit packaged models: reading a workout must never fetch models or upload the source.
   paths={'Det.model_path':models/'PP-OCRv6_det_small.onnx','Cls.model_path':models/'ch_ppocr_mobile_v2.0_cls_mobile.onnx','Rec.model_path':models/'PP-OCRv6_rec_small.onnx'}
   if not all(p.is_file() for p in paths.values()):raise ValueError('Local OCR models are missing; reinstall the workout import dependencies')
   _engine=RapidOCR(params={**{k:str(v) for k,v in paths.items()},'EngineConfig.onnxruntime.intra_op_num_threads':2,'EngineConfig.onnxruntime.inter_op_num_threads':2,'Global.log_level':'error'})
  image=image.convert('RGB');image.thumbnail((2000,2000))
  out=_engine(np.array(image))
  rows=[]
  if out.txts is None:return '',[]
  items=[]
  for box,text,score in zip(out.boxes,out.txts,out.scores):
   items.append({'x':float(box[:,0].min()),'y':float(box[:,1].mean()),'height':float(box[:,1].max()-box[:,1].min()),'text':str(text),'confidence':round(float(score),3)})
  return ordered_lines(items)

def capabilities():
 import importlib.util
 return {'local_ocr':importlib.util.find_spec('PIL') is not None and ((sys.platform=='darwin' and importlib.util.find_spec('Vision') is not None) or all(importlib.util.find_spec(k) is not None for k in ('rapidocr','onnxruntime'))),'pdf':importlib.util.find_spec('pypdfium2') is not None,'max_bytes':MAX_BYTES,'max_pages':MAX_PAGES,'formats':['png','jpg','jpeg','webp','pdf','txt','md'],'handwriting':'Supported as an image draft; OCR may need correction or AI visual review.'}

def _read_file(raw,name):
 from PIL import Image, ImageOps
 ext=Path(name).suffix.lower();pages=[];texts=[];warnings=[]
 def page_image(img,text=None,lines=None):
  img=ImageOps.exif_transpose(img).convert('RGB');img.thumbnail((1800,1800))
  if text is None:text,lines=ocr(img)
  preview=io.BytesIO();img.save(preview,format='PNG')
  pages.append({'image':preview.getvalue(),'lines':lines or []});texts.append(text)
 if ext in ('.txt','.md'):
  try:texts=[raw.decode('utf-8-sig')]
  except UnicodeError:raise ValueError('Text files must use UTF-8')
 elif ext=='.pdf':
  if not raw.startswith(b'%PDF-'):raise ValueError('The selected file is not a PDF')
  import pypdfium2 as pdfium
  try:
   with pdfium.PdfDocument(raw) as doc:
    if not 1<=len(doc)<=MAX_PAGES:raise ValueError(f'Choose a PDF with 1–{MAX_PAGES} pages; split longer documents')
    for page in doc:
     try:
      tp=page.get_textpage()
      try:text=tp.get_text_range().strip()
      finally:tp.close()
      # Always preserve a rendered page for visual checking, even for text PDFs.
      width,height=page.get_size()
      scale=min(2,1800/max(width,height))
      bitmap=page.render(scale=scale)
      try:img=bitmap.to_pil().copy()
      finally:bitmap.close()
      page_image(img,text if len(text)>20 else None)
     finally:page.close()
  except ValueError:raise
  except Exception as e:raise ValueError('Could not read this PDF; unlock encrypted files or export a readable copy') from e
 elif ext in ('.png','.jpg','.jpeg','.webp'):
  try:
   with Image.open(io.BytesIO(raw)) as img:
    if img.width*img.height>24_000_000:raise ValueError('Image exceeds 24 megapixels; resize it before importing')
    if img.format not in ('PNG','JPEG','WEBP'):raise ValueError('Choose a PNG, JPEG or WebP image')
    page_image(img)
  except (OSError,Image.DecompressionBombError) as e:raise ValueError('Could not read this image') from e
 else:raise ValueError('Choose PNG, JPEG, WebP, PDF, TXT or Markdown')
 if len('\n'.join(texts))>18000:raise ValueError('The document exceeds 18,000 text characters; split it into workouts')
 if not any(t.strip() for t in texts):warnings.append('No readable text found. Enter the transcription, or ask your AI assistant to inspect the source.')
 if any(line['confidence']<.85 for p in pages for line in p['lines']):warnings.append('Some text has low OCR confidence. Compare distances, repetitions and interval times with the source.')
 warnings.append('Review all extracted text before saving. Handwriting and layouts can be misread even when OCR confidence is high.')
 return {'text':'\n\n'.join(texts),'pages':pages,'warnings':warnings}

def read_file(raw,name):
 # PDF/image native code runs in a disposable process, not in the live bike Hub.
 try:
  result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--read'],input=json.dumps({'data':base64.b64encode(raw).decode(),'name':name}),capture_output=True,text=True,encoding='utf-8',timeout=120)
 except subprocess.TimeoutExpired:raise ValueError('Reading took too long; crop the image or split the PDF and retry')
 if result.returncode:raise ValueError('The local file reader could not finish. The Hub is still running; try a clearer image or paste the workout text.')
 try:out=json.loads(result.stdout)
 except ValueError:raise ValueError('The local file reader returned an unreadable result')
 if out.get('error'):raise ValueError(out['error'])
 for page in out['pages']:page['image']=base64.b64decode(page['image'])
 return out

def upload(base,req):
 name=Path(str(req.get('name') or 'workout')).name[:140]
 data=req.get('data')
 if not isinstance(data,str) or len(data)>14_000_000:raise ValueError('Choose a file smaller than 10 MB')
 if ',' in data:data=data.split(',',1)[1]
 try:raw=base64.b64decode(data,validate=True)
 except Exception:raise ValueError('Invalid file encoding')
 if not 0<len(raw)<=MAX_BYTES:raise ValueError('Choose a file smaller than 10 MB')
 try:result=read_file(raw,name)
 except ImportError as e:raise ValueError('Install the Hub workout import dependencies, then retry. You can still paste or type the workout.') from e
 ident=uuid.uuid4().hex;dest=folder(base)/ident;dest.mkdir(parents=True)
 (dest/('source'+Path(name).suffix.lower())).write_bytes(raw)
 images=[]
 for i,p in enumerate(result['pages']):
  (dest/f'page-{i+1}.png').write_bytes(p['image']);images.append({'page':i+1,'url':f'/api/coach/workout-import/{ident}/page/{i+1}','lines':p['lines']})
 import swim_workouts
 text=result['text'];units='yd' if re.search(r'\b(?:yds?|yards?)\b',text,re.I) else 'm' if re.search(r'\b(?:meters?|metres?|m)\b',text,re.I) else None
 doc={'id':ident,'name':name,'text':text,'pages':images,'warnings':result['warnings'],'suggested_unit':units,'fields':swim_workouts.split_sections(text),'status':'unreviewed draft','source_url':f'/api/coach/workout-import/{ident}/source'}
 (dest/'draft.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
 return doc

def get(base,ident):
 try:return json.loads((folder(base)/identifier(ident)/'draft.json').read_text(encoding='utf-8'))
 except OSError:raise ValueError('Workout import not found')
def get_page(base,ident,page):
 get(base,ident)
 if isinstance(page,bool) or not isinstance(page,int) or not 1<=page<=MAX_PAGES:raise ValueError('Invalid page number')
 try:return (folder(base)/identifier(ident)/f'page-{page}.png').read_bytes()
 except OSError:raise ValueError('Source page not found')
def source(base,ident):
 doc=get(base,ident);p=folder(base)/identifier(ident)/('source'+Path(doc['name']).suffix.lower())
 mime={'.pdf':'application/pdf','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.txt':'text/plain; charset=utf-8','.md':'text/plain; charset=utf-8'}[p.suffix]
 return p.read_bytes(),mime

if __name__=='__main__' and '--read' in sys.argv:
 try:
  req=json.loads(sys.stdin.read(14_001_000));out=_read_file(base64.b64decode(req['data'],validate=True),req['name'])
  for page in out['pages']:page['image']=base64.b64encode(page['image']).decode()
 except ImportError:out={'error':'Install the Hub workout import dependencies, then retry. You can still paste or type the workout.'}
 except Exception as e:out={'error':str(e)}
 print(json.dumps(out,ensure_ascii=False))
