import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import pack_install,packs
class InstallTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.pack=self.base/'source';self.pack.mkdir();(self.pack/'game.pck').write_bytes(b'example game');(self.pack/'credits.txt').write_text('Example credits')
  (self.pack/'manifest.json').write_text(json.dumps({'id':'example-chase','name':'Example Chase','version':'1.0','format':1,'engine':'4.7.1','main':'game.pck','permissions':{'telemetry':['ftp'],'controls':[]}}));secret='11'*32;self.key=patch.dict(packs.TRUSTED_KEYS,{'test':packs.public_key(bytes.fromhex(secret)).hex()});self.key.start();packs.sign_pack(self.pack,'test',secret);self.engine=patch.object(packs,'engine_dir',return_value=self.base);self.engine.start();self.isolated=patch.object(packs,'isolated_engine_dir',return_value=self.base);self.isolated.start();self.root=self.base/'installed'
 def tearDown(self):self.isolated.stop();self.engine.stop();self.key.stop();self.tmp.cleanup()
 def archive(self,extra=None,tamper=False):
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:
   for f in self.pack.iterdir():z.writestr(f.name,b'changed' if tamper and f.name=='game.pck' else f.read_bytes())
   if extra:z.writestr(extra,b'unlisted')
  return out.getvalue()
 def test_preview_approval_replacement_backup(self):
  d=self.archive();info=pack_install.inspect(d,self.root);self.assertFalse(info['installed']);self.assertFalse(self.root.exists());pack_install.inspect(d,self.root,approve=True);self.assertEqual((self.root/'example-chase/game.pck').read_bytes(),b'example game')
  with self.assertRaises(ValueError):pack_install.inspect(d,self.root,approve=True)
  info=pack_install.inspect(d,self.root,approve=True,replace=True);self.assertTrue(info['backup_saved']);self.assertEqual(len(list(self.root.glob('.previous-*'))),1)
 def test_reject_tampering_and_traversal(self):
  for data in [self.archive(tamper=True),self.archive('../escape.txt'),self.archive('outside.txt'),b'not zip']:
   with self.assertRaises(ValueError):pack_install.inspect(data,self.root,approve=True)
  self.assertFalse(self.root.exists())
 def test_missing_engine_and_bad_id(self):
  with patch.object(packs,'engine_dir',return_value=None):
   with self.assertRaises(ValueError):pack_install.inspect(self.archive(),self.root)
 def test_rollback(self):
  data=self.archive();pack_install.inspect(data,self.root,approve=True);real=pack_install.os.replace
  def fail(src,dst):
   if Path(src).name.startswith('.incoming-'):raise OSError('simulated installation failure')
   return real(src,dst)
  with patch.object(pack_install.os,'replace',side_effect=fail):
   with self.assertRaises(OSError):pack_install.inspect(data,self.root,approve=True,replace=True)
  self.assertEqual((self.root/'example-chase/game.pck').read_bytes(),b'example game')
if __name__=='__main__':unittest.main()
