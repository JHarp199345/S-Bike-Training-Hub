"""Read-only completed-activity metrics. Observations stay separate from load estimates."""
import datetime as dt
import math
import statistics


def number(value, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value if value > 0 or (not positive and value >= 0) else None


def mean(values):
    values = [v for v in values if v is not None]
    return round(statistics.fmean(values), 2) if values else None


def swim_metrics(a):
    pool = number(a.get('pool_length_m'), True)
    active = [x for x in a.get('swim_lengths', []) if x.get('length_type') == 1]
    by_stroke = {}
    import swimload
    for x in active:
        # Drill/kick and unclassified lengths do not measure normal stroke efficiency.
        style = x.get('swim_stroke')
        if style not in (0, 1, 2, 3): continue
        strokes = number(x.get('total_strokes'), True)
        seconds = number(x.get('total_timer_time'), True)
        if not pool or not strokes or not seconds: continue
        row = by_stroke.setdefault(swimload.STROKES[style], [])
        row.append({'swolf': seconds + strokes, 'strokes': strokes, 'seconds': seconds,
                    'distance_per_stroke_m': pool / strokes})
    def aggregate(rows):
        return {'lengths': len(rows), 'swolf_avg': mean([r['swolf'] for r in rows]),
                'swolf_best': round(min(r['swolf'] for r in rows), 2) if rows else None,
                'strokes_per_length_avg': mean([r['strokes'] for r in rows]),
                'distance_per_stroke_avg_m': round(pool * len(rows) / sum(r['strokes'] for r in rows), 2) if rows else None,
                'distance_per_stroke_best_m': round(max(r['distance_per_stroke_m'] for r in rows), 2) if rows else None,
                'pace_per_100m_seconds': round(sum(r['seconds'] for r in rows) / (pool * len(rows)) * 100, 1) if rows else None}
    rows = [r for group in by_stroke.values() for r in group]
    return {**aggregate(rows), 'pool_length_m': pool, 'active_lengths': len(active),
            'excluded_lengths': len(active) - len(rows),
            'by_stroke': {name: aggregate(group) for name, group in by_stroke.items()},
            'basis': 'Calculated from watch active pool lengths with watch-classified stroke, positive stroke count and duration. SWOLF = seconds + counted strokes per length. Average distance per stroke = measured length distance / total counted strokes; best is the longest distance per stroke for one measured length. Push-offs affect it. Drill, kick and unknown lengths excluded. Compare SWOLF at the same pool length, stroke and similar pace; lower alone does not prove improvement.'}


def build(a, scored=None, d=None, actual=None):
    s = a.get('session') or {}; scored = scored or {}; d = d or {}
    hrs = [number(r.get('hr'), True) for r in a.get('records', [])]
    hrs = [h for h in hrs if h is not None]
    timer = number(s.get('total_timer_time'), True)
    seconds = timer or (number(a.get('minutes'), True) or 0) * 60
    distance = number(a.get('distance_m'))
    date = scored.get('date') or dt.date.fromtimestamp(a['start']).isoformat()
    feedback = next((v for v in d.get('training_feedback', {}).values() if v.get('activity_id') == a['id']), None)
    if feedback is None:
        import coach, copy, training_block
        sessions = training_block.sessions(d.get('plans', {}).get(date) or {})
        done = (actual or {}).get(date) or [{**scored, 'sport': a['sport'], 'minutes': a.get('minutes', 0), 'activity_id': a['id']}]
        marked = coach.attach_completions(d, date, copy.deepcopy(sessions), done)
        index = next((i for i, x in enumerate(marked) if x.get('completion', {}).get('activity_id') == a['id']), None)
        if index is not None: feedback = d.get('training_feedback', {}).get(date + ':' + str(index))
    out = {'feedback_supported': True, 'activity_id': a['id'], 'date': date, 'sport': a['sport'], 'source': a.get('source'),
           'duration_seconds': round(seconds, 1), 'distance_m': distance,
           'calories_kcal': number(s.get('total_calories')),
           'calories_basis': 'Watch-reported total; active/resting split unknown' if number(s.get('total_calories')) is not None else None,
           'avg_hr': number(s.get('avg_heart_rate'), True) or mean(hrs),
           'max_hr': number(s.get('max_heart_rate'), True) or (max(hrs) if hrs else None),
           'load': {k: scored.get(k) for k in ('engine', 'impact', 'muscle')},
           'load_basis': 'Existing Hub model estimates, not measured tissue damage',
           'feedback': feedback, 'workout_details': d.get('activity_workouts', {}).get(a['id'])}
    # Use the ledger's existing metabolic estimate, never add mechanical lifting work to it.
    energy = number(scored.get('energy_kcal')) if 'energy_kcal' in scored else number(s.get('total_calories'))
    source = scored.get('energy_source') if 'energy_kcal' in scored else 'watch'
    out['energy_rate'] = {'kcal_per_min': round(energy * 60 / seconds, 2),
                          'metabolic_power_w': round(energy * 4184 / seconds, 2),
                          'energy_kcal': energy, 'source': source,
                          'duration_basis': 'Recorded timer' if timer else 'Hub recorded duration (rounded)'} if energy is not None and seconds > 0 else None
    if a['sport'] == 'swim': out['swim'] = swim_metrics(a)
    if a['sport'] == 'run':
        cadence = number(s.get('avg_cadence'), True)
        out['run'] = {'pace_per_km_seconds': round(seconds / distance * 1000, 1) if distance and seconds else None,
                      'cadence_steps_min': cadence * 2 if cadence else None,
                      'steps': s['total_cycles'] * 2 if number(s.get('total_cycles'), True) else None,
                      'estimated_steps': scored.get('steps'), 'drift_pct': scored.get('drift_pct'),
                      'step_length_m': s['avg_step_length'] / 1000 if number(s.get('avg_step_length'), True) else None,
                      'ground_contact_ms': number(s.get('avg_stance_time'), True),
                      'vertical_oscillation_mm': number(s.get('avg_vertical_oscillation'), True),
                      'vertical_ratio_pct': number(s.get('avg_vertical_ratio'), True),
                      'cadence_basis': 'FIT running cycles per minute × 2 steps',
                      'laps': [{'lap': i + 1, 'seconds': l.get('total_timer_time'), 'distance_m': l.get('total_distance'), 'avg_hr': l.get('avg_heart_rate')} for i, l in enumerate(a.get('laps', []))]}
    if a['sport'] == 'bike':
        out['bike'] = {k: number(s.get(field), True) for k, field in [('avg_power_w', 'avg_power'), ('max_power_w', 'max_power'), ('normalized_power_w', 'normalized_power'), ('cadence_rpm', 'avg_cadence'), ('work_j', 'total_work')]}
    return out


def read_activity(base, ident):
    """Read only the chosen file; never scan historical ride CSVs to open a report."""
    from pathlib import Path
    import re, loads
    if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', ident):
        raise ValueError('Choose an imported activity ID from the calendar')
    base=Path(base)
    for suffix, reader in [('.fit', loads._from_fit), ('.tcx', loads._from_tcx)]:
        path=base/'activities'/(ident+suffix)
        if path.is_file():return reader(path)
    path=base/'rides'/(ident+'.csv')
    if path.is_file() and not ident.endswith(('_events','_report')):return loads._from_bridge(path)
    raise ValueError('Activity file not found; import the workout first')
