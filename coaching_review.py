"""Read forecasts, compare calendar changes and review capacity; never biological clearance.

Policy thresholds (three observations, two-point report discrepancy, ten-percent
review step) are conservative product heuristics, not research-derived constants.
"""
import copy
import datetime as dt
import json
import secrets
import time
import zlib
import program_drafts

MIN_OBSERVATIONS = 3
REVIEW_STEP = .10


def _rem(load):
    return (((load.get('systems') or {}).get('impact') or {}).get('tissue') or {}).get('remodeling') or {}


def _latest(d, target):
    return next((r for r in reversed(d.get('capacity_adjustments', [])) if r['target']==target), {})


def _prediction(d, date, metric):
    # Use a prediction saved before the workout, never a newly generated historical forecast.
    for record in d.get('load_forecasts', {}).get(date, []):
        if record.get('saved_at', '')[:10] <= date:
            row=next((r for r in record['forecast']['metrics'] if r['key']==metric), {})
            if row.get('after') is not None:return row['after']
    return None


def outlook(d, load, done, workouts, today, days=14):
    import training_block as B, progression
    if not 1 <= days <= 14:raise ValueError('Outlook covers 1–14 days')
    dates=[(dt.date.fromisoformat(today)+dt.timedelta(days=n)).isoformat() for n in range(days)]
    rows=B.projected_loads(d,today,dates,load,done,workouts).values()
    summaries=[];daily=[]
    for row in rows:
        sessions=B.sessions(d.get('plans',{}).get(row['date']) or {})
        if not sessions:continue
        metrics=[{k:m.get(k) for k in ('key','before','after','limit','over_limit','session_dose','unit')} for m in row['metrics']]
        daily.append({'date':row['date'],'readings':metrics})
        run=next((m for m in metrics if m['key']=='run_mechanical'),{})
        strength=[m for m in metrics if m['key'].startswith('lift_')]
        for i,s in enumerate(sessions):
            if s['sport'] not in ('run','gym'):continue
            selected=[run] if s['sport']=='run' else strength
            unknown=not selected or any(m.get('after') is None for m in selected)
            conflicts=[m for m in selected if m.get('after') is not None and m.get('limit') is not None and m['after']>=m['limit']]
            summaries.append({'date':row['date'],'index':i,'sport':s['sport'],'name':s.get('name'),'minutes':s.get('minutes'),
                'context':progression.context(d,row['date'],s['sport'],s),'readings':selected,
                'status':'unknown' if unknown else 'conflict' if conflicts else 'within_projected_limits',
                'alternatives':['Shorten or reduce the scheduled dose','Move the exposure and recheck the following week','Replace affected work with an eligible activity or rest'] if conflicts else [],
                'meaning':'Readings include all work on this day; they are not isolated per-session measurements.'})
    gate=B.running_gate(d,load,d.get('checkins',{}).get(today))
    return {'as_of':today,'days':days,'sessions':summaries,'daily_readings':daily,'running_gate':gate,
            'active_symptoms':progression.active_symptoms(d,today),
            'running_progression':running_progression(d,load,today,daily,gate),
            'notice':'Check the entire sequence, including openers after peak work. Forecasts do not clear execution holds.'}


# Running load targets by phase, in blocks at the week's peak (the 1.5-block line is the hard limit). Provisional
# product policy: build steps the peak up to the band, then responses (mornings, hops, pace at heart rate) let the
# block itself learn and grow, so the same band holds more running.
RUN_TARGETS = {'assessment':(.6,1.0),'base':(.8,1.1),'build':(1.2,1.45),'peak':(1.2,1.45),'specific':(1.1,1.4),
               'taper':(.4,.9),'recovery':(0,.8)}


def running_progression(d, load, today, daily, gate):
    """Is the plan actually challenging running? The coming week's forecast peak against the phase's band."""
    import progression
    phase=progression.context(d,today,'run')['phase']
    band=RUN_TARGETS.get(phase)
    week_end=(dt.date.fromisoformat(today)+dt.timedelta(days=6)).isoformat()
    planned=[m['after'] for day in daily if day['date']<=week_end for m in day['readings'] if m['key']=='run_mechanical' and m.get('after') is not None]
    peak=round(max(planned),2) if planned else None
    since=(dt.date.fromisoformat(today)-dt.timedelta(days=14)).isoformat()
    rem=_rem(load)
    recent=[c['after_blocks'] for c in rem.get('components',[]) if since<=c['date']<today]
    learned=rem.get('block_learning') or []
    out={'phase':phase,'target_blocks':list(band) if band else None,'planned_week_peak_blocks':peak,
         'recent_peak_blocks':round(max(recent),2) if recent else None,'block_points':rem.get('reference_points'),
         'last_block_change':learned[-1] if learned else None,'status':None,'advice':None}
    if not band or phase=='recovery':
        out['status']='not_progressing';out['advice']='No running progression in this phase.'
    elif gate.get('status')!='open_for_review' or progression.active_symptoms(d,today):
        out['status']='held';out['advice']='Resolve the running hold or symptoms first; do not add running load.'
    elif peak is None:
        out['status']='no_runs_planned';out['advice']='No runs with a forecast this week.'
    elif peak<band[0]:
        out['status']='under_target'
        out['advice']=(f'The plan peaks at {peak} blocks; this {phase} phase targets {band[0]}-{band[1]}. Lengthen the long run or '
                       'add an easy run at least two days from the others, previewing until the forecast peak reaches the band. '
                       'Prefer one well-spaced step over several stacked runs. Check the next mornings, hop test and pace at heart '
                       'rate before the next step: clean responses let the block grow.')
    elif peak>band[1]:
        out['status']='over_target';out['advice']=f'The plan peaks at {peak} blocks, above the {phase} band: shorten or space runs.'
    else:
        out['status']='on_target';out['advice']='Running load is in the band. Hold it until the responses are clean, then step again.'
    return out


def capacity_candidates(d, load, today):
    import lifting, progression, journal
    symptoms=progression.active_symptoms(d,today)
    last_run=_latest(d,'running_block');rem=_rem(load)
    run_events=[]
    for a in sorted(load.get('activities',[]),key=lambda x:x.get('date','')):
        date=a.get('date','')
        if a.get('sport')!='run' or not last_run.get('date','')<date<today:continue
        expected=_prediction(d,date,'run_mechanical')
        if expected is None:continue
        reports=[journal.effective(d.get('checkins',{}).get((dt.date.fromisoformat(date)+dt.timedelta(days=n)).isoformat()) or {}) for n in (1,2)]
        if not all(c.get('feet') is not None and c.get('legs') is not None for c in reports):continue
        feedback=[e for e in d.get('training_feedback',{}).values() if e.get('date')==date and e.get('sport')=='run']
        bad=any(c[k]>=6 for c in reports for k in ('feet','legs')) or any(e.get('heart_rate_issue') or any(x.get('severity',0)>0 for x in e.get('symptoms',[])) for e in feedback)
        clean=all(c[k]<=3 for c in reports for k in ('feet','legs'))
        benchmark=(d.get('benchmarks',{}).get('runs',{}).get(date) or {})
        bad=bad or benchmark.get('pain',False) or any(c.get('hops') is not None and c['hops']<=3 for c in reports)
        graded=benchmark.get('result')=='review_candidate' and benchmark.get('block_after',0)>benchmark.get('block_before',0)
        easy=any(e.get('effort')=='too_easy' and e.get('context',{}).get('phase') in ('base','build') for e in feedback)
        race=any(e.get('kind')=='race' and e.get('sport') in ('run','tri') and e.get('date')==date for e in d.get('events',[]))
        clean=clean and not bad
        direction='decrease' if bad and expected<1.5 else 'increase' if clean and expected>=1.5 and (easy or race or graded) else None
        if graded and clean and not bad:direction='increase'
        if direction:run_events.append({'benchmark':bool(graded),'date':date,'direction':direction,'source':'graded benchmark plus recovery' if graded else 'competition plus recovery' if race else 'completed run plus delayed reports','expected_blocks':expected,'activity_id':a.get('id'),'minutes':a.get('minutes'),'km':a.get('km'),'avg_hr':a.get('avg_hr')})
    lift_events={}
    lift_state=lifting.state(copy.deepcopy(d))
    for log in lift_state['logs']:
        date=log['date']
        if date>=today:continue
        follow=lift_state['followups'].get(date) or {}
        if not (dt.date.fromisoformat(date)+dt.timedelta(days=lifting.FOLLOW_DAYS[0])).isoformat()<=follow.get('date','')<=today:continue
        for region,dose in log.get('regions',{}).items():
            if not dose or date<=_latest(d,'lift_'+region).get('date',''):continue
            predicted=_prediction(d,date,'lift_'+region);observed=follow.get('regions',{}).get(region)
            if predicted is None or observed is None:continue
            expected=lifting._predict(predicted)
            direction='increase' if observed<=3 and expected-observed>=2 else 'decrease' if observed>=6 and observed-expected>=2 else None
            if direction:lift_events.setdefault(region,[]).append({'date':date,'direction':direction,'source':'logged lifting plus regional follow-up','expected_rating':round(expected,1),'reported_rating':observed,'exercises':[{k:x.get(k) for k in ('name','weight','unit','sets','reps','tempo')} for x in log.get('lifts',[]) if region in x.get('regions',{})]})
    candidates=[]
    def append(target,events,reference,blocked):
        # Count dates, not multiple sessions/regions/reports on the same day.
        by_date={x['date']:x for x in events};events=list(by_date.values())[-6:]
        directions={x['direction'] for x in events}
        direction=next(iter(directions)) if len(directions)==1 else None
        enough=(len(events)>=MIN_OBSERVATIONS or target=='running_block' and any(x.get('benchmark') for x in events)) and direction is not None
        candidates.append({'target':target,'reference':reference,'observations':events,'direction':direction,
            'status':'blocked' if blocked else 'review_candidate' if enough and reference else 'more_evidence_needed',
            'reasons':blocked,'suggested_reference':round(reference*(1+REVIEW_STEP if direction=='increase' else 1-REVIEW_STEP),2) if reference and enough and not blocked else None,
            'recommendation':'Review a calibration session or test week when eligible; it may increase, retain or decrease capacity. Do not schedule a benchmark through a hold.'})
    blocked=[]
    current=journal.effective(d.get('checkins',{}).get(today) or {})
    if any(current.get(k) is not None and current[k]>=6 for k in ('feet','legs')) or current.get('hops') is not None and current['hops']<=3 or current.get('gut')=='no':
        blocked.append('Current readiness report does not support running capacity review')
    protected=load.get('run_progression')
    if protected and rem.get('phase')=='plateau':blocked.append('Protected recovery plateau: use the existing 60% review workflow; capacity cannot rescale it here')
    if any(set(s['regions']).intersection(lifting.LEG_REGIONS) for s in symptoms):blocked.append('Unresolved lower-body symptoms')
    append('running_block',run_events,rem.get('reference_points'),blocked)
    regions=(load.get('lifting') or {}).get('regions') or lifting.model(copy.deepcopy(d),dt.date.fromisoformat(today))['regions']
    for region in sorted(set(regions)|set(lift_events)):
        append('lift_'+region,lift_events.get(region,[]),regions.get(region,{}).get('reference'),['Unresolved regional symptoms'] if any(region in s['regions'] for s in symptoms) else [])
    return {'as_of':today,'candidates':candidates,'policy':{'minimum_distinct_dates':MIN_OBSERVATIONS,'review_step_fraction':REVIEW_STEP,'provisional':True},
            'meaning':'A strength estimate is not a recovery-capacity estimate. Competition without delayed recovery evidence cannot grow recovery blocks.'}


def with_capacity(d,load,today,base):
    """Recalculate the affected modeled readings without rewriting any recorded doses."""
    import lifting, loads, damage
    out=copy.deepcopy(load)
    out['lifting']=lifting.model(copy.deepcopy(d),dt.date.fromisoformat(today))
    latest=_latest(d,'running_block')
    if latest:
        days=out.get('days') or []
        if not days:raise ValueError('Running dose history is unavailable')
        prof=loads.load_profile(base)
        reports=d.get('checkins',{})
        rem=damage.remodeling_response([x['date'] for x in days],[x.get('sports',{}).get('run',{}).get('impact',0) for x in days],
            weight_kg=prof['weight_kg'],feet_reports=reports,walking=loads.walking_inputs(out.get('activities',[]),loads.load_steps(base),prof),
            block=latest['reference'],reviews=(d.get('run_progression') or {}).get('reviews',[]))
        if not rem:raise ValueError('Running history cannot be recalculated')
        out['systems']['impact']['tissue']['remodeling']=rem
        if out.get('run_progression'):
            import recovery
            out['run_progression']=recovery.status(d,rem,today)
    return out


def _store(base,payload,revision):
    db=program_drafts.connect(base)
    token=secrets.token_urlsafe(24);expires=time.time()+program_drafts.TTL_SECONDS
    try:
        db.execute('CREATE TABLE IF NOT EXISTS coaching_reviews (id TEXT PRIMARY KEY, revision TEXT, expires REAL, payload BLOB)')
        db.execute('DELETE FROM coaching_reviews WHERE expires < ?',(time.time(),))
        db.execute('INSERT INTO coaching_reviews VALUES (?,?,?,?)',(token,revision,expires,zlib.compress(json.dumps(payload,allow_nan=False).encode())))
        db.execute('DELETE FROM coaching_reviews WHERE id NOT IN (SELECT id FROM coaching_reviews ORDER BY expires DESC LIMIT 8)');db.commit()
    finally:db.close()
    return {**payload,'draft_id':token,'expires_at':dt.datetime.fromtimestamp(expires,dt.timezone.utc).isoformat()}


def preview(d,load,done,workouts,today,base,revision,fields):
    import coach, training_block as B
    candidate=copy.deepcopy(d);kind=fields.get('kind')
    if kind=='capacity':
        target=fields.get('target');row=next((c for c in capacity_candidates(d,load,today)['candidates'] if c['target']==target),None)
        if not row or row['status']!='review_candidate':raise ValueError('Capacity needs repeated matched evidence and no protected restrictions before review')
        record={'target':target,'date':today,'reference':row['suggested_reference'],'before':row['reference'],'direction':row['direction'],'evidence':row['observations'],'note':str(fields.get('note') or '')[:1000]}
        candidate.setdefault('capacity_adjustments',[]).append(record)
        adjusted=with_capacity(candidate,load,today,base)
        payload={'kind':kind,'record':record,'before':outlook(d,load,done,workouts,today),'after':outlook(candidate,adjusted,done,workouts,today),
            'notice':'Capacity is a reviewed estimate. Existing doses, snapshots, plateau reviews and personal minimum waits are retained; forecast changes do not clear running.'}
    elif kind=='calendar':
        changes=fields.get('changes')
        if not isinstance(changes,list) or not 1<=len(changes)<=14:raise ValueError('Give 1–14 day replacements')
        seen=set();originals=[]
        for change in changes:
            date=change['date'];dt.date.fromisoformat(date)
            if not today<=date<=(dt.date.fromisoformat(today)+dt.timedelta(days=13)).isoformat() or date in seen:raise ValueError('Choose distinct dates within the next 14 days')
            if done.get(date):raise ValueError('Completed days cannot be rewritten')
            seen.add(date);originals.append({'date':date,'sessions':copy.deepcopy(B.sessions(d.get('plans',{}).get(date) or {}))})
            coach.set_sessions(candidate,date,change['sessions'])
            candidate['plans'][date].pop('test',None)
        after=outlook(candidate,load,done,workouts,today)
        gate=after['running_gate'];violations=[]
        # A hold from recent running load alone clears on the model's own projection: it blocks runs before that
        # date (later runs still face their forecast). Symptoms, hop tests, readiness or the return-to-run protocol
        # block every run in the window.
        load_only=bool(gate.get('reasons')) and all(str(r).startswith('mechanical running load') for r in gate['reasons'])
        clear_by=(dt.date.fromisoformat(today)+dt.timedelta(days=int(gate['model_days']))).isoformat() if load_only and gate.get('model_days') is not None else None
        for row in after['sessions']:
            if row['date'] not in seen:continue
            if row['status']!='within_projected_limits':violations.append(row['date']+': '+str(row['name'])+' has unknown or excessive projected load')
            if row['sport']=='run' and gate['status']!='open_for_review' and (clear_by is None or row['date']<clear_by):violations.append(row['date']+': current running hold remains in force'+(f' (projected to clear {clear_by})' if clear_by else ''))
            if any(__import__('progression').affected(s,[symptom]) for symptom in after['active_symptoms'] for s in B.sessions(candidate['plans'][row['date']])):violations.append(row['date']+': unresolved symptom overlap')
        # Flag newly introduced or worsened limit breaches across all sports, including later days.
        before=outlook(d,load,done,workouts,today)
        prior={(day['date'],m['key']):m for day in before['daily_readings'] for m in day['readings']}
        for day in after['daily_readings']:
            for m in day['readings']:
                old=prior.get((day['date'],m['key']),{})
                if m.get('after') is not None and m.get('limit') is not None and m['after']>=m['limit'] and (old.get('after') is None or m['after']>old['after']+.005):
                    violations.append(day['date']+': worsened '+m['key']+' forecast limit')
        for row in after['sessions']:
            if row['status']=='conflict':violations.append(row['date']+': remaining '+str(row['name'])+' conflict in reviewed sequence')
        payload={'kind':kind,'changes' :[{'date':c['date'],'sessions':copy.deepcopy(B.sessions(candidate['plans'][c['date']]))} for c in changes],'original':originals,
            'before':before,'after':after,'violations':sorted(set(violations)),
            'notice':'Review the whole 14-day sequence. Holds, unknown loads and symptom overlap block Apply; compare shortening, spacing, substitutions or rest.'}
    else:raise ValueError('Review kind is calendar or capacity')
    return _store(base,payload,revision)


def apply(d,base,revision,today,draft_id,approved):
    import coach
    if approved is not True:raise ValueError('Explicit athlete approval is required')
    db=program_drafts.connect(base)
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS coaching_reviews (id TEXT PRIMARY KEY, revision TEXT, expires REAL, payload BLOB)')
        row=db.execute('SELECT revision,expires,payload FROM coaching_reviews WHERE id=?',(draft_id,)).fetchone()
        if not row:raise program_drafts.Conflict('Review unavailable; preview again')
        payload=json.loads(zlib.decompress(row[2]))
        receipt=next((r for r in d.get('coaching_review_receipts',[]) if r['draft_id']==draft_id),None)
        if receipt:db.commit();return {**receipt,'already_applied':True}
        if row[1]<time.time() or row[0]!=revision:raise program_drafts.Conflict('Review expired or athlete data changed; preview again')
        if payload.get('violations'):raise ValueError('Resolve forecast, hold and symptom violations before applying')
        if payload['kind']=='calendar':
            for c in payload['changes']:
                coach.set_sessions(d,c['date'],c['sessions'])
                d['plans'][c['date']].pop('test',None)
        else:d.setdefault('capacity_adjustments',[]).append(copy.deepcopy(payload['record']))
        receipt={'draft_id':draft_id,'kind':payload['kind'],'date':today,'proposal_hash':program_drafts.digest(payload)}
        d['coaching_review_receipts']=(d.get('coaching_review_receipts',[])+[receipt])[-8:]
        coach.save(d);db.commit()
        return {**receipt,'already_applied':False,'verify':'Re-read coaching review outlook and saved calendar; no running clearance was issued.'}
    except Exception:db.rollback();raise
    finally:db.close()
