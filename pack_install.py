"""Reviewed installation of signed Ride World ZIPs. No game code is executed here."""
import hashlib,io,json,os,re,stat,tempfile,threading,zipfile
from pathlib import Path
import packs,paths
LIMIT=128*1024*1024
_lock=threading.Lock()
def inspect(data,root=None,approve=False,replace=False):
 if not isinstance(data,bytes) or not 0<len(data)<=LIMIT:raise ValueError('Choose a game ZIP up to 128 MB.')
 root=Path(root or paths.DATA/'modes')
 with tempfile.TemporaryDirectory(prefix='s-bike-pack-') as tmp:
  stage=Path(tmp)
  try:
   with zipfile.ZipFile(io.BytesIO(data)) as z:
    files=[f for f in z.infolist() if not f.is_dir()]
    if not files or len(files)>32 or sum(f.file_size for f in files)>LIMIT:raise ValueError('This game exceeds the installation size limit.')
    prefixes={str(Path(f.filename).parent) for f in files}
    if len(prefixes)!=1:raise ValueError('Drop one game folder or ZIP at a time.')
    prefix=next(iter(prefixes))
    if prefix!='.' and (len(Path(prefix).parts)!=1 or prefix.startswith('.')):raise ValueError('This ZIP has an unsupported folder layout.')
    names=set()
    for f in files:
     parts=Path(f.filename).parts;name=parts[-1]
     if '\\' in f.filename or '..' in parts or f.filename.startswith('/') or name in names or stat.S_ISLNK(f.external_attr>>16):raise ValueError('This ZIP contains an unsafe or duplicate file.')
     if name!='manifest.json' and Path(name).suffix not in packs.SERVED:raise ValueError('This ZIP contains an unsupported file.')
     names.add(name)
     with z.open(f) as inp,open(stage/name,'wb') as out:
      total=0
      while chunk:=inp.read(1024*1024):
       total+=len(chunk)
       if total>f.file_size or total>LIMIT:raise ValueError('This game exceeds the installation size limit.')
       out.write(chunk)
  except (zipfile.BadZipFile,RuntimeError,EOFError):raise ValueError('This is not a readable game ZIP.') from None
  manifest,why=packs.check(stage)
  if why:raise ValueError(why)
  ident=manifest.get('id')
  if not isinstance(ident,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}',ident):raise ValueError('This game has an invalid identifier.')
  if names!=set(manifest['files'])|{'manifest.json'}:raise ValueError('This ZIP includes files outside its signed manifest.')
  if not isinstance(manifest.get('engine'),str) or not re.fullmatch(r'\d+\.\d+\.\d+',manifest['engine']):raise ValueError('This game has an invalid engine version.')
  if not packs.engine_dir(manifest['engine']):raise ValueError('The shared engine '+manifest['engine']+' is not installed. Update the Hub before installing this game.')
  import module_sandbox
  declared=module_sandbox.permissions(manifest)
  if not packs.isolated_engine_dir(manifest["engine"]):raise ValueError("The isolated game engine is missing. Update the Hub.")
  dest=root/ident
  result={'id':ident,'name':manifest.get('name',ident),'version':manifest.get('version'),'engine':manifest['engine'],'size':sum(f.file_size for f in files),'permissions':declared,'existing':dest.exists(),'installed':False,'sha256':hashlib.sha256(data).hexdigest()}
  if not approve:return result
  with _lock:
   if dest.is_symlink():raise ValueError('The installed game folder is a symbolic link; installation refused.')
   if dest.exists() and not replace:raise ValueError('This game is already installed. Review and approve replacing it.')
   root.mkdir(parents=True,exist_ok=True)
   import shutil,uuid
   incoming=root/('.incoming-'+uuid.uuid4().hex);backup=root/('.previous-'+ident+'-'+uuid.uuid4().hex)
   try:
    shutil.copytree(stage,incoming)
    if dest.exists():os.replace(dest,backup)
    try:os.replace(incoming,dest)
    except Exception:
     if backup.exists():os.replace(backup,dest)
     raise
   finally:
    if incoming.exists():shutil.rmtree(incoming)
   packs._checked.pop(dest,None)
   result.update(installed=True,backup_saved=backup.exists())
  return result
