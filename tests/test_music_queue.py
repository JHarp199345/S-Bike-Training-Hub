"""The queue must shuffle without repetition and retain correct Previous history."""
import pathlib, shutil, subprocess, sys

def main():
    node=shutil.which('node')
    if not node: print('SKIP music queue: Node is unavailable');return True
    source=(pathlib.Path(__file__).resolve().parent.parent/'web/music-common.js').read_text()
    import base64
    module='data:text/javascript;base64,'+base64.b64encode(source.encode()).decode()
    test='''import {Queue} from MODULE;
import assert from 'node:assert/strict';
const q=new Queue(()=>0);q.set([{id:0},{id:1},{id:2}]);q.shuffle=true;
assert.equal(q.next().id,1);assert.equal(q.next().id,2);assert.equal(q.previous().id,1);
q.set([{id:3}]);assert.equal(q.next().id,3);assert.equal(q.previous().id,3);
q.set([]);assert.equal(q.next(),undefined);assert.equal(q.current(),undefined);
console.log('PASS music shuffle, history, one-track and empty queues');'''.replace('MODULE',repr(module))
    return subprocess.run([node,'--input-type=module','-e',test]).returncode==0

if __name__=='__main__':sys.exit(0 if main() else 1)
