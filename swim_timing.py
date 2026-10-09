"""Deterministic swim timing: distance/order alignment, no invented set splits.

Times never decide which watch segment matches a target: that would bias the grade.
Coarse watch segments are compared as combined blocks, not divided by planned time.
"""
import copy
import datetime as dt
import math
import statistics


def positive(v):
    return isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) and v > 0


def blocks(recipe):
    out = []
    for i, s in enumerate(recipe.get('sets', [])):
        # Consecutive drills may be one continuous watch drill-mode block.
        if out and s['work'] == 'drill' and out[-1]['work'] == 'drill' and s['section'] == out[-1]['section']:
            out[-1]['sets'].append(s); out[-1]['indices'].append(i)
        else:
            out.append({'sets': [s], 'indices': [i], 'work': s['work'], 'section': s['section']})
    return out


def segments(a):
    pool = a.get('pool_length_m')
    lengths = a.get('swim_lengths') or []
    laps = [l for l in a.get('laps', []) if positive(l.get('total_distance'))]
    total = a.get('distance_m') or 0
    tolerance = max(1, (pool or 25) * .05)
    def length_rows(items):
        return [{'distance_m': pool, 'seconds': x.get('total_timer_time'), 'stroke': x.get('swim_stroke'),
                 'basis': 'Watch active length time'} for x in items if x.get('length_type') == 1]
    active = [x for x in lengths if x.get('length_type') == 1]
    if positive(pool) and active and abs(len(active)*pool-total) <= tolerance:
        return length_rows(active), None
    if laps and abs(sum(l['total_distance'] for l in laps)-total) <= tolerance:
        rows = []
        for lap in laps:
            first, count = lap.get('first_length_index'), lap.get('num_lengths')
            inside = lengths[first:first+count] if isinstance(first,int) and isinstance(count,int) else []
            chosen = [x for x in inside if x.get('length_type') == 1]
            # A drill lap can represent distance not resolved by individual lengths.
            if positive(pool) and chosen and abs(len(chosen)*pool-lap['total_distance']) <= tolerance:
                rows.extend(length_rows(chosen))
            else:
                rows.append({'distance_m': lap['total_distance'], 'seconds': lap.get('total_timer_time'),
                             'stroke': lap.get('swim_stroke'), 'basis': 'Watch lap timer; may include timer-running rests'})
        return rows, None
    return [], 'The watch has no complete distance-resolved lengths or laps. Set times need review; session duration is not divided into guessed set times.'


def grade(actual, goal, expected):
    if not all(positive(v) for v in (actual, goal, expected)): return None
    return {'status': 'At goal' if actual <= goal else 'As or better than expected' if actual <= expected else 'Slower than expected',
            'seconds_vs_expected': round(expected-actual, 1), 'percent_vs_expected': round((expected-actual)/expected*100, 1),
            'seconds_to_goal': round(max(0,actual-goal), 1), 'percent_over_goal': round((actual-goal)/goal*100, 1),
            'goal_progress_pct': round((expected-actual)/(expected-goal)*100, 1) if expected > goal else None}


def compare(recipe, a):
    planned = blocks(recipe); observed, issue = segments(a)
    result = {'rows': [], 'actual_seconds':None, 'grade':None, 'issues': [], 'basis': 'Watch distance and workout order; timing targets do not influence matching.',
              'goal_seconds': recipe.get('completion_goal_minutes',0)*60 if recipe.get('all_completion_timed') else None,
              'expected_seconds': recipe.get('completion_expected_minutes',0)*60 if recipe.get('all_completion_timed') else None}
    tolerance = max(1, (a.get('pool_length_m') or 25)*.05)
    if issue: result['issues'].append(issue)
    if abs((a.get('distance_m') or 0)-recipe.get('total_distance_m',0)) > tolerance:
        result['issues'].append('Recorded and planned distances differ. Review missing, extra or partial sets before assigning set grades.')
    if result['issues']:
        result['rows'] = [row(b['sets'],b['indices'],[],True) for b in planned]
        return result
    i=j=0
    while i<len(planned) and j<len(observed):
        ss=list(planned[i]['sets']);indices=list(planned[i]['indices']);oo=[observed[j]];i+=1;j+=1
        pd=sum(s['distance_m'] for s in ss);od=oo[0]['distance_m']
        # Find the next shared distance boundary. No separator or drill is required.
        while abs(pd-od)>tolerance:
            if pd<od and i<len(planned):
                ss.extend(planned[i]['sets']);indices.extend(planned[i]['indices']);pd+=sum(s['distance_m'] for s in planned[i]['sets']);i+=1
            elif od<pd and j<len(observed):
                oo.append(observed[j]);od+=observed[j]['distance_m'];j+=1
            else:break
        review=abs(pd-od)>tolerance
        styles={s['stroke'] for s in ss};work={s['work'] for s in ss}
        codes={0:'free',1:'back',2:'breast',3:'fly'}
        detected={codes.get(o['stroke'],'drill' if o['stroke']==4 else 'unknown') for o in oo}
        if work=={'drill'}:review |= not detected <= {'drill','unknown'}
        elif 'choice' not in styles and 'medley' not in styles:
            review |= not detected <= styles | {'unknown'}
        result['rows'].append(row(ss,indices,oo,review))
    if i<len(planned) or j<len(observed): result['issues'].append('Not all set boundaries could be aligned.')
    reliable=all(not r['needs_review'] and r['actual_seconds'] is not None for r in result['rows']) and not result['issues']
    actual=sum(r['actual_seconds'] for r in result['rows']) if reliable else None
    result['actual_seconds']=actual
    result['grade']=grade(actual,result['goal_seconds'],result['expected_seconds'])
    return result


def row(ss, indices, observed, review):
    timed=all(positive(o.get('seconds')) for o in observed)
    actual=round(sum(o['seconds'] for o in observed),1) if observed and timed else None
    goal=sum(s['goal_seconds'] for s in ss) if all(positive(s.get('goal_seconds')) for s in ss) else None
    expected=sum(s['expected_seconds'] for s in ss) if all(positive(s.get('expected_seconds')) for s in ss) else None
    return {'set_indices':indices,'label':' + '.join(f"{s['repetitions']*s['distance']:g} {s['unit']} {s['description']}" for s in ss),
            'distance_m':round(sum(s['distance_m'] for s in ss),4),'goal_seconds':goal,'expected_seconds':expected,
            'actual_seconds':actual,'needs_review':bool(review or actual is None),'combined':len(indices)>1,
            'basis':' + '.join(sorted({o['basis'] for o in observed})) or 'Not matched',
            'grade':None if review else grade(actual,goal,expected),
            'signature':signature(ss) if len(ss)==1 else None}


def signature(ss):
    s=ss[0]
    return f"{s['distance_m']:.2f}|{s['stroke']}|{s['work']}|{','.join(sorted(s.get('equipment') or []))}"


def capture(d, ident, recipe, date, index):
    snapshots=d.setdefault('swim_timing_baselines',{})
    old=snapshots.get(ident)
    if old and old['date']==date and old['session_index']==index:return
    if old:d.setdefault('swim_timing_baseline_history',[]).append(copy.deepcopy(old))
    snapshots[ident]={'activity_id':ident,'date':date,'session_index':index,'recipe':copy.deepcopy(recipe),
                      'captured_at':dt.datetime.now().isoformat(timespec='seconds'),'basis':'Saved plan captured at workout association'}


def recipe_for(d, a, actual=None):
    saved=d.get('swim_timing_baselines',{}).get(a['id'])
    if saved:return saved['recipe'],saved['basis']
    import coach,training_block
    date=dt.date.fromtimestamp(a['start']).isoformat()
    sessions=training_block.sessions(d.get('plans',{}).get(date) or {})
    done=(actual or {}).get(date) or [{'activity_id':a['id'],'sport':'swim','minutes':a.get('minutes',0)}]
    marked=coach.attach_completions(d,date,copy.deepcopy(sessions),done)
    for s in marked:
        if s.get('completion',{}).get('activity_id')==a['id'] and s.get('swim_recipe'):
            return s['swim_recipe'],'Current saved plan; no earlier association snapshot'
    return None,None


def remember(d,a,recipe):
    result=compare(recipe,a)
    d.setdefault('swim_timing_history',{})[a['id']]={'date':dt.date.fromtimestamp(a['start']).isoformat(),
        'pool_length_m':a.get('pool_length_m'),'rows':result['rows']}
    return result


def suggestions(recipe,d):
    out=[]
    for i,s in enumerate(recipe.get('sets',[])):
        if s.get('goal_seconds') is not None:continue
        key=signature([s]);values=[]
        for ident,h in sorted(d.get('swim_timing_history',{}).items(),key=lambda x:x[1]['date'],reverse=True)[:30]:
            pool=recipe.get('pool_length')
            if pool and abs(pool*(.9144 if recipe['unit']=='yd' else 1)-(h.get('pool_length_m') or 0))>.5:continue
            times=[r['actual_seconds'] for r in h['rows'] if r.get('signature')==key and not r['needs_review'] and positive(r.get('actual_seconds'))]
            if times:values.append(statistics.median(times))
        if len(values)>=3:
            values=values[:10];out.append({'set_index':i,'recent_best_seconds':min(values),'expected_seconds':round(statistics.median(values),1),
                'source_text':s.get('source_text'),'section':s['section'],'performances':len(values),'basis':'Recent matched sets of the same distance, stroke, work and equipment. Suggestions require review; recent best is not an assigned goal.'})
    return out


def save_splits(d,a,recipe,splits):
    """Athlete recall is separate evidence, never replacement watch measurements."""
    if not isinstance(splits,list) or len(splits)>100:raise ValueError('Provide at most 100 drill split entries')
    saved={};seen=set()
    for item in splits:
        if not isinstance(item,dict):raise ValueError('Each split needs a set_index and seconds')
        i=item.get('set_index');seconds=item.get('seconds')
        if isinstance(i,bool) or not isinstance(i,int) or not 0<=i<len(recipe['sets']) or i in seen:raise ValueError('Choose a distinct set in this workout')
        seen.add(i)
        if recipe['sets'][i]['work']!='drill':raise ValueError('Optional split recall is for drill sets')
        if seconds is None:continue
        if not positive(seconds) or seconds>36000:raise ValueError('Split time must be positive seconds, up to 10 hours')
        saved[str(i)]={'seconds':seconds,'source':'Athlete-reported drill split','recorded_at':dt.datetime.now().isoformat(timespec='seconds'),'signature':signature([recipe['sets'][i]])}
    d.setdefault('swim_reported_splits',{})[a['id']]=saved
    return reported_splits(d,a,recipe)


def reported_splits(d,a,recipe):
    saved=d.get('swim_reported_splits',{}).get(a['id'],{});out=[]
    for i,s in enumerate(recipe['sets']):
        if s['work']!='drill':continue
        v=saved.get(str(i),{})
        actual=v.get('seconds') if v.get('signature')==signature([s]) else None
        out.append({'set_index':i,'label':f"Set {i+1}: {s['repetitions']*s['distance']:g} {s['unit']} {s['description']}",
                    'actual_seconds':actual,'grade':grade(actual,s.get('goal_seconds'),s.get('expected_seconds')),
                    'source':'Athlete-reported drill split; watch block unchanged'})
    return out
