"""Validate and retain imported recordings without overwriting another activity."""
import hashlib
import re
import tempfile
import threading

_store_lock=threading.Lock()
from pathlib import Path


def store(base, name, data):
    with _store_lock:
        return _store(base,name,data)


def _store(base, name, data):
    import loads
    base=Path(base);folder=base/'activities';folder.mkdir(exist_ok=True)
    name=Path(name).name;extension=Path(name).suffix.lower()
    if extension not in ('.fit','.tcx') or not 0<len(data)<=20_000_000:
        raise ValueError('Choose a FIT or TCX workout file up to 20 MB')
    if extension=='.fit' and data[8:12]!=b'.FIT':raise ValueError('This is not a FIT activity file')
    reader=loads._from_fit if extension=='.fit' else loads._from_tcx
    with tempfile.NamedTemporaryFile(dir=folder,suffix=extension) as tmp:
        tmp.write(data);tmp.flush()
        try:activity=reader(Path(tmp.name))
        except Exception as e:raise ValueError('This file could not be read as a workout') from e
    if not activity or not activity.get('start') or not activity.get('minutes'):
        raise ValueError('This file has no usable workout date and duration')
    # Notice identical content even under a different export filename.
    digest=hashlib.sha256(data).digest()
    for p in folder.glob('*'+extension):
        if p.stat().st_size==len(data) and hashlib.sha256(p.read_bytes()).digest()==digest:
            return {'imported':[],'already':[p.name]}
    stem=re.sub(r'[^A-Za-z0-9_-]+','-',Path(name).stem).strip('-')[:95] or 'watch-workout'
    dest=folder/(stem+extension)
    if any((folder/(stem+ext)).exists() for ext in ('.fit','.tcx')) or (base/'rides'/(stem+'.csv')).exists():dest=folder/(stem+'-'+hashlib.sha256(data).hexdigest()[:12]+extension)
    dest.write_bytes(data)
    return {'imported':[dest.name],'already':[]}
