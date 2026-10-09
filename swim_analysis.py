"""Descriptive swim composition and response. No new training score or prescription."""
import math
from datetime import date, timedelta

STROKES = {0:'free',1:'back',2:'breast',3:'fly',4:'drill',5:'mixed',6:'medley'}
LABELS = {'free':'Freestyle','back':'Backstroke','breast':'Breaststroke','fly':'Butterfly','drill':'Drill · stroke unresolved','mixed':'Mixed','medley':'Medley · split unknown','choice':'Choice · split unknown','unknown':'Unclassified'}

def positive(v):
    return float(v) if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>0 else None

def mix(parts, total=None, basis=''):
    parts={k:v for k,v in parts.items() if positive(v)}
    known=sum(parts.values());total=max(positive(total) or known,known)
    if total-known>.01:parts['unknown']=parts.get('unknown',0)+total-known
    return {'total_m':round(total,3),'basis':basis,'parts':[{'stroke':k,'label':LABELS.get(k,LABELS['unknown']),'distance_m':round(v,3),'percent':round(v/total*100,2)} for k,v in parts.items()] if total else []}

def recipe_mix(recipe, basis='Written workout · distance proportions'):
    parts={};work_parts={}
    for s in (recipe or {}).get('sets',[]):
        key=s.get('stroke') if s.get('stroke') in LABELS else 'unknown'
        # A named stroke drill remains named in the athlete's description, not the watch.
        distance=positive(s.get('distance_m')) or 0
        parts[key]=parts.get(key,0)+distance
        work=s.get('work') if s.get('work') in ('swim','drill','kick','pull') else 'swim'
        work_parts[(key,work)]=work_parts.get((key,work),0)+distance
    out=mix(parts,basis=basis)
    out['work_parts']=[{'stroke':stroke,'work':work,'distance_m':round(distance,3)} for (stroke,work),distance in work_parts.items() if distance>0]
    return out

def watch_mix(a):
    parts={};pool=positive(a.get('pool_length_m'));session=positive(a.get('distance_m'))
    active=[x for x in a.get('swim_lengths',[]) if x.get('length_type')==1]
    if pool and active:
        for x in active:
            key=STROKES.get(x.get('swim_stroke'),'unknown');parts[key]=parts.get(key,0)+pool
        basis='Watch-classified active pool lengths · distance proportions'
    else:
        for lap in a.get('laps',[]):
            distance=positive(lap.get('total_distance'))
            if distance:
                key=STROKES.get(lap.get('swim_stroke'),'unknown');parts[key]=parts.get(key,0)+distance
        basis='Watch lap classification · distance proportions' if parts else 'Stroke classification unavailable in this file'
    out=mix(parts,session,basis)
    out['distance_mismatch']=bool(session and sum(parts.values())>session+max(1,(pool or 0)/2))
    return out

def response(a):
    s=a.get('session') or {};seconds=positive(s.get('total_timer_time')) or (positive(a.get('minutes')) or 0)*60
    average=positive(s.get('avg_heart_rate'))
    basis='Watch session average × recorded timer minutes (includes timer-running rests)'
    # Sparse HR samples do not represent the entire session. Do not bridge long gaps.
    observed=weighted=0
    recs=sorted((r for r in a.get('records',[]) if positive(r.get('hr')) and positive(r.get('t'))),key=lambda r:r['t'])
    for left,right in zip(recs,recs[1:]):
        gap=right['t']-left['t']
        if 0<gap<=10:
            observed+=gap;weighted+=(left['hr']+right['hr'])/2*gap
    if not average and observed:
        average=weighted/observed;basis='Time-weighted HR samples × observed minutes only; gaps over 10 seconds excluded'
    hr_minutes=seconds/60 if positive(s.get('avg_heart_rate')) else observed/60
    distance=positive(a.get('distance_m'))
    return {'duration_minutes':round(seconds/60,2),'distance_m':distance,'avg_hr':round(average,1) if average else None,
            'hr_time_bpm_min':round(average*hr_minutes,1) if average and hr_minutes else None,
            'hr_minutes':round(hr_minutes,2) if average else None,'hr_basis':basis if average else 'Heart rate unavailable',
            'hr_coverage_percent':round(min(100,observed/seconds*100),1) if seconds else None,
            'pace_per_100m_seconds':round(seconds/distance*100,1) if seconds and distance else None}

def profile(a):
    return {'watch_mix':watch_mix(a),'response':response(a)}

def history_rows(scored,d):
    """Uses the already cached work ledger; never rereads every watch file per card."""
    rows=[]
    for a in scored:
        if a.get('sport')!='swim' or not a.get('swim_analysis'):continue
        detail=d.get('activity_workouts',{}).get(a['id']) or {}
        recipe=detail.get('recipe');planned=(d.get('swim_timing_baselines',{}).get(a['id']) or {}).get('recipe');p=a['swim_analysis'];feedback=next((v for v in d.get('training_feedback',{}).values() if v.get('activity_id')==a['id']),{})
        written=recipe or planned
        written_basis='Recorded workout breakdown' if recipe else 'Saved planned workout' if planned else None
        rows.append({'activity_id':a['id'],'date':a['date'],'start':a.get('start'),'current':False,
                     'written_mix':recipe_mix(written,written_basis) if written else None,'written_basis':written_basis,
                     'watch_mix':p['watch_mix'],'planned_mix':recipe_mix(planned,'Saved plan captured at workout association') if planned else None,'described_mix':recipe_mix(recipe,'Athlete-described performed sets') if recipe else None,
                     'work_types':{'sets':[{'distance_m':s.get('distance_m',0),'work':s.get('work','swim')} for s in recipe.get('sets',[])]} if recipe else None,
                     'response':{**p['response'],'reported_effort':feedback.get('rpe')}})
    rows.sort(key=lambda r:(r['date'],r.get('start') or '',r['activity_id']))
    return rows

def history(scored,d,current_id):
    rows=history_rows(scored,d)
    for r in rows:r['current']=r['activity_id']==current_id
    # Show only history up to the selected workout, never compare an old record to its future.
    position=next((i for i,r in enumerate(rows) if r['current']),None)
    if position is None:return []
    cutoff=(date.fromisoformat(rows[position]['date'])-timedelta(days=89)).isoformat()
    return [r for r in rows[:position+1] if r['date']>=cutoff]


def dashboard(scored,d,as_of):
    """Recorded canonical swims only, with saved phase boundaries and no predictions."""
    date.fromisoformat(as_of)
    rows=[r for r in history_rows(scored,d) if r['date']<=as_of]
    phases=[{k:p.get(k) for k in ('id','label','start','end')} for p in d.get('phase_profiles',[]) if p.get('start') and p.get('end')]
    return {'as_of':as_of,'history_start':rows[0]['date'] if rows else None,'rows':rows,'phases':phases,
            'basis':'Imported canonical swim recordings; watch classification and athlete-described sets remain separate.'}
