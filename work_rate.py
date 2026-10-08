"""Read-only workload ledger. No fatigue estimate, decay, threshold or prescription.

Cardio energy is one metabolic estimate per session from the source least dependent on heart rate (energy.py:
power, then motion, then the watch). Nominal lifting external work is a distinct quantity beside it. Each report
keeps the 3-day rate and 28-day carried load frozen at the moment it was saved (snapshot()), so formula changes never
move old evidence; records saved before snapshots existed are rebuilt through a preview/apply back-fill.
"""
import datetime as dt
import math

MODEL = 'recorded-work-rate-v2-local'
SNAPSHOT = 'snapshot-v1'
J_PER_KCAL = 4184
TRAVEL_M = 0.5
KG_PER_LB = 0.45359237


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (TypeError, ValueError):
        return None


def lift_work(log):
    """Count completed dynamic loaded repetitions; never infer magnetic force."""
    volume = 0.0
    sets = []
    excluded = []
    for exercise in log.get('lifts', []):
        if not exercise.get('done', True):
            continue
        parts = exercise.get('set_details')
        if not parts:
            parts = [dict(exercise, sets=1) for _ in range(int(exercise.get('sets') or 1))]
        for index, part in enumerate(parts, 1):
            if not part.get('done', True):
                continue
            values = {**exercise, **part}
            reps, mass = number(values.get('reps')), number(values.get('weight'))
            unit = values.get('unit', 'lb')
            if not reps or not mass or unit not in ('lb', 'kg'):
                excluded.append({'exercise': exercise.get('name'), 'set': index,
                                 'reason': 'Static/unloaded work or resistance not quantified'})
                continue
            kg = mass * (KG_PER_LB if unit == 'lb' else 1)
            v = kg * reps * (2 if values.get('per_side') else 1)
            volume += v
            sets.append({'exercise': exercise.get('name'), 'set': index, 'reps': reps,
                         'weight': mass, 'unit': unit, 'volume_kg': v})
    joules = volume * 9.80665 * TRAVEL_M
    minutes = number(log.get('minutes'))
    return {'date': log['date'], 'session': log.get('session', 'Lifting'),
            'source_activity_id': log.get('source_activity_id'),
            'minutes': minutes, 'volume_kg': volume, 'volume_lb': volume / KG_PER_LB,
            'work_j': joules, 'j_per_min': joules / minutes if minutes else None,
            'sets': sets, 'excluded': excluded, 'complete': not excluded,
            'duration_basis': 'Logged session duration; includes rests',
            'travel_m_per_rep': TRAVEL_M}


def _prepare(load, logs, end):
    """The ledger's activities and lifts up to `end` (same preparation as build)."""
    activities, seen = [], set()
    for a in load.get('activities', []):
        if a.get('date', '') > end or a.get('id') in seen:
            continue
        seen.add(a.get('id'))
        seconds = number(a.get('duration_seconds'))
        minutes = seconds / 60 if seconds is not None else number(a.get('minutes'))
        calories = number(a.get('energy_kcal')) if 'energy_kcal' in a else number(a.get('calories_kcal'))
        watch = number(a.get('calories_kcal'))
        activities.append({**a, 'minutes': minutes, 'energy_j': calories * J_PER_KCAL if calories is not None else None,
                           'energy_kcal_per_min': calories / minutes if calories is not None and minutes and minutes > 0 else None,
                           'energy_power_w': calories * J_PER_KCAL / (minutes * 60) if calories is not None and minutes and minutes > 0 else None,
                           'energy_source': a.get('energy_source') or ('watch' if watch is not None else None),
                           'watch_energy_j': watch * J_PER_KCAL if watch is not None else None,
                           'duration_basis': 'Recorded timer' if seconds is not None else 'Hub recorded duration (rounded)'})
    lifts = [lift_work(l) for l in logs if l.get('date', '') <= end]
    by_id = {a.get('id'): a for a in activities}
    for l in lifts:
        match = by_id.get(l['source_activity_id'])
        if match and match.get('minutes'):
            l['minutes'] = match['minutes']
            l['j_per_min'] = l['work_j'] / l['minutes']
            l['duration_basis'] = match['duration_basis']
    return activities, lifts


def _window(activities, lifts, feedback, date, n, cutoff=None):
    """Work over the n calendar days ending `date`. `cutoff` (HH:MM) drops that day's sessions that started later,
    so a morning check-in isn't credited with the afternoon's ride."""
    start = (dt.date.fromisoformat(date) - dt.timedelta(days=n - 1)).isoformat()
    later = lambda a: cutoff is not None and a['date'] == date and (a.get('start') or '00:00') > cutoff
    aa = [a for a in activities if start <= a['date'] <= date and a.get('source') != 'lifts' and not later(a)]
    ll = [l for l in lifts if start <= l['date'] <= date and not (cutoff is not None and l['date'] == date)]
    known = [a for a in aa if a['energy_j'] is not None]
    joules = sum(a['energy_j'] for a in known)
    minutes = sum(a['minutes'] or 0 for a in known)
    mix, sources = {}, {}
    for a in known:
        mix[a['sport']] = mix.get(a['sport'], 0) + a['energy_j']
        sources[a.get('energy_source') or 'watch'] = sources.get(a.get('energy_source') or 'watch', 0) + 1
    lift_j = sum(l['work_j'] for l in ll)
    lift_min = sum(l['minutes'] or 0 for l in ll)
    # How the work is spread: the biggest single day, and the typical training day (median of days with work).
    # The same average can be one big day or several moderate ones (Foster 1998, training monotony).
    per_day = {}
    for a in known:
        day = per_day.setdefault(a['date'], {'j': 0.0, 'sports': []})
        day['j'] += a['energy_j']
        if a['sport'] not in day['sports']:
            day['sports'].append(a['sport'])
    peak = max(per_day.items(), key=lambda kv: kv[1]['j'], default=None)
    training_days = sorted(v['j'] for v in per_day.values() if v['j'] > 0)
    median_day = None
    if training_days:
        m = len(training_days) // 2
        median_day = training_days[m] if len(training_days) % 2 else (training_days[m - 1] + training_days[m]) / 2
    # Session effort x minutes (Foster et al. 2001): a validated common load unit, beside the joules.
    srpe = [(v.get('rpe'), number(v.get('actual_minutes')) or number(v.get('planned_minutes')))
            for k, v in (feedback or {}).items() if start <= (v.get('date') or k[:10]) <= date and not
            (cutoff is not None and (v.get('date') or k[:10]) == date)]
    srpe = [(r, m) for r, m in srpe if number(r) is not None and m]
    return {'start': start, 'end': date, 'days': n, **({'cutoff': cutoff} if cutoff else {}),
            'cardio': {'known_j': joules, 'j_per_day': joules / n,
                       'j_per_min': joules / minutes if minutes else None, 'known_minutes': minutes,
                       'known_sessions': len(known), 'recorded_sessions': len(aa),
                       'missing_ids': [a['id'] for a in aa if a['energy_j'] is None],
                       'complete': len(known) == len(aa), 'sport_j': mix, 'sources': sources,
                       'gaps': [{'id': a['id'], 'sport': a['sport'], 'watch_vs_primary': a.get('energy_gap_ratio')}
                                for a in known if a.get('energy_gap_ratio')],
                       'share_percent': {s: v / joules * 100 for s, v in mix.items()} if joules else {},
                       'peak_day': {'date': peak[0], 'j': peak[1]['j'], 'sports': peak[1]['sports']} if peak else None,
                       'training_days': len(training_days), 'median_training_day_j': median_day},
            'lifting': {'known_j': lift_j, 'j_per_day': lift_j / n,
                        'j_per_min': lift_j / lift_min if lift_min else None,
                        'known_minutes': lift_min, 'volume_kg': sum(l['volume_kg'] for l in ll),
                        'volume_lb': sum(l['volume_lb'] for l in ll), 'sessions': len(ll),
                        'excluded_sets': sum(len(l['excluded']) for l in ll),
                        'complete': all(l['complete'] for l in ll)},
            'session_load': {'srpe_au': sum(number(r) * m for r, m in srpe), 'reports': len(srpe),
                             'basis': 'Reported session effort x minutes (Foster et al. 2001); only sessions with an effort report'}}


def snapshot(load, logs, feedback, date, cutoff=None, recorded='at_report', session=None, saved_at=None):
    """The context frozen with a report: exactly the dashboard's 3-day and 28-day windows at that moment."""
    activities, lifts = _prepare(load, logs, date)
    s = {'version': SNAPSHOT, 'recorded': recorded, 'model': MODEL, 'date': date,
         'saved_at': saved_at or dt.datetime.now().isoformat(timespec='seconds'),
         'context_3_days': _window(activities, lifts, feedback, date, 3, cutoff),
         'context_28_days': _window(activities, lifts, feedback, date, 28, cutoff)}
    if cutoff:
        s['cutoff'] = cutoff
    if session:
        a = next((x for x in activities if x.get('id') == session), None)
        if a:
            s['session'] = {k: a.get(k) for k in ('id', 'sport', 'minutes', 'energy_j', 'energy_source', 'watch_energy_j',
                                                  'avg_hr', 'energy_estimates', 'energy_gap_ratio', 'km', 'descent_m')}
    return s


def build(load, logs=(), checkins=None, weekly=None, feedback=None, followups=None, today=None):
    today = dt.date.fromisoformat(today) if isinstance(today, str) else today or dt.date.today()
    end = today.isoformat()
    activities, lifts = _prepare(load, logs, end)

    window = lambda date, n, cutoff=None: _window(activities, lifts, feedback, date, n, cutoff)

    earliest = min([a['date'] for a in activities] + [l['date'] for l in lifts], default=end)
    daily = []
    date = dt.date.fromisoformat(earliest)
    import bodymap
    while date <= today:
        day = date.isoformat()
        aa = [a for a in activities if a['date'] == day]
        sports = {}
        for a in aa:
            sp = sports.setdefault(a['sport'], {'engine': 0.0, 'impact': 0.0, 'muscle': 0.0})
            for domain in sp:
                sp[domain] += number(a.get(domain)) or 0
        regions = {}
        for key, (name, weights) in bodymap.REGIONS.items():
            parts = {}
            for sport, weight in weights.items():
                value = (sum(v['impact'] for v in sports.values()) if sport == 'impact'
                         else sports.get(sport, {}).get('muscle', 0)) * weight
                if value:
                    parts[sport] = value
            lift_points = sum(number(l.get('regions', {}).get(key)) or 0 for l in logs if l.get('date') == day)
            if lift_points:
                parts['lift'] = lift_points
            regions[key] = {'name': name, 'sources': parts}
        daily.append({'date': day, **window(day, 1), 'sports': sports, 'regions': regions,
                      'exposure': {k: sum(v[k] for v in sports.values()) for k in ('engine', 'impact', 'muscle')}})
        date += dt.timedelta(days=1)

    reports = []
    start90 = (today - dt.timedelta(days=89)).isoformat()
    for kind, collection in [('Daily check-in', checkins or {}), ('Weekly check-in', weekly or {}),
                             ('Workout report', feedback or {}), ('Lifting follow-up', followups or {})]:
        for key, value in collection.items():
            date = value.get('date') or key[:10]
            if not start90 <= date <= end:
                continue
            # No conversion of comfort, soreness or wellness into modeled fatigue.
            readings = {k: value[k] for k in ('legs', 'feet', 'shoulders', 'gut', 'week', 'rpe', 'wellness', 'regions', 'pain', 'hooper_index', 'ostrc', 'note', 'journal', 'run_response') if value.get(k) is not None}
            if readings:
                snap = value.get('snapshot')
                frozen = isinstance(snap, dict) and snap.get('version') == SNAPSHOT
                reports.append({'date': date, 'kind': kind, 'source_key': key,
                                'activity_id': value.get('activity_id'), 'readings': readings,
                                'context_basis': snap.get('recorded') if frozen else 'reconstructed',
                                'context_3_days': snap['context_3_days'] if frozen else window(date, 3),
                                'context_28_days': snap['context_28_days'] if frozen else window(date, 28)})
    recent = sorted([l for l in lifts if (today - dt.timedelta(days=9)).isoformat() <= l['date'] <= end], key=lambda l:l['date'])[-3:]
    recent_minutes = sum(l['minutes'] or 0 for l in recent)
    return {'model': MODEL, 'local_experiment': True, 'as_of': end, 'current_day_in_progress': True,
            'windows': {'3': window(end, 3), '28': window(end, 28)},
            'history_start': earliest, 'daily': daily, 'activities': activities, 'lifts': lifts,
            'recent_lifts': {'sessions': recent, 'j_per_min': sum(l['work_j'] for l in recent) / recent_minutes if recent_minutes else None},
            'reports': sorted(reports, key=lambda r: (r['date'], r['kind']), reverse=True),
            'response_band': None,
            'basis': {'cardio': 'One metabolic energy estimate per session × 4,184 J/kcal: cycling power (mechanical kJ ≈ metabolic kcal at ~20–25% gross efficiency), running and walking from mass × distance × gradient cost (Minetti et al. 2002) plus resting metabolism, otherwise the watch calories (heart-rate based). Watch calories are kept beside every primary estimate; gaps beyond 30% are flagged.',
                      'lifting': 'Completed load × repetitions × 9.80665 × assumed 0.5 m travel per repetition. Nominal external work, not metabolic energy. Holds and tempo excluded.',
                      'exposure': 'Existing modeled exposure indices per calendar day. Region coefficients overlap; source units are not measured tissue force.',
                      'windows': 'Inclusive calendar dates ending today. Today is in progress. Missing sessions/imports cannot be detected; no recorded activity does not prove rest.',
                      'reports': 'Report contexts are frozen when the report is saved (at_report), rebuilt by the back-fill (rebuilt), or reconstructed now for records not yet back-filled. They describe recorded work, not causal attribution. Daily and weekly reports can overlap; they are not independent recovery trials.',
                      'session_load': 'Session effort × minutes (Foster et al. 2001) where an effort report exists, beside the joules.',
                      'peak_day': 'Biggest single calendar day of cardio energy in the window, compared with the median training day (days with recorded work) over 28 days. Spread matters as well as the average (Foster 1998).'}}
