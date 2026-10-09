"""Explicit watch-to-workout association. Source files stay immutable.

The same preview/save operation serves the manual UI and MCP. Timestamps remain
absolute unless the athlete explicitly supplies a clock offset.
"""
import bisect
import copy
import datetime as dt
import math


def sport(a):
    return {'ride': 'bike'}.get(a.get('sport'), a.get('sport'))


def brief(a):
    return {'id': a['id'], 'source': a['source'], 'sport': a['sport'],
            'date': dt.date.fromtimestamp(a['start']).isoformat(),
            'start': dt.datetime.fromtimestamp(a['start']).isoformat(timespec='seconds'),
            'minutes': round(a['minutes'], 2), 'distance_m': a.get('distance_m', 0)}


def interval(a):
    ts = [r['t'] for r in a.get('records', [])]
    return (min(ts), max(ts)) if ts else (a['start'], a['start'] + a['minutes'] * 60)


def merge(target, watch, offset):
    """Bike timestamps/power/cadence win; nearest watch sample <=2s supplies HR.
    No interpolation over gaps, no extension of the target's work timeline.
    """
    out = copy.deepcopy(target)
    source = sorted(watch.get('records', []), key=lambda r: r['t'])
    times = [r['t'] + offset for r in source]
    matched = 0
    filled = set()
    for r in out.get('records', []):
        i = bisect.bisect_left(times, r['t'])
        near = [j for j in (i-1, i) if 0 <= j < len(times)]
        j = min(near, key=lambda j: abs(times[j]-r['t'])) if near else None
        if j is None or abs(times[j]-r['t']) > 2: continue
        w = source[j]
        if w.get('hr') is not None:
            r['hr'] = w['hr']; matched += 1
        for key, value in w.items():
            if key != 't' and r.get(key) is None and value is not None:
                r[key] = value; filled.add(key)
    session = copy.deepcopy(watch.get('session') or {})
    session.update(target.get('session') or {})
    session['total_timer_time'] = target['minutes'] * 60
    # HR summaries describe the overlap, not a longer watch recording.
    hrs = [r['hr'] for r in out.get('records', []) if r.get('hr') is not None]
    for key in ('avg_heart_rate', 'max_heart_rate', 'avg_power', 'max_power', 'normalized_power', 'avg_cadence', 'total_work'):
        session.pop(key, None)
    if hrs: session.update(avg_heart_rate=sum(hrs)/len(hrs), max_heart_rate=max(hrs))
    watts = [r['w'] for r in out.get('records', []) if r.get('w') is not None]
    cadence = [r['rpm'] for r in out.get('records', []) if r.get('rpm') is not None]
    if watts:
        session.update(avg_power=sum(watts)/len(watts), max_power=max(watts))
        records=out.get('records',[])
        session['total_work']=sum(max(0,r.get('w') or 0)*max(0,min(2,n['t']-r['t'])) for r,n in zip(records,records[1:]))
    if cadence: session['avg_cadence'] = sum(cadence)/len(cadence)
    out['session'] = session
    out['source'] = 'linked'
    out['recording_sources'] = [brief(target), brief(watch)]
    out['recording_alignment'] = {'offset_seconds': offset, 'matched_hr_samples': matched,
                                 'timeline_samples': len(out.get('records', [])), 'tolerance_seconds': 2,
                                 'basis': 'Recorded timestamps plus explicitly saved watch offset'}
    out['metric_sources'] = {'power': target['source']+(' + watch fallback' if 'w' in filled else ''), 'cadence': target['source']+(' + watch fallback' if 'rpm' in filled else ''), 'heart_rate': 'watch' if matched else 'No aligned watch HR',
                            'calories': 'watch total, may include time outside the linked timeline'}
    return out


def apply(activities, links):
    """Return canonical activities and remove only explicitly merged sources."""
    by_id = {a['id']: copy.deepcopy(a) for a in activities}
    removed = set()
    for ident, link in links.items():
        if ident not in by_id: continue
        if link.get('target_activity_id'):
            target = by_id.get(link.get('target_activity_id'))
            if not target: continue
            merged = merge(target, by_id[ident], link.get('offset_seconds', 0))
            merged['workout_link'] = copy.deepcopy(link)
            by_id[target['id']] = merged; removed.add(ident)
        else:
            by_id[ident].setdefault('workout_link', copy.deepcopy(link))
    return [a for ident, a in by_id.items() if ident not in removed]


def choices(base, d, ident=None):
    import loads
    raw = loads.gather(base/'activities', base/'rides', raw=True)
    watches = sorted((a for a in raw if a['source'] == 'watch'), key=lambda a: a['start'], reverse=True)
    links = d.get('recording_links', {})
    if ident is None:
        return {'activities': [{**brief(a), 'link': links.get(a['id'])} for a in watches]}
    activity = next((a for a in watches if a['id'] == ident), None)
    if not activity: raise ValueError('Choose an imported watch workout')
    current = links.get(ident)
    canonical = {a['id']: a for a in apply(raw, links)}
    candidates = []
    for a in canonical.values():
        if a['id'] == ident or sport(a) != sport(activity): continue
        if dt.date.fromtimestamp(a['start']) != dt.date.fromtimestamp(activity['start']): continue
        if a.get('source') == 'linked' and (not current or current.get('target_activity_id') != a['id']): continue
        start, end = interval(a); s, e = interval(activity)
        overlap = max(0, min(end,e)-max(start,s))
        candidates.append({**brief(a), 'name': d.get('activity_workouts',{}).get(a['id'],{}).get('name') or 'Recorded '+a['sport'],
                           'overlap_seconds': round(overlap), 'start_difference_seconds': round(a['start']-activity['start']),
                           'suggested': overlap >= min(a['minutes'], activity['minutes']) * 30})
    candidates.sort(key=lambda a: (not a['suggested'], abs(a['start_difference_seconds'])))
    date = dt.date.fromtimestamp(activity['start']).isoformat()
    plan = d.get('plans',{}).get(date) or {}
    sessions = plan.get('sessions') or ([plan] if plan.get('sport') else [])
    scheduled = [{'date':date,'session_index':i,'name':s.get('name') or s['sport'],
                  'sport':s['sport'],'minutes':s.get('minutes'), 'already_linked':bool(s.get('recorded_activity_id'))}
                 for i,s in enumerate(sessions) if sport(s)==sport(activity) and not s.get('skipped_id')]
    return {'activity':brief(activity),'current':current,'recorded':candidates,'scheduled':scheduled,
            'default_offset_seconds':0, 'new_workout_date':date}


def select(base, d, req):
    import loads
    mode = req.get('mode'); ident = req.get('activity_id')
    if mode not in ('activity','scheduled','new'): raise ValueError('Choose a recorded workout, scheduled workout or new workout')
    raw = loads.gather(base/'activities', base/'rides', raw=True)
    source = next((a for a in raw if a['id']==ident and a['source']=='watch'),None)
    if not source: raise ValueError('Choose an imported watch workout')
    if req.get('save') is not None and not isinstance(req['save'],bool): raise ValueError('save must be true or false')
    offset = req.get('offset_seconds',0)
    if isinstance(offset,bool) or not isinstance(offset,(int,float)) or not math.isfinite(offset) or abs(offset)>86400:
        raise ValueError('Clock offset must be seconds between -86400 and 86400')
    date = dt.date.fromtimestamp(source['start']).isoformat()
    link = {'mode':mode,'date':date,'offset_seconds':offset,'at':dt.datetime.now().isoformat(timespec='seconds')}
    proposal = copy.deepcopy(d); links=proposal.setdefault('recording_links',{})
    # A canonical target must not already feed into another recording or own a different watch.
    target_id=req.get('target_activity_id')
    if any(v.get('target_activity_id')==ident for k,v in links.items() if k!=ident):
        raise ValueError('This watch recording is already the target of another link')
    if mode=='new' and target_id:raise ValueError('A new separate workout cannot also merge another recording')
    if mode=='activity' or target_id:
        target=next((a for a in raw if a['id']==target_id),None)
        if not target or target_id==ident or sport(target)!=sport(source): raise ValueError('Choose a different recording of the same sport')
        if links.get(target_id,{}).get('target_activity_id') or any(v.get('target_activity_id')==target_id for k,v in links.items() if k!=ident):
            raise ValueError('This workout is already linked to another recording')
        annotations=proposal.get('activity_workouts',{})
        if annotations.get(ident) and annotations.get(target_id) and links.get(ident,{}).get('target_activity_id')!=target_id:raise ValueError('Both recordings have workout details. Review them before combining.')
        reports=proposal.get('training_feedback',{})
        if any(v.get('activity_id')==ident for v in reports.values()) and any(v.get('activity_id')==target_id for v in reports.values()):raise ValueError('Both recordings have session reports. Review them before combining.')
        if dt.date.fromtimestamp(target['start']).isoformat()!=date:raise ValueError('Choose another recording on the watch workout date')
        logs=(proposal.get('lifting') or {}).get('logs',[])
        if any(l.get('source_activity_id')==ident for l in logs) and any(l.get('source_activity_id')==target_id for l in logs):raise ValueError('Both recordings have lifting logs. Review them before combining.')
        s,e=interval(source);t,u=interval(target)
        if min(e+offset,u)-max(s+offset,t)<10: raise ValueError('The recordings do not overlap. Review their times and clock offset.')
        link['target_activity_id']=target_id; canonical_id=target_id
    else: canonical_id=ident
    old_canonical=links.get(ident,{}).get('target_activity_id') or ident
    old_schedule=links.get(ident,{}).get('session_index')
    # Remove an old explicit schedule association when moving this watch recording.
    for p in proposal.get('plans',{}).values():
        for s in p.get('sessions') or ([p] if p.get('sport') else []):
            if s.get('recorded_activity_id')==ident or (old_schedule is not None and s.get('recorded_activity_id')==old_canonical): s.pop('recorded_activity_id')
    if mode=='scheduled' or (mode=='activity' and req.get('session_index') is not None):
        index=req.get('session_index'); chosen_date=req.get('date') or date
        if chosen_date!=date: raise ValueError('Choose a workout on the watch recording date')
        p=proposal.get('plans',{}).get(date) or {};ss=p.get('sessions') or ([p] if p.get('sport') else [])
        if isinstance(index,bool) or not isinstance(index,int) or not 0<=index<len(ss):raise ValueError('Scheduled workout no longer exists; refresh the choices')
        session=ss[index]
        if session.get('skipped_id') or sport(session)!=sport(source):raise ValueError('Choose an active scheduled workout of the same sport')
        if session.get('recorded_activity_id') not in (None,ident,canonical_id):raise ValueError('That scheduled workout already has a linked recording')
        session['recorded_activity_id']=canonical_id;link['mode']='scheduled';link['session_index']=index;link['name']=session.get('name') or session['sport']
        if sport(source)=='swim' and session.get('swim_recipe'):
            import swim_timing
            swim_timing.capture(proposal,canonical_id,session['swim_recipe'],date,index)
    if target_id:
        details=proposal.setdefault('activity_workouts',{})
        if ident in details and target_id not in details:details[target_id]=copy.deepcopy(details[ident])
    reports=proposal.get('training_feedback',{})
    for key,report in list(reports.items()):
        follows_source=report.get('activity_id')==ident or report.get('source_activity_id')==ident
        follows_schedule=link.get('session_index') is not None and report.get('activity_id')==canonical_id
        if not (follows_source or follows_schedule):continue
        destination=date+':'+str(link['session_index']) if link.get('session_index') is not None else 'activity:'+canonical_id
        if destination!=key and destination in reports:raise ValueError('The destination already has a session report. Review the reports before linking.')
        if destination!=key or report.get('activity_id')!=canonical_id:
            proposal.setdefault('recording_link_report_history',[]).append({'old_key':key,'new_key':destination,'report':copy.deepcopy(report)})
        if follows_source:report.setdefault('source_activity_id',ident)
        report['activity_id']=canonical_id;report['session_index']=link.get('session_index')
        reports.pop(key);reports[destination]=report
    for log in (proposal.get('lifting') or {}).get('logs',[]):
        if log.get('source_activity_id')==ident or log.get('recording_source_activity_id')==ident:
            log.setdefault('recording_source_activity_id',ident);log['source_activity_id']=canonical_id
    links[ident]=link
    result=next(a for a in apply(raw,links) if a['id']==canonical_id)
    if sport(result)=='swim':
        import swim_timing
        recipe,_=swim_timing.recipe_for(proposal,result)
        if recipe:swim_timing.remember(proposal,result,recipe)
    if req.get('save') is True:
        # There is one coach transaction; this function has no file-writing side effects.
        d.clear();d.update(proposal)
    return {'saved':req.get('save') is True,'activity_id':ident,'canonical_activity_id':canonical_id,
            'link':link,'workout':brief(result),'recording_sources':result.get('recording_sources',[brief(result)]),
            'measurements':{k:v for k,v in (result.get('session') or {}).items() if k in (('avg_heart_rate','max_heart_rate','avg_power','avg_cadence') if sport(result)=='bike' else ('avg_heart_rate','max_heart_rate'))},
            'alignment':result.get('recording_alignment'), 'metric_sources':result.get('metric_sources'),
            'note':'Counted once. Original recording files are unchanged.'}
