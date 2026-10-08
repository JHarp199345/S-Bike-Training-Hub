"""Conservative, auditable progression and forecast records; not injury clearance."""
import copy
import datetime as dt
import hashlib
import json

PROTECTED_FRACTION = .60
MIN_RUN_DAYS = None            # no fixed wait: the accumulated blocks set when running clears (an athlete may set their own)
CHECK_KINDS = ('strength', 'balance', 'loading')


def _date(value):
    return dt.date.fromisoformat(value) if isinstance(value, str) else value


def record_check(d, fields, today=None):
    today = _date(today or dt.date.today())
    date = _date(fields.get('test_date') or today.isoformat())
    if date > today: raise ValueError('A check cannot be recorded in the future')
    kind = fields.get('kind')
    if kind not in CHECK_KINDS: raise ValueError('Check kind is strength, balance or loading')
    for key in ('controlled', 'gritted', 'after_ok'):
        if not isinstance(fields.get(key), bool): raise ValueError(key+' must be explicitly true or false')
    symptoms = float(fields.get('symptoms', 10))
    if not 0 <= symptoms <= 10: raise ValueError('Symptoms must be between 0 and 10')
    follow = fields.get('followup_date')
    next_ok = fields.get('next_day_ok')
    if follow:
        follow = _date(follow)
        if not date < follow <= today: raise ValueError('Follow-up must be after the check and no later than today')
        if not isinstance(next_ok, bool): raise ValueError('Next-day response must be explicitly true or false')
    elif next_ok is not None: raise ValueError('Next-day response needs a dated follow-up')
    name = str(fields.get('name') or kind).strip()[:160]
    key = hashlib.sha256((date.isoformat()+kind+name).encode()).hexdigest()[:16]
    entry = {'id':key, 'date':date.isoformat(), 'kind':kind, 'name':name,
             'controlled':fields['controlled'], 'gritted':fields['gritted'], 'symptoms':symptoms,
             'after_ok':fields['after_ok'], 'followup_date':follow.isoformat() if follow else None,
             'next_day_ok':next_ok if follow else None, 'note':str(fields.get('note') or '')[:1000],
             'recorded_at':today.isoformat()}
    state = d.setdefault('run_progression', {})
    checks = state.setdefault('checks', [])
    old = next((x for x in checks if x['id']==key), None)
    if old:
        state.setdefault('check_edits', []).append(copy.deepcopy(old))
        checks[checks.index(old)] = entry
    else: checks.append(entry)
    bad=(entry['gritted'] or not entry['controlled'] or entry['symptoms']>0
         or not entry['after_ok'] or entry['next_day_ok'] is False)
    reviews=state.get('reviews',[])
    if bad and reviews and reviews[-1]['action']=='begin_decline':
        reviews.append({'date':today.isoformat(),'action':'restore_plateau','check_id':key,
                        'note':'Setback reverses the tentative early-decline calibration; not extra workout force'})
    return entry


def successful(c, today):
    return (c.get('controlled') is True and c.get('gritted') is False and c.get('symptoms') == 0
            and c.get('after_ok') is True and c.get('next_day_ok') is True
            and c.get('followup_date') and c['date'] < c['followup_date'] <= today)


def status(d, remodel=None, today=None):
    today = _date(today or dt.date.today()); key=today.isoformat(); remodel=remodel or {}
    state=d.get('run_progression') or {}
    response_model=bool(remodel.get('response_model'))
    days=remodel.get('plateau_days'); left=remodel.get('plateau_remaining_days')
    progress=max(0,min(1,1-left/days)) if days and left is not None else None
    checks=sorted([c for c in state.get('checks',[]) if c['date']<=key],key=lambda c:c['date'])
    setbacks=[c for c in checks if c.get('gritted') or not c.get('controlled') or c.get('symptoms',10)>0
              or c.get('after_ok') is False or c.get('next_day_ok') is False]
    bad=max((c.get('followup_date') if c.get('next_day_ok') is False else c['date'] for c in setbacks),default='')
    good=[c for c in checks if c['date']>bad and successful(c,key)
          and (today-_date(c['date'])).days<=7]
    repeated=len({c['date'] for c in good})>=2
    kinds={c['kind'] for c in good}
    last_run=remodel.get('last_run_date') if response_model else max((e['date'] for e in remodel.get('components',[]) if e.get('raw_blocks',0)>0),default=None)
    if last_run: good=[c for c in good if c['date']>last_run]; kinds={c['kind'] for c in good}; repeated=len({c['date'] for c in good})>=2
    min_days=state.get('minimum_run_days',MIN_RUN_DAYS)
    elapsed=(today-_date(last_run)).days if last_run else None
    import journal
    current=journal.effective((d.get('checkins') or {}).get(key) or {})
    poor_today=(any(current.get(k) is not None and current[k]>=6 for k in ('feet','legs'))
                or current.get('hops') is not None and current['hops']<=3 or current.get('gut')=='no')
    reasons=[]
    if poor_today:reasons.append("Today's check-in does not support progression")
    if not response_model:
        if remodel.get('score') is None: reasons.append('Mechanical running load is unavailable')
        elif remodel['score']>=remodel.get('threshold_blocks',1.5): reasons.append('Mechanical running load is still at or above its planning limit')
    if min_days and (elapsed is None or elapsed<min_days): reasons.append(f'Personal minimum wait: {min_days} days since the latest run')
    if not repeated or not set(CHECK_KINDS)<=kinds: reasons.append('Repeated comfortable strength, balance and loading checks with dated next-day responses are still needed')
    rt=run_test_status(d,remodel,today)
    test_ok=bool(rt.get('last') and rt['last']['verdict']=='good' and (today-_date(rt['last']['finished'])).days<=7)
    review_ok=(remodel.get('phase')=='plateau' and progress is not None and progress>=PROTECTED_FRACTION
               and ((repeated and {'strength','balance'}<=kinds) or test_ok) and not poor_today)
    return {'protected_fraction':PROTECTED_FRACTION,'plateau_progress':progress,'run_test':rt,
            'review_eligible':review_ok,'run_eligible':not reasons,'run_reasons':reasons,
            'minimum_run_days':min_days,'days_since_run':elapsed,'successful_checks':len(good),
            'latest_setback':bad or None,'checks':checks[-12:], 'reviews':state.get('reviews',[])[-6:],
            'stage':'running review' if not reasons else 'functional response checks' if response_model else 'awaiting metrics' if remodel.get('score') is None else 'preparatory checks' if remodel.get('phase')!='plateau' or progress is not None and progress>=PROTECTED_FRACTION else 'protected recovery',
            'model': 'reported response' if response_model else 'legacy blocks',
            'note':'Functional response checks remain separate from the advisory running estimate.' if response_model else 'Passing a check never automatically ends the plateau, erases blocks, or clears running.'}


# ── the run-walk test at the 60% checkpoint (the athlete's protocol, 2026-10-05) ──────────────────────────────
# Day 1 a short run-walk; day 2 (24 h) how walking feels; day 3 (48 h) how stairs feel (or walking, without stairs).
# Built to common return-to-running guidance: before the first run, a brisk 30-min walk and 10 single-leg hops without
# rising discomfort; a first session of ~5 min of running broken up with walking; morning or night pain, or pain past
# 48 h, means step back, while slight discomfort gone within 24 h is acceptable; pain during the run stays below 5/10
# (Silbernagel et al. 2007 pain-monitoring model). A good test OFFERS the reviewed early decline - never automatic.
RUN_TEST_STEPS = ('run_walk', 'walk', 'stairs')
RUN_TEST_RETRY_DAYS = 7
RUN_TEST_SESSION = {'minutes': 15, 'pattern': '1 min easy running, then 1-2 min walking, on the flat',
                    'running_minutes': 5, 'stop_if_pain': 5}


def _checkpoint(remodel, today):
    days, left = remodel.get('plateau_days'), remodel.get('plateau_remaining_days')
    if not days or left is None or remodel.get('phase') != 'plateau':
        return None, None
    served = days - left
    return round(max(0, min(1, served / days)), 2), (today + dt.timedelta(days=max(0, round(PROTECTED_FRACTION * days - served)))).isoformat()


def _entry_ok(checkin, fields):
    hl, hr = checkin.get('hops_left'), checkin.get('hops_right')
    hops = min(hl, hr) if hl is not None and hr is not None else checkin.get('hops')
    why = []
    if hops is None or hops < 10:
        why.append('10 pain-free single-leg hops on each leg (today\'s check-in)')
    for k in ('feet', 'legs'):
        if checkin.get(k) is None or checkin[k] > 3:
            why.append(f'{k} at 3/10 or lower today')
    if fields.get('brisk_walk_ok') is not True:
        why.append('a brisk 30-minute walk without discomfort rising, during or after')
    return why


def run_test_status(d, remodel=None, today=None):
    """Where the run-walk test stands: not due yet, ready to start (or what's missing), in progress, or done."""
    today = _date(today or dt.date.today()); key = today.isoformat(); remodel = remodel or {}
    state = (d.get('run_progression') or {})
    tests = state.get('run_tests') or []
    cur = next((t for t in reversed(tests) if not t.get('verdict')), None)
    last = next((t for t in reversed(tests) if t.get('verdict')), None)
    progress, due = _checkpoint(remodel, today)
    if remodel.get('response_model'):progress,due=PROTECTED_FRACTION,key
    out = {'session': RUN_TEST_SESSION, 'progress': progress, 'checkpoint_date': due, 'last': last}
    if cur:
        nxt = next(s for s in RUN_TEST_STEPS if s not in cur['steps'])
        prev = max(cur['steps'].values(), key=lambda x: x['date'])['date']
        out.update(stage='in_progress', test=cur, next_step=nxt,
                   next_date=(_date(prev) + dt.timedelta(days=1)).isoformat())
        return out
    if last and last['verdict'] != 'good' and key < last['retry_from']:
        out.update(stage='retry_wait', retry_from=last['retry_from'])
        return out
    if progress is None:
        out.update(stage='not_applicable')
    elif progress < PROTECTED_FRACTION:
        out.update(stage='not_due')
    else:
        import journal
        checkin = journal.effective((d.get('checkins') or {}).get(key) or {})
        out.update(stage='ready', missing=_entry_ok(checkin, {'brisk_walk_ok': True}))
    return out


def record_run_test(d, step, fields, remodel=None, today=None):
    """One step of the test. run_walk: {brisk_walk_ok, completed, pain_max (0-10)}; walk: {walk_feel (0-10),
    morning_pain, night_pain}; stairs: {used_stairs, stairs_feel (0-10), pain_lasting}. Returns the test."""
    import journal
    today = _date(today or dt.date.today()); key = today.isoformat()
    state = d.setdefault('run_progression', {}); tests = state.setdefault('run_tests', [])
    st = run_test_status(d, remodel, today)
    num = lambda k, lo=0, hi=10: max(lo, min(hi, float(fields[k]))) if fields.get(k) is not None else None
    if step == 'run_walk':
        if st['stage'] != 'ready':
            raise ValueError({'not_due': f"the run-walk test opens at 60% of the plateau ({st.get('checkpoint_date')})",
                              'retry_wait': f"the next try is from {st.get('retry_from')}", 'in_progress': 'a test is already under way',
                              'not_applicable': 'no running plateau to test'}.get(st['stage'], 'not available'))
        checkin = journal.effective((d.get('checkins') or {}).get(key) or {})
        missing = _entry_ok(checkin, fields)
        if missing:
            raise ValueError('Before the run-walk: ' + '; '.join(missing))
        for k in ('completed',):
            if not isinstance(fields.get(k), bool): raise ValueError(k + ' must be true or false')
        test = {'id': key, 'started': key, 'steps': {'run_walk': {'date': key, 'completed': fields['completed'],
                'pain_max': num('pain_max'), 'note': str(fields.get('note') or '')[:500]}}}
        tests.append(test)
        if not fields['completed'] or (num('pain_max') or 0) >= RUN_TEST_SESSION['stop_if_pain']:
            _verdict(test, key)
        return test
    if st['stage'] != 'in_progress' or st['next_step'] != step:
        raise ValueError(f"the next step is {st.get('next_step') or 'the run-walk'}")
    test = st['test']
    prev = max(test['steps'].values(), key=lambda x: x['date'])['date']
    if key <= prev:
        raise ValueError(f'{step} is checked the day after the previous step ({st["next_date"]})')
    if step == 'walk':
        for k in ('morning_pain', 'night_pain'):
            if not isinstance(fields.get(k), bool): raise ValueError(k + ' must be true or false')
        test['steps']['walk'] = {'date': key, 'walk_feel': num('walk_feel'), 'morning_pain': fields['morning_pain'],
                                 'night_pain': fields['night_pain'], 'note': str(fields.get('note') or '')[:500]}
        if fields['morning_pain'] or fields['night_pain']:
            _verdict(test, key)
    else:
        if not isinstance(fields.get('pain_lasting'), bool): raise ValueError('pain_lasting must be true or false')
        test['steps']['stairs'] = {'date': key, 'used_stairs': bool(fields.get('used_stairs', True)), 'stairs_feel': num('stairs_feel'),
                                   'pain_lasting': fields['pain_lasting'], 'note': str(fields.get('note') or '')[:500]}
        _verdict(test, key)
    return test


def _verdict(test, key):
    r, w, s = (test['steps'].get(x) or {} for x in RUN_TEST_STEPS)
    why = []
    if not r.get('completed'): why.append('the run-walk was not completed')
    if (r.get('pain_max') or 0) >= RUN_TEST_SESSION['stop_if_pain']: why.append(f"pain reached {r.get('pain_max'):g}/10 during the run-walk")
    if w.get('morning_pain'): why.append('morning pain the next day')
    if w.get('night_pain'): why.append('pain at night')
    if w and (w.get('walk_feel') or 0) > 2: why.append(f"walking felt {w['walk_feel']:g}/10 the next day")
    if s and (s.get('stairs_feel') or 0) > 2: why.append(f"{'stairs' if s.get('used_stairs') else 'walking'} felt {s['stairs_feel']:g}/10 two days on")
    if s.get('pain_lasting'): why.append('pain lasting past 48 hours')
    good = not why and bool(s)
    test.update(verdict='good' if good else 'retry', finished=key, why=why or ['no morning pain, and walking and stairs comfortable'],
                retry_from=(_date(key) + dt.timedelta(days=RUN_TEST_RETRY_DAYS)).isoformat())


def approve_decline(d, remodel, today=None, note=''):
    today=_date(today or dt.date.today()); s=status(d,remodel,today)
    if not s['review_eligible']: raise ValueError('Review requires at least 60% of the plateau and a good run-walk test, or repeated comfortable strength/balance checks with next-day responses')
    if any(r['date']==today.isoformat() for r in (d.get('run_progression') or {}).get('reviews',[])):
        raise ValueError('A review is already recorded today')
    r={'date':today.isoformat(),'action':'begin_decline','score':remodel['score'],
       'plateau_progress':s['plateau_progress'],'note':str(note)[:1000],
       'evidence_ids':[c['id'] for c in s['checks'] if successful(c,today.isoformat())],
       'policy':'60% protected plateau; explicit review; load preserved; running stays separately gated'}
    d.setdefault('run_progression',{}).setdefault('reviews',[]).append(r)
    return r


def save_forecasts(d, forecast, done=None, now=None):
    """First pre-work baseline is immutable; save plan revisions until work begins."""
    now=now or dt.datetime.now().isoformat(timespec='seconds'); day=now[:10]; done=done or {}
    snapshots=d.setdefault('load_forecasts',{})
    saved=[]
    for f in forecast.get('load_outlooks',[]):
        date=f['date']
        if date<day or done.get(date) or any(s.get('completed') for s in f['sessions']): continue
        fingerprint=hashlib.sha256(json.dumps({'metrics':f['metrics'],'sessions':f['sessions']},sort_keys=True).encode()).hexdigest()
        records=snapshots.setdefault(date,[])
        if any(r['fingerprint']==fingerprint for r in records): continue
        record={'saved_at':now,'fingerprint':fingerprint,'forecast':copy.deepcopy({k:v for k,v in f.items() if k not in ('regional_overlap','metrics_by_key')})}
        if len(records)>=12: records.pop(1)  # retain the first baseline and recent revisions
        records.append(record);saved.append(date)
    return saved


def comparisons(d, load, today=None):
    """Compare saved pre-work predictions with the recorded model, using like units."""
    today=_date(today or dt.date.today()).isoformat()
    out=[]
    import training_block
    history=training_block.recorded_load_history(load,_date(today)+dt.timedelta(days=1))
    actual={r['date']:{m['key']:m['after'] for m in r['metrics']} for r in history}
    systems=load.get('systems') or {}
    tissue=(systems.get('impact') or {}).get('tissue') or {}
    current={k:(systems.get(system) or {}).get(field) for k,system,field in (
        ('cardio_fatigue','engine','fatigue'),('cardio_conditioning','engine','fitness'),
        ('impact_fatigue','impact','fatigue'),('muscle_fatigue','muscle','fatigue'))}
    response=load.get('running_response') or {}
    if response.get('active'):
        estimate=response['estimate'];current['run_response']=(estimate['low']+estimate['high'])/2
    current.update(run_mechanical=None if response.get('active') else (tissue.get('remodeling') or {}).get('score'),
                   run_recent=None if response.get('active') else (tissue.get('event') or {}).get('score'),
                   swim_recovery=(load.get('swim_recovery') or {}).get('score'),
                   mechanical=((load.get('headline') or {}).get('mechanical') or {}).get('ratio'))
    regions=(load.get('lifting') or {}).get('regions') or {}
    current.update({'lift_'+r:v.get('blocks') for r,v in regions.items()})
    current['strength']=max((v['blocks'] for v in regions.values()),default=0)
    actual[today]=current
    for date,records in sorted((d.get('load_forecasts') or {}).items()):
        if date>today or date not in actual or not records: continue
        r=records[-1]; metrics=[]
        for m in r['forecast']['metrics']:
            a=actual[date].get(m['key']); expected=m.get('after')
            metrics.append({'key':m['key'],'name':m['name'],'unit':m['unit'],'actual':a,'expected':expected,
                            'difference':round(a-expected,2) if a is not None and expected is not None else None})
        out.append({'date':date,'saved_at':r['saved_at'],'metrics':metrics,
                    'status':'day in progress' if date==today else 'recorded model vs saved plan'})
    return out


def observe_checkin(d, date, checkin):
    """A poor mechanical report reverses an existing tentative review, never ordinary plateaus."""
    import journal
    c=journal.effective(checkin)
    poor=any(c.get(k) is not None and c[k]>=6 for k in ('feet','legs')) or c.get('hops') is not None and c['hops']<=3
    reviews=(d.get('run_progression') or {}).get('reviews',[])
    if poor and reviews and reviews[-1]['action']=='begin_decline' and date>=reviews[-1]['date']:
        reviews.append({'date':date,'action':'restore_plateau','note':'Poor mechanical check-in reverses tentative early decline; no extra workout dose'})
