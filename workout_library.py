"""Reusable prescriptions and dated workout briefs. Neither is completed activity.

Goals describe requested work; weights, energy and distance are separate quantities.
Responses link to the original logs rather than copying them into a second load record.
"""
import copy
import datetime as dt
import hashlib
import json
import math
import re
import uuid

SPORTS = ('gym', 'swim', 'ride', 'run', 'walk', 'other')
GOALS = {
    'gym': {'weight_moved': (1, 1000000), 'minutes': (1, 600)},
    'swim': {'distance': (25, 30000), 'minutes': (1, 600)},
    'ride': {'minutes': (1, 600), 'distance_km': (.1, 500), 'power_low': (20, 1500), 'power_high': (20, 1500),
             'cadence_low': (30, 200), 'cadence_high': (30, 200), 'energy_kcal': (1, 10000)},
    'run': {'minutes': (1, 600), 'distance_km': (.1, 100), 'steps': (1, 200000), 'zone': (1,5), 'hr_low': (30,240), 'hr_high': (30,240)},
    'walk': {'minutes': (1, 600), 'distance_km': (.1, 100)},
    'other': {'minutes': (1, 600)},
}
TEMPLATE_KEYS = ('sport', 'name', 'minutes', 'note', 'steps', 'lifts', 'typed_workout', 'swim_recipe', 'run_recipe', 'swim_plan', 'swim_profile', 'bike_plan', 'route_id', 'workout', 'cadence', 'focus', 'workout_goals')

def now():
    return dt.datetime.now().isoformat(timespec='seconds')

def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{32}', value):
        raise ValueError('Invalid workout library or goal ID')
    return value

def clean_goals(sport, goals):
    if sport not in SPORTS or not isinstance(goals, dict):
        raise ValueError('Choose a sport and provide workout goals')
    unknown = set(goals) - set(GOALS[sport]) - {'unit', 'power_scope'}
    if unknown:
        raise ValueError('Unknown goal fields: ' + ', '.join(sorted(unknown)))
    out = {}
    for key, bounds in GOALS[sport].items():
        value = goals.get(key)
        if value in (None, ''):
            continue
        if isinstance(value, bool):
            raise ValueError('Goal values must be numbers')
        value = float(value)
        if not math.isfinite(value) or not bounds[0] <= value <= bounds[1]:
            raise ValueError(f'{key} must be between {bounds[0]:g} and {bounds[1]:g}')
        out[key] = value
    if not out:
        raise ValueError('Enter at least one workout goal')
    if sport == 'gym':
        out['unit'] = goals.get('unit', 'lb')
        if out['unit'] not in ('lb', 'kg'):
            raise ValueError('Choose pounds or kilograms')
    if sport == 'swim':
        import swim_workouts
        out['unit'] = swim_workouts.unit(goals.get('unit', 'yd'))
    if sport == 'ride':
        if ('power_low' in out) != ('power_high' in out):
            raise ValueError('Enter both ends of the power range')
        if out.get('power_low', 0) > out.get('power_high', 1500):
            raise ValueError('The power range must go from lower to higher watts')
        if ('cadence_low' in out) != ('cadence_high' in out):
            raise ValueError('Enter both ends of the cadence range')
        if out.get('cadence_low', 0) > out.get('cadence_high', 200):
            raise ValueError('The cadence range must go from lower to higher rpm')
        out['power_scope'] = goals.get('power_scope', 'main')
        if out['power_scope'] not in ('main', 'session'):
            raise ValueError('Power goals cover main work or the whole session')
    if sport=='run':
        if any(k in out and out[k]!=int(out[k]) for k in ('steps','zone')):raise ValueError('Steps and zone must be whole numbers')
        if ('hr_low' in out)!=('hr_high' in out) or out.get('hr_low',0)>out.get('hr_high',240):raise ValueError('Enter an ordered heart-rate range')
    return out

def strength_totals(lifts):
    kg = 0.0
    seconds = 0.0
    missing_weight = []
    estimated_tempo = False
    sections = {key: 0.0 for key in ('warmup', 'main', 'cooldown')}
    for x in lifts or []:
        if x.get('done') is False:
            continue
        count = float(x.get('sets') or 0) * (2 if x.get('per_side') else 1)
        reps = float(x.get('reps') or 0)
        weight = x.get('weight')
        moved = 0
        if reps:
            if weight is not None:
                moved = count * reps * float(weight) * (1 if x.get('unit') == 'kg' else .45359237)
                kg += moved
            elif x.get('kind') != 'bodyweight' and x.get('style') != 'restorative':
                missing_weight.append(x.get('name', 'Exercise'))
            tempo = [float(v) for v in re.findall(r'\d+(?:\.\d+)?', str(x.get('tempo') or ''))]
            estimated_tempo |= not bool(tempo)
            seconds += count * reps * ((sum(tempo[:4]) if tempo else 4) + float(x.get('hold') or 0))
        else:
            seconds += count * float(x.get('seconds') or 0)
        section = x.get('section') if x.get('section') in sections else 'main'
        sections[section] += moved
    return {'weight_moved_kg': round(kg, 4), 'active_seconds': round(seconds, 2), 'time_excludes_rest': True,
            'estimated_tempo': estimated_tempo, 'missing_weights': missing_weight, 'section_weight_kg': sections,
            'basis': 'Sets × repetitions × entered external weight, counting each side when specified. Body weight and static holds are excluded from moved weight; entered machine weight is not measured tissue force.'}

def compare(sport, goals, session):
    goals = clean_goals(sport, goals)
    values = {}; unresolved = []; stats = {}
    if session.get('minutes'):
        values['minutes'] = float(session['minutes'])
    if sport == 'gym':
        stats = strength_totals(session.get('lifts'))
        values['weight_moved'] = stats['weight_moved_kg'] / (1 if goals['unit'] == 'kg' else .45359237)
        if stats['missing_weights']:
            unresolved.append('Some external weights are missing; the moved-weight total is partial.')
    elif sport == 'swim' and session.get('swim_recipe'):
        import swim_workouts
        recipe = swim_workouts.validate_recipe(session['swim_recipe'])
        values['distance'] = recipe['total_distance_m'] / (.9144 if goals['unit'] == 'yd' else 1)
        stats = {'distance_m': recipe['total_distance_m'], 'timed_sendoff_minutes': recipe['sendoff_minutes']}
    elif sport == 'run' and session.get('run_recipe'):
        import run_workouts
        recipe=run_workouts.validate(session['run_recipe']);stats=run_workouts.exposure(recipe,{})
        if recipe['distance_complete']:values['distance_km']=recipe['distance_m']/1000
        if stats['estimated_steps'] is not None:values['steps']=stats['estimated_steps']
        active=[r for r in recipe['stages'] if r['kind']=='run']
        if active and all(r['zone'] is not None for r in active) and len({r['zone'] for r in active})==1:values['zone']=active[0]['zone']
        if active and all(r['hr'] for r in active):
            values['hr_low']=min(r['hr'][0] for r in active);values['hr_high']=max(r['hr'][1] for r in active)
        unresolved.extend(stats['assumptions'])
    elif sport == 'ride':
        steps = (session.get('bike_plan') or {}).get('power_steps') or []
        if session.get('ride_blocks'):
            import workouts
            steps = workouts.flatten(session['ride_blocks'])
        chosen = [s for s in steps if goals['power_scope'] == 'session' or s.get('section') == 'main']
        if chosen and all(s.get('watts') is not None for s in chosen):
            total = sum(s['minutes'] for s in chosen)
            if total:
                values['average_watts'] = sum(s['minutes'] * s['watts'] for s in chosen) / total
        with_rpm = [s for s in chosen if s.get('rpm') is not None]       # stages without a written rpm don't count
        if with_rpm:
            total = sum(s['minutes'] for s in with_rpm)
            values['average_cadence'] = sum(s['minutes'] * s['rpm'] for s in with_rpm) / total
            if len(with_rpm) < len(chosen):
                values['cadence_basis'] = f'Averaged over the {len(with_rpm)} of {len(chosen)} stages with a written rpm.'
        if steps and all(s.get('watts') is not None for s in steps):
            stats['external_work_kj'] = round(sum(s['watts'] * s['minutes'] * 60 / 1000 for s in steps), 2)
        if 'distance_km' in goals:
            unresolved.append('Power alone does not determine distance. Route, resistance and speed data are needed to check this goal.')
        if 'energy_kcal' in goals:
            unresolved.append('Metabolic calories cannot be checked from power alone without an energy model or recorded data. External work in kJ is a different quantity.')
    checks = []
    for key in ('weight_moved', 'distance', 'minutes', 'distance_km', 'energy_kcal', 'steps', 'zone', 'hr_low', 'hr_high'):
        if key not in goals:
            continue
        got = values.get(key)
        checks.append({'metric': key, 'goal': goals[key], 'calculated': round(got, 2) if got is not None else None,
                       'difference': round(got - goals[key], 2) if got is not None else None,
                       'matches': abs(got - goals[key]) <= .05 if got is not None else None})
    if 'power_low' in goals:
        got = values.get('average_watts')
        checks.append({'metric': 'average_watts', 'scope': goals['power_scope'], 'goal_low': goals['power_low'], 'goal_high': goals['power_high'],
                       'calculated': round(got, 2) if got is not None else None,
                       'matches': goals['power_low'] <= got <= goals['power_high'] if got is not None else None})
    if 'cadence_low' in goals:
        got = values.get('average_cadence')
        check = {'metric': 'average_cadence', 'scope': goals['power_scope'], 'goal_low': goals['cadence_low'], 'goal_high': goals['cadence_high'],
                 'calculated': round(got, 1) if got is not None else None,
                 'matches': goals['cadence_low'] <= got <= goals['cadence_high'] if got is not None else None}
        if values.get('cadence_basis'):
            check['note'] = values['cadence_basis']
        if got is None:          # no rpm written in the stages: the range becomes the ride's cadence target instead
            check['note'] = 'No rpm in the written stages, so this range is saved as the ride’s cadence target.'
        checks.append(check)
    if any(c['calculated'] is None and not c.get('note') for c in checks):
        unresolved.append('Some targets cannot yet be verified from these workout details.')
    return {'goals': goals, 'checks': checks, 'totals': stats, 'unresolved': list(dict.fromkeys(unresolved)),
            'requires_review': bool(unresolved) or any(c['matches'] is False for c in checks),
            'basis': 'Checks requested work against the written prescription. This is not readiness clearance or a measure of biological response.'}

def goal_requests(d, date=None):
    return [copy.deepcopy(v) for v in d.get('workout_goal_requests', {}).values()
            if v.get('status') == 'needs_workout' and (not date or v['date'] == date)]

def save_goal(d, req):
    date = str(req.get('date') or '')
    dt.date.fromisoformat(date)
    sport = req.get('sport'); goals = clean_goals(sport, req.get('goals'))
    ident = identifier(req['id']) if req.get('id') else uuid.uuid4().hex
    requests = d.setdefault('workout_goal_requests', {})
    if req.get('id') and (ident not in requests or requests[ident]['status'] != 'needs_workout'):
        raise ValueError('Choose an unresolved workout brief to edit')
    item = {'id': ident, 'date': date, 'sport': sport, 'name': str(req.get('name') or 'Workout to design')[:80],
            'goals': goals, 'note': str(req.get('note') or '')[:600], 'status': 'needs_workout', 'updated': now(),
            'instructions': 'Design or reuse a workout within the current phase and athlete constraints. Include appropriate preparation and cool-down. Preview goal differences and whole-calendar load, then save only reviewed work. This brief has no projected or recorded activity load.'}
    requests[ident] = item
    return copy.deepcopy(item)

def attach_goals(d, date, index, req):
    session = d['plans'][date]['sessions'][index]
    goals = req.get('workout_goals')
    goal_id = req.get('goal_request_id')
    if goal_id:
        item = d.get('workout_goal_requests', {}).get(identifier(goal_id))
        if not item or item['status'] != 'needs_workout' or item['date'] != date or item['sport'] != session['sport']:
            raise ValueError('Choose an unresolved brief for this date and sport')
        goals = goals or item['goals']
    if not goals and session.get('workout_goals'):goals=session['workout_goals']
    if goals:
        comparison = compare(session['sport'], goals, session)
        if comparison['requires_review'] and req.get('goal_difference_reviewed') is not True:
            raise ValueError('Review target differences or unresolved targets before saving this workout')
        session['workout_goals'] = comparison['goals']
        session['goal_comparison'] = comparison
    if goal_id:
        d['workout_goal_requests'][goal_id].update(status='workout_created', session_index=index, resolved=now())
        session['goal_request_id'] = goal_id
    return session

def dose_signature(template):
    """Identity of what the workout prescribes. Explanatory text (how a plan was derived) is not the workout, so two
    saves of the same dose through different paths are one library entry."""
    t = copy.deepcopy(template)
    for plan in ('bike_plan', 'swim_plan'):
        if isinstance(t.get(plan), dict):
            t[plan].pop('basis', None)
    return hashlib.sha256(json.dumps(t, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def remove(d, ident, merge_into=None):
    """Take a workout out of the library. With merge_into, its dated uses and the sessions pointing at it move to the
    kept entry, so no history is lost."""
    library = d.get('workout_library', {})
    item = library.get(identifier(ident))
    if not item:
        raise ValueError('Library workout not found')
    keep_item = library.get(identifier(merge_into)) if merge_into else None
    if merge_into and not keep_item:
        raise ValueError('The workout to keep was not found')
    if keep_item:
        for use in item['uses']:
            if use not in keep_item['uses']:
                keep_item['uses'].append(use)
        keep_item['favorite'] = keep_item.get('favorite') or item.get('favorite')
        keep_item['remembered'] = keep_item.get('remembered') or item.get('remembered')
    for plan in (d.get('plans') or {}).values():
        for s in plan.get('sessions') or []:
            if s.get('library_id') == item['id']:
                if keep_item:
                    s['library_id'] = keep_item['id']
                else:
                    s.pop('library_id', None)
    for detail in (d.get('activity_workouts') or {}).values():
        if detail.get('library_id') == item['id']:
            detail['library_id'] = keep_item['id'] if keep_item else None
    del library[item['id']]
    return {'removed': item['id'], 'kept': keep_item['id'] if keep_item else None}


def routine_signature(session):
    """Gym movement identity, independent of date, weights, repetitions and effort.
    Consecutive dose rows for the same movement are one movement. Order, section,
    circuit, equipment and unilateral/bilateral structure still distinguish routines.
    """
    if session.get('sport')!='gym':return None
    import lifting
    movements=[]
    for x in session.get('lifts') or []:
        name=re.sub(r'\s+level\s+[0-3]\b','',lifting.key(x['name']))
        row=[name,x.get('section') or 'main',x.get('block') or '',
             x.get('equipment') or '',bool(x.get('per_side'))]
        if not movements or row!=movements[-1]:movements.append(row)
    return hashlib.sha256(json.dumps(movements,sort_keys=True).encode()).hexdigest() if movements else None

def _matching_item(d, template, signature, library_id=None):
    library=d.get('workout_library',{})
    family=routine_signature(template)
    if library_id:
        item=library.get(library_id)
        if not item:raise ValueError('Selected library workout not found')
        if item and family and routine_signature(item['session'])==family:return item
    exact=next((i for i in library.values() if i['signature']==signature or dose_signature(i['session'])==signature),None)
    if exact:return exact
    matches=[i for i in library.values() if family and routine_signature(i['session'])==family]
    # Ambiguous legacy duplicates need an explicit selection, never a silent merge.
    return matches[0] if len(matches)==1 else None

def keep(d, date, index, favorite=None, origin='athlete', library_id=None):
    import training_block
    sessions = training_block.sessions(d.get('plans', {}).get(date) or {})
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(sessions):
        raise ValueError('Choose an existing workout')
    session = sessions[index]
    if session['sport'] not in SPORTS or session.get('skipped_id'):
        raise ValueError('Keep an active workout rather than a rest or skipped session')
    template = {k: copy.deepcopy(session[k]) for k in TEMPLATE_KEYS if k in session}
    if template.get('bike_plan') and template.get('typed_workout'):template.pop('workout', None)
    # Machine/control identifiers and per-date source files stay out of the reusable template.
    signature = dose_signature(template)
    library = d.setdefault('workout_library', {})
    item = _matching_item(d, template, signature, library_id or session.get('library_id'))
    if item is None:
        if len(library) >= 1000:
            raise ValueError('The library has 1,000 workouts; archive unused entries before adding more')
        ident = uuid.uuid4().hex
        item = {'id': ident, 'signature': signature, 'session': template, 'favorite': False, 'created': now(), 'origin': origin, 'uses': []}
        library[ident] = item
    if favorite is not None:
        if not isinstance(favorite, bool):
            raise ValueError('Favorite must be true or false')
        item['favorite'] = favorite
    usage = {'date': date, 'index': index, 'session_name': session.get('name')}
    if usage not in item['uses']:
        item['uses'].append(usage)
    item['updated'] = now()
    if d['plans'].get(date, {}).get('sessions'):
        d['plans'][date]['sessions'][index]['library_id'] = item['id']
    return copy.deepcopy(item)

def get(d, ident):
    item = d.get('workout_library', {}).get(identifier(ident))
    if not item:
        raise ValueError('Library workout not found')
    return copy.deepcopy(item)

def responses(d, item, done=None):
    import training_block
    out = []
    for use in item.get('uses',[]):
        date, index = use['date'], use['index']
        # A replaced or edited prescription must not inherit an unrelated response by index.
        sessions = training_block.sessions(d.get('plans', {}).get(date) or {})
        if index >= len(sessions) or sessions[index].get('library_id') != item['id']:
            continue
        row = {**use, 'feedback': copy.deepcopy(d.get('training_feedback', {}).get(f'{date}:{index}'))}
        follow=copy.deepcopy(d.get('capacity_followups',{}).get(f'{date}:{index}'))
        if follow:row['delayed_capacity_followup']=follow
        if done is not None:
            import coach
            marked=coach.attach_completions(d,date,copy.deepcopy(sessions),copy.deepcopy(done.get(date,[])))
            if marked[index].get('completion'):row['completion']=marked[index]['completion']
        logs = [x for x in d.get('lifting', {}).get('logs', []) if x.get('date') == date and x.get('session') == use['session_name']]
        if logs:
            row['strength_logs'] = [{k: copy.deepcopy(x[k]) for k in ('rpe', 'wellness', 'points_total', 'regions', 'lifts') if k in x} for x in logs]
            row['delayed_lifting_followup'] = copy.deepcopy(d.get('lifting', {}).get('followups', {}).get(date))
            row['followup_scope'] = 'Lifting day; shared when multiple lifts happened on this date.'
        if row['feedback'] or logs or row.get('delayed_capacity_followup') or row.get('completion'):
            out.append(row)
    # Completed imports link by immutable source ID; measurements remain in their
    # original records, not copied into a reusable prescription.
    for ref in item.get('completed_uses',[]):
        ident=ref['activity_id']
        detail=d.get('activity_workouts',{}).get(ident,{})
        if detail.get('library_id')!=item['id']:continue
        import recorded_strength
        log=recorded_strength.source_log(d,ident)
        feedback=next((copy.deepcopy(x) for x in d.get('training_feedback',{}).values() if str(x.get('activity_id'))==ident),None)
        completion=next((copy.deepcopy(x) for x in (done or {}).get(ref['date'],[]) if str(x.get('activity_id'))==ident),None)
        existing=next((r for r in out if str((r.get('completion') or {}).get('activity_id'))==ident),None)
        row=existing if existing is not None else copy.deepcopy(ref)
        row.update(activity_id=ident,feedback=feedback or row.get('feedback'),completion=completion or row.get('completion'))
        if log:
            row.update(session_name=log['session'],external_volume_lb=log.get('dose',{}).get('external_volume_lb'),
                strength_logs=[{k:copy.deepcopy(log[k]) for k in ('rpe','wellness','points_total','regions','lifts') if k in log}],
                delayed_lifting_followup=copy.deepcopy(d.get('lifting',{}).get('followups',{}).get(ref['date'])),
                followup_scope='Lifting day; shared when multiple lifts happened on this date.')
        if existing is None:out.append(row)
    return sorted(out,key=lambda r:(r['date'],str(r.get('activity_id','')),r.get('index',-1)),reverse=True)

def completed_cardio_template(activity, detail, req):
    """Reuse recorded work without turning watch measurements into targets."""
    sport = 'ride' if activity['sport'] == 'bike' else activity['sport']
    if sport not in SPORTS:
        raise ValueError('Choose a supported recorded workout')
    name = str(req.get('name') or detail.get('name') or detail.get('workout_name') or
               'Recorded ' + {'ride': 'cycling', 'swim': 'swim', 'run': 'run', 'walk': 'walk', 'other': 'workout'}[sport]).strip()
    if not name or len(name) > 120:
        raise ValueError('Give a library name of 1–120 characters')
    template = {'sport': sport, 'name': name, 'minutes': activity['minutes'], 'note': detail.get('note', '')}
    fields = detail.get('fields') or {}
    if fields:
        template['typed_workout'] = {**{k: fields.get(k, '') for k in ('warmup', 'main', 'cooldown')}, 'repeats': 1}
        template['steps'] = [f"{LABELS[k]}: {fields[k]}" for k in ('warmup', 'main', 'cooldown') if fields.get(k)]
    if sport == 'swim' and detail.get('recipe'):
        import swim_workouts
        template['swim_recipe'] = swim_workouts.validate_recipe({**detail['recipe'], 'fields': detail['recipe'].get('fields') or fields})
        template['swim_plan'] = swim_workouts.snapshot(template['swim_recipe'])
    elif detail.get('run_recipe'):
        import run_workouts
        template['run_recipe'] = run_workouts.validate(detail['run_recipe'])
    if not template.get('steps') and not template.get('swim_recipe') and not template.get('run_recipe'):
        # A duration/distance outline is useful even without recorded interval detail.
        # Do not invent stroke, watt targets, effort, or section splits.
        distance = activity.get('km')
        template['steps'] = [f"Recorded {activity['minutes']:g} min" +
                             (f" · {distance:g} km" if distance else '')]
    return template

def save_completed(d, activity, req):
    import recorded_strength
    ident=str(activity['id']);log=recorded_strength.source_log(d,ident)
    detail=d.get('activity_workouts',{}).get(ident,{})
    if activity['sport'] != 'gym':
        return _keep_completed_template(d, activity, req, completed_cardio_template(activity, detail, req))
    if not log:raise ValueError('Add and approve the actual lifting details before saving this routine')
    lifts=copy.deepcopy((log.get('inputs',{}).get('session') or {}).get('lifts') or [])
    # The log has per-set actuals, but no planned prescription: rebuild dose rows.
    if not lifts:
        for x in log['lifts']:
            for sd in x.get('set_details') or [x]:
                if sd.get('done') is False:continue
                lifts.append({**{k:copy.deepcopy(x[k]) for k in ('name','kind','style','regions','equipment','section','block','per_side','sled','how') if k in x},
                    **{k:sd.get(k) for k in ('weight','unit','reps','seconds','tempo','hold')},'sets':1})
    template={'sport':'gym','name':str(req.get('name') or log['session']).strip(),
        'minutes':activity['minutes'],'lifts':lifts,'note':detail.get('note','')}
    if not template['name'] or len(template['name'])>120:raise ValueError('Give a library name of 1–120 characters')
    # Generate readable reusable dose text, rather than copying watch data or
    # stale athlete prose that might disagree with corrected parsed dose.
    fields={k:'\n'.join(f"{x['name']} {x.get('sets') or 1} x "+
        (f"{x['reps']}" if x.get('reps') else f"{x.get('seconds') or 0} seconds")+
        (' per side' if x.get('per_side') else '')+
        (f" @ {x['weight']} {x.get('unit') or 'lb'}" if x.get('weight') is not None else '')+
        (f" tempo {x['tempo']}" if x.get('tempo') else '')
        for x in lifts if (x.get('section') or 'main')==k) for k in ('warmup','main','cooldown')}
    template['typed_workout']={**fields,'repeats':1}
    return _keep_completed_template(d, activity, req, template)

def _keep_completed_template(d, activity, req, template):
    ident = str(activity['id'])
    detail = d.get('activity_workouts', {}).get(ident, {})
    signature=dose_signature(template)
    item=_matching_item(d,template,signature,req.get('library_id') or detail.get('library_id'))
    if item is None:
        if len(d.get('workout_library',{}))>=1000:raise ValueError('The library has 1,000 workouts')
        uid=uuid.uuid4().hex
        item={'id':uid,'signature':signature,'session':template,'favorite':False,'created':now(),'origin':'completed workout','uses':[]}
        d.setdefault('workout_library',{})[uid]=item
    # An explicit library save updates its reusable dose, while history stays
    # attached to immutable original performances. Keep a previously chosen title.
    if item.get('completed_uses') or item.get('uses'):
        template['name']=str(req.get('name') or item['session']['name'])
    item['session']=template
    item['signature']=hashlib.sha256(json.dumps(template,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    # Explicitly keeping a completed routine is the heart action.
    item['favorite']=True
    ref={'date':activity['date'],'activity_id':ident}
    if ref not in item.setdefault('completed_uses',[]):item['completed_uses'].append(ref)
    item['updated']=now()
    d.setdefault('activity_workouts',{}).setdefault(ident,{})['library_id']=item['id']
    return copy.deepcopy(item)

def reconcile_completed(d, ident):
    detail=d.get('activity_workouts',{}).get(ident,{})
    item=d.get('workout_library',{}).get(detail.get('library_id'))
    if not item:return
    import recorded_strength
    log=recorded_strength.source_log(d,ident)
    if log and routine_signature({'sport':'gym','lifts':log['lifts']})!=routine_signature(item['session']):
        item['completed_uses']=[r for r in item.get('completed_uses',[]) if r['activity_id']!=ident]
        detail.pop('library_id',None)

def remember(d, ident, remembered):
    """The brain: a remembered layer on top of the library (everything in the library is already kept)."""
    item = d.get('workout_library', {}).get(identifier(ident))
    if not item:
        raise ValueError('Library workout not found')
    if not isinstance(remembered, bool):
        raise ValueError('remembered is true or false')
    item['remembered'] = remembered
    item['updated'] = now()
    return copy.deepcopy(item)


def listing(d, sport=None, favorite_only=False, done=None, remembered_only=False):
    items = []
    for raw in d.get('workout_library', {}).values():
        if sport and raw['session']['sport'] != sport or favorite_only and not raw['favorite'] or remembered_only and not raw.get('remembered'):
            continue
        item = copy.deepcopy(raw); item['responses'] = responses(d, item, done)
        item['response_count'] = len(item['responses'])
        # Preference order, not clearance or an invented fitness-effect score.
        items.append(item)
    return sorted(items, key=lambda i: (i['favorite'], i['response_count'], i['updated']), reverse=True)

def template_from_request(d, req):
    """Validate a library draft using the same sport validators as scheduled work."""
    import coach
    import workouts
    sport = req.get('sport')
    if sport not in SPORTS:
        raise ValueError('Choose a workout sport')
    entry = {k: copy.deepcopy(req[k]) for k in TEMPLATE_KEYS if k in req}
    if sport == 'gym':
        import lifting
        entry['lifts'] = lifting.clean(copy.deepcopy(d), req.get('lifts'), draft=True)
        if not entry['lifts']:
            raise ValueError('Enter exercises before saving a strength workout; use Save brief for a goal alone')
        entry['minutes'] = float(req.get('minutes') or lifting.estimate_minutes(entry['lifts']))
    elif sport == 'swim':
        import swim_workouts
        if not req.get('swim_recipe'):
            raise ValueError('Preview a structured swim before saving it to the library')
        entry['swim_recipe'] = swim_workouts.validate_recipe(req['swim_recipe'])
        entry['swim_plan'] = swim_workouts.snapshot(entry['swim_recipe'])
        if not req.get('minutes') or float(req['minutes']) < entry['swim_recipe']['sendoff_minutes'] - .02:
            raise ValueError('Enter the full swim duration, including rest')
    elif sport == 'ride':
        if not req.get('ride_blocks'):
            raise ValueError('Preview executable power stages before saving a ride to the library')
        stages = workouts.flatten(req['ride_blocks']); duration = sum(s['minutes'] for s in stages)
        if abs(duration - float(req.get('minutes') or 0)) > .01:
            raise ValueError('Ride stage durations must match the session duration')
        entry['bike_plan'] = {'power_steps': stages, 'basis': 'Reviewed explicit watts, independent of FTP.'}
    elif sport=='run' and req.get('run_recipe'):
        import run_workouts
        entry['run_recipe']=run_workouts.validate(req['run_recipe'])
        if float(entry.get('minutes') or 0)+.01<entry['run_recipe']['minutes']:raise ValueError('Session time must include all running stages')
    elif not entry.get('steps'):
        raise ValueError('Enter a workout outline before saving it to the library')
    candidate = copy.deepcopy(d)
    coach.set_sessions(candidate, '2000-01-01', [entry], draft=True)
    normalized = candidate['plans']['2000-01-01']['sessions'][0]
    if req.get('workout_goals'):
        comparison = compare(sport, req['workout_goals'], normalized)
        if comparison['requires_review'] and req.get('goal_difference_reviewed') is not True:
            raise ValueError('Review differences or unresolved goal targets before saving')
        normalized['workout_goals'] = comparison['goals']
    return normalized

def save_template(d, req):
    entry = template_from_request(d, req)
    # Use the common signature/validation logic without touching any scheduled day.
    candidate = copy.deepcopy(d)
    candidate['plans']['2000-01-01'] = {'sessions': [entry]}
    item = keep(candidate, '2000-01-01', 0, favorite=req.get('favorite'), origin='athlete',library_id=req.get('library_id'))
    ident = item['id']
    item['session']=entry
    item['signature']=hashlib.sha256(json.dumps(entry,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    item['uses'] = copy.deepcopy(d.get('workout_library', {}).get(ident, {}).get('uses', []))
    d.setdefault('workout_library', {})[ident] = item
    return copy.deepcopy(item)

# The seven starter rides from the old block builder, now plain-English workouts in the library. Each is
# (name, purpose, [(section, kind, ...)]) in % of FTP; they're written out in watts at the athlete's FTP when added.
STARTER_RIDES = (
    ('Zone 2 · 60 min', 'Easy aerobic base.', [('warmup', 'ramp', 10, 40, 60), ('main', 'steady', 40, 62), ('cooldown', 'steady', 10, 45)]),
    ('Sweet spot 3×10', 'Sustained work just under threshold.', [('warmup', 'ramp', 10, 40, 70), ('main', 'reps', 3, 10, 90, 5, 50), ('cooldown', 'steady', 10, 45)]),
    ('Threshold 2×20', 'Long efforts at threshold.', [('warmup', 'ramp', 12, 40, 75), ('main', 'reps', 2, 20, 97, 8, 50), ('cooldown', 'steady', 10, 45)]),
    ('VO2max 5×3', 'Short hard efforts.', [('warmup', 'ramp', 12, 40, 75), ('main', 'reps', 5, 3, 112, 3, 50), ('cooldown', 'steady', 10, 45)]),
    ('Over-unders 12×(1+1)', 'Alternating just over and under threshold.', [('warmup', 'ramp', 10, 40, 75), ('main', 'reps', 12, 1, 105, 1, 90), ('cooldown', 'steady', 10, 45)]),
    ('Cadence builder', 'High-rpm spin-ups at easy watts.', [('warmup', 'steady', 10, 50), ('main', 'reps', 6, 1, 60, 2, 50, (110, 120)), ('cooldown', 'steady', 10, 50)]),
    ('Recovery spin · 30 min', 'Very easy spinning.', [('main', 'steady', 30, 45)]),
)
LABELS = {'warmup': 'Warm-up', 'main': 'Main work', 'cooldown': 'Cool-down'}


def starter_ride(name, purpose, parts, ftp):
    """One starter as the coach form would send it: typed text, parsed blocks, minutes."""
    w = lambda pct: max(20, round(pct / 100 * ftp))
    unit = lambda m: f"{m:g} minute{'s' if m != 1 else ''}"
    text, blocks = {'warmup': [], 'main': [], 'cooldown': []}, []
    for section, kind, *a in parts:
        label = LABELS[section]
        if kind == 'ramp':
            m, lo, hi = a
            text[section].append(f"{unit(m)} ramping from {w(lo)} to {w(hi)} watts")
            blocks.append({'type': 'ramp', 'minutes': m, 'from_watts': w(lo), 'to_watts': w(hi), 'label': 'Ramp', 'section': section})
        elif kind == 'steady':
            m, pct = a
            text[section].append(f"{unit(m)} at {w(pct)} watts")
            blocks.append({'type': 'steady', 'minutes': m, 'watts': w(pct), 'label': label, 'section': section})
        else:
            n, on, on_pct, off, off_pct, *rpm = a
            cad = {'rpm_low': rpm[0][0], 'rpm_high': rpm[0][1]} if rpm else {}
            words = f", {rpm[0][0]}-{rpm[0][1]} rpm" if rpm else ""
            text[section].append(f"{n} x {unit(on)} at {w(on_pct)} watts{words} with {unit(off)} at {w(off_pct)} watts between intervals")
            for i in range(n):
                blocks.append({'type': 'steady', 'minutes': on, 'watts': w(on_pct), **cad, 'label': f'Work {i + 1}', 'section': section})
                if i < n - 1:
                    blocks.append({'type': 'steady', 'minutes': off, 'watts': w(off_pct), 'label': f'Recovery {i + 1}', 'section': section})
    minutes = sum(b['minutes'] for b in blocks)
    fields = {k: '\n'.join(v) for k, v in text.items()}
    steps = [f"{s}: {t}" for s, t in fields.items() if t]
    return {'sport': 'ride', 'name': name, 'minutes': minutes, 'note': purpose + f' Written at FTP {ftp} W.',
            'typed_workout': {**fields, 'repeats': 1}, 'steps': steps, 'ride_blocks': blocks}


def add_starter_rides(d, ftp):
    """Once per athlete: the starter rides join the library (origin 'starter'). Returns how many were added."""
    if d.get('starter_rides_added'):
        return 0
    added = 0
    for name, purpose, parts in STARTER_RIDES:
        item = save_template(d, starter_ride(name, purpose, parts, ftp))
        d['workout_library'][item['id']]['origin'] = 'starter'
        added += 1
    d['starter_rides_added'] = now()
    return added
