"""Local reviewed proposals, revision checks and retry-safe application.

Drafts are private, compressed SQLite records. Preview never changes coach.json.
API handlers call these synchronously, so a revision check and coach save have no
await gap. The SQLite write transaction serializes competing draft applications.
"""
import copy
import datetime as dt
import hashlib
import json
import secrets
import sqlite3
import time
import zlib
from pathlib import Path

TTL_SECONDS = 6 * 3600
MAX_DRAFTS = 8
DERIVED = {'_path', 'load_forecasts', 'program_apply_receipts'}

class Conflict(ValueError):
    pass

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def revision(d, base, profile, workouts, today):
    files=[]
    base=Path(base)
    for name in ('profile.json', 'activities', 'rides', 'workouts'):
        path=base/name
        candidates=path.rglob('*') if path.is_dir() else [path]
        for p in candidates:
            if p.is_file() and p.suffix.lower() in ('.json','.fit','.tcx','.csv'):
                stat=p.stat();files.append((str(p.relative_to(base)),stat.st_size,stat.st_mtime_ns))
    code={n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest() for n in ('program_builder.py','starter_programs.py','training_block.py','loads.py','damage.py','swimload.py','lifting.py','phaseblend.py','progression.py','coaching_review.py','calibration.py','recovery_calibration.py','running_response.py','response_model.py')}
    return digest({'model_code':code,'today':today,'coach':{k:v for k,v in d.items() if k not in DERIVED},
                   'profile':profile,'workouts':workouts,'files':sorted(files)})

def connect(base):
    db=sqlite3.connect(Path(base)/'program-drafts.sqlite3',timeout=10)
    (Path(base)/'program-drafts.sqlite3').chmod(0o600)
    db.execute('CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, revision TEXT, expires REAL, payload BLOB)')
    return db

def store(base, proposal, state_revision, now=None):
    now=time.time() if now is None else now
    token=secrets.token_urlsafe(24);expires=now+TTL_SECONDS
    db=connect(base)
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM drafts WHERE expires < ?', (now,))
        db.execute('INSERT INTO drafts VALUES (?,?,?,?)', (token,state_revision,expires,zlib.compress(json.dumps(proposal,allow_nan=False).encode())))
        db.execute('DELETE FROM drafts WHERE id NOT IN (SELECT id FROM drafts ORDER BY expires DESC LIMIT ?)',(MAX_DRAFTS,))
        db.commit()
    finally:db.close()
    return {**proposal,'draft':{'id':token,'state_revision':state_revision,'proposal_hash':digest(proposal),
            'expires_at':dt.datetime.fromtimestamp(expires,dt.timezone.utc).isoformat(),
            'notice':'Apply this exact draft ID. New training data or plan edits require another preview.'}}

def apply(base, d, token, state_revision, today, now=None):
    import coach, program_builder
    now=time.time() if now is None else now
    if not isinstance(token,str) or not token:raise ValueError('Preview first and provide its draft_id; field-only Apply is no longer supported')
    db=connect(base)
    try:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT revision,expires,payload FROM drafts WHERE id=?',(token,)).fetchone()
        if not row:raise Conflict('Draft is unavailable or expired. Preview again before applying.')
        proposal=json.loads(zlib.decompress(row[2]))
        receipt=next((r for r in d.get('program_apply_receipts',[]) if r['draft_id']==token),None)
        if receipt:
            db.commit();return {**proposal,'application':{**receipt,'already_applied':True}}
        if now>row[1]:raise Conflict('Draft expired. Preview again before applying.')
        if row[0]!=state_revision:raise Conflict('Training data or program changed since review. Preview again; nothing was applied.')
        if proposal['start']<today:raise Conflict('Draft starts in the past. Preview from today or a future date.')
        if proposal.get('starter') and proposal.get('starter_equipment')=='barbell':
            missing={x['name'] for p in proposal['starter']['plans'].values() for s in p['sessions'] for x in s.get('lifts',[]) if x.get('kind')=='barbell' and x.get('weight') is None}
            if missing:raise ValueError('Enter a recent set or report calibration results for: '+', '.join(sorted(missing)))
        program_builder.accept(d,copy.deepcopy(proposal))
        receipt={'draft_id':token,'proposal_hash':digest(proposal),'applied_at':dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat()}
        d['program_apply_receipts']=(d.get('program_apply_receipts',[])+[receipt])[-MAX_DRAFTS:]
        coach.save(d)
        db.commit()
        return {**proposal,'application':{**receipt,'already_applied':False}}
    except Exception:
        db.rollback();raise
    finally:db.close()
