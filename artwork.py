"""User artwork stays on this machine, separate from the stock asset catalog."""
import base64,json,uuid
from pathlib import Path

def library(base,web):
    stock=json.loads((web/'program-art.json').read_text()).get('assets',[])
    path=base/'artwork.json'
    return stock+(json.loads(path.read_text()).get('assets',[]) if path.exists() else [])

def upload(base,web,req):
    categories={'recovery':(['recovery','taper','rest'],['sleeping','stretching']),
                'cycling':(['assessment','base','build'],['cycling']),
                'swimming':(['assessment','base','build'],['swimming']),
                'strength':(['base','build','specific'],['lifting']),
                'running':(['specific','overview'],['running']),
                'preparation':(['taper','overview'],['preparation'])}
    category=req.get('category','preparation')
    if category not in categories:raise ValueError('Choose an artwork category')
    focal=req.get('focal',[75,50])
    if not isinstance(focal,list) or len(focal)!=2 or any(not isinstance(n,(int,float)) or not 0<=n<=100 for n in focal):raise ValueError('Invalid subject position')
    data=req.get('image','')
    if not isinstance(data,str) or len(data)>8_000_000:raise ValueError('Image must be smaller than 6 MB')
    prefix,sep,encoded=data.partition(',')
    allowed={'data:image/jpeg;base64':('jpg',b'\xff\xd8\xff'),'data:image/png;base64':('png',b'\x89PNG\r\n\x1a\n')}
    if not sep or prefix not in allowed:raise ValueError('Choose a JPEG or PNG image')
    try:raw=base64.b64decode(encoded,validate=True)
    except Exception:raise ValueError('Invalid image data')
    ext,magic=allowed[prefix]
    if len(raw)>6_000_000 or not raw.startswith(magic):raise ValueError('Invalid or oversized image')
    id='user-'+uuid.uuid4().hex
    file=web/'sports'/f'phase-{id}.{ext}';file.write_bytes(raw)
    phases,subjects=categories[category]
    asset={'id':id,'title':str(req.get('title') or 'My '+category+' photo')[:100],'phases':phases,'subjects':subjects,'style':'photorealistic','file':'/web/sports/'+file.name,'source':'local-upload','focal':focal}
    path=base/'artwork.json';d=json.loads(path.read_text()) if path.exists() else {'assets':[]}
    d['assets'].append(asset);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(d,indent=2)+'\n');tmp.replace(path)
    return asset
