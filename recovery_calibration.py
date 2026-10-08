"""One athlete-specific running time scale, learned from dated recovery episodes.

The scale is a provisional planning fit to reported symptoms, not measured tissue
repair or an injury probability. Constants below are explicit learning policies.
Read/preview never saves athlete data. Only the reviewed API apply path persists.
"""
import copy
import datetime as dt
import math
import statistics
import time
import zlib
import json

WINDOW_DAYS = 42
SCALE_BOUNDS = (.25, 2.0)
VERSION = 1
LIMIT = 1.5


def parameters(profile=None):
    scale = (profile or {}).get('time_scale', 1.0)
    if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale) or not SCALE_BOUNDS[0] <= scale <= SCALE_BOUNDS[1]:
        raise ValueError('Running recovery time scale is outside its reviewed bounds')
    return {'version': VERSION, 'time_scale': scale,
            'plateau_days_per_block': round(5 * scale, 5),
            'decline_days_per_block': round(3 * scale, 5), 'tail_days': round(120 * scale, 5),
            'source': 'pooled reported recovery' if profile else 'provisional starting assumptions',
            'meaning': 'One shared time scale; smaller means faster modeled decline. Tail shape is coupled, not independently measured.'}


def _rem(load):
    return load.get('systems', {}).get('impact', {}).get('tissue', {}).get('remodeling') or {}


def _reports(d, today):
    import journal
    out = {}
    for date, c in d.get('checkins', {}).items():
        if date > today: continue
        c = journal.effective(c)
        if all(isinstance(c.get(k), (int, float)) and not isinstance(c[k], bool) and math.isfinite(c[k]) and 1 <= c[k] <= 10 for k in ('feet', 'legs')):
            out[date] = {k: c[k] for k in ('feet', 'legs', 'hops') if c.get(k) is not None}
    return out


def _clean(c):
    return c['feet'] <= 3 and c['legs'] <= 3 and (c.get('hops') is None or c['hops'] >= 10)


def episodes(d, load, today):
    """An observed transition bracket, never an imputed recovery date.

    A run-free interval needs an initial non-clean morning and two consecutive
    reported clean mornings (at most three calendar days apart). Missing, neutral
    and ambiguous intervals cannot accelerate the curve. Several stacked runs
    yield one interval, not multiple independent observations.
    """
    start = (dt.date.fromisoformat(today) - dt.timedelta(days=WINDOW_DAYS - 1)).isoformat()
    days = [x for x in load.get('days', []) if x['date'] <= today]
    run_dates = [x['date'] for x in days if x.get('sports', {}).get('run', {}).get('impact', 0) > 0]
    reports = _reports(d, today)
    result = []
    for i, date in enumerate(run_dates):
        if date < start: continue
        stop = run_dates[i + 1] if i + 1 < len(run_dates) else None
        observations = [(day, c) for day, c in sorted(reports.items()) if date < day <= today and (stop is None or day < stop)]
        row = {'id': date, 'last_run': date, 'status': 'awaiting_response', 'observations': observations}
        bad = None; previous_clean = None
        for day, c in observations:
            if not _clean(c):
                bad = day; previous_clean = None
            elif bad:
                if previous_clean and (dt.date.fromisoformat(day) - dt.date.fromisoformat(previous_clean)).days <= 3:
                    row.update(status='eligible', last_nonclean=bad, first_clean=previous_clean, confirmed_on=day)
                    break
                previous_clean = day
        if observations and not bad: row['status'] = 'no_recovery_transition'
        if row['status'] == 'eligible':
            end = row['confirmed_on']
            # Changed block sizing / reviewed phase transitions and competing leg
            # work make recovery speed unidentifiable from this interval alone.
            confounds = []
            if any(date < x.get('date', '') <= end for x in d.get('capacity_adjustments', []) if x.get('target') == 'running_block'):
                confounds.append('running block capacity changed during interval')
            if any(date < x.get('date', '') <= end for x in (d.get('run_progression') or {}).get('reviews', [])):
                confounds.append('reviewed plateau transition during interval')
            if any(date < x.get('date', '') <= end and x.get('leg_points', 0) > 0 for x in (d.get('lifting') or {}).get('logs', [])):
                confounds.append('logged leg strength competes with the soreness signal')
            if any(date < x.get('date', '') <= end and x.get('sport') != 'run' and (x.get('impact', 0) > 0 or x.get('sport') == 'gym' and x.get('muscle', 0) > 0) for x in load.get('activities', [])):
                confounds.append('other recorded impact or gym leg load during interval')
            if confounds: row.update(status='confounded', reasons=confounds)
        result.append(row)
    return result


def _predict(d, load, base, row, scale):
    import damage, loads
    # Freeze capacity; fitting dose and time simultaneously would hide which was wrong.
    reference = _rem(load).get('reference_points')
    end = row.get('confirmed_on') or load['days'][-1]['date']
    days = [x for x in load['days'] if x['date'] <= end]
    prof = loads.load_profile(base)
    reset = max((c.get('run_date', '') for c in ((d.get('benchmarks') or {}).get('calibrations') or {}).values() if c.get('result') == 'set' and c.get('clean_watch')), default='') or None
    curve = damage.remodeling_response([x['date'] for x in days], [x.get('sports', {}).get('run', {}).get('impact', 0) for x in days],
        block=reference, weight_kg=prof['weight_kg'],
        walking=loads.walking_inputs(load.get('activities', []), loads.load_steps(base), prof),
        reset_before=reset, recovery_curve={'time_scale': scale})
    series = curve['history'] + curve['projection']
    after = next((x['score'] for x in series if x['date'] == row['last_run']), 0)
    if after < LIMIT: return None
    return next((x['date'] for x in series if x['date'] > row['last_run'] and x['score'] < LIMIT), None)


def review(d, load, base, today):
    state = d.get('running_recovery_calibration') or {}
    current = parameters(state.get('profile'))
    rows = episodes(d, load, today)
    eligible = [r for r in rows if r['status'] == 'eligible']
    ref = _rem(load).get('reference_points')
    used = set(state.get('used_episodes', []))
    informative = []
    if ref and load.get('days'):
        for r in eligible:
            predicted = _predict(d, load, base, r, current['time_scale'])
            if predicted:
                r['predicted_clean_date'] = predicted
                informative.append(r)
            else: r['status'] = 'below_threshold_uninformative'
    new = [r for r in informative if r['id'] not in used]
    result = {'as_of': today, 'current': current, 'episodes': rows, 'new_episodes': len(new),
        'status': 'more_evidence_needed', 'candidate': None,
        'policy': {'window_calendar_days': WINDOW_DAYS, 'scale_bounds': list(SCALE_BOUNDS),
                   'early_max_step_fraction': .20, 'mature_max_step_fraction': .02,
                   'maturity_distinct_report_days': 42, 'repeated_same_episode_updates': False},
        'validation': {'status': 'not_prospectively_validated', 'accuracy': None,
                       'meaning': 'Historical symptom fit is not an 80% per-run probability, tissue repair measurement, or injury clearance.'},
        'notice': 'Capacity is held fixed during fitting. Missing reports are unknown. A run completed during a hold does not itself establish recovery. Existing symptoms, hop checks and protected return-to-run rules still apply.'}
    if not new: return result
    # Pool up to six weeks. Search one parameter; interval-censored clean dates,
    # equal episode weight, capped residuals, prior tie-break; no per-run tuning.
    def loss(scale):
        values = []
        for row in informative:
            predicted = _predict(d, load, base, row, scale)
            if not predicted: return float('inf')
            p = dt.date.fromisoformat(predicted)
            lo, hi = dt.date.fromisoformat(row['last_nonclean']) + dt.timedelta(days=1), dt.date.fromisoformat(row['first_clean'])
            error = max((lo - p).days, (p - hi).days, 0)
            span = max(1, (hi - dt.date.fromisoformat(row['last_run'])).days)
            values.append(min(4.0, (error / span) ** 2))
        return statistics.mean(values)
    grid = [round(.25 + i * .025, 5) for i in range(71)] + [current['time_scale']]
    losses = [(loss(scale), abs(math.log(scale / current['time_scale'])), scale) for scale in grid]
    best_loss, _, target = min(losses)
    before_loss = loss(current['time_scale'])
    if before_loss - best_loss < .005:
        result['status'] = 'consistent_with_current'; return result
    seen_days = set(state.get('learned_report_days', []))
    maturity = min(42, len(seen_days))
    gain = 1 / (3 + maturity)
    max_step = .20 - .18 * maturity / 42
    old = current['time_scale']
    proposed = max(old * (1 - max_step), min(old * (1 + max_step), old + gain * (target - old)))
    proposed = round(max(SCALE_BOUNDS[0], min(SCALE_BOUNDS[1], proposed)), 5)
    blocked = []
    if proposed < old:
        import progression, lifting
        if any(set(x['regions']).intersection(lifting.LEG_REGIONS) for x in progression.active_symptoms(d, today)):
            blocked.append('Unresolved lower-body symptom reports need review before shortening')
        reports = _reports(d, today)
        if today in reports and not _clean(reports[today]): blocked.append('Current lower-leg response is not clean')
    result.update(status='blocked' if blocked else 'review_candidate', reasons=blocked,
        candidate={'time_scale': proposed, 'pooled_target': target, 'learning_gain': round(gain, 5),
            'max_step_fraction': round(max_step, 5), 'direction': 'faster' if proposed < old else 'slower',
            'parameters': parameters({'time_scale': proposed}), 'before_loss': round(before_loss, 5),
            'pooled_loss': round(best_loss, 5), 'reference_points_held_fixed': ref,
            'episode_ids': [r['id'] for r in new],
            'report_days': sorted({day for r in new for day, _ in r['observations'] if day <= r['confirmed_on']}),
            'bound_reached': target in SCALE_BOUNDS})
    return result


def revision(d, load, base, today):
    import program_drafts
    from pathlib import Path
    return program_drafts.digest({'state': program_drafts.revision(d, base, {}, [], today),
        'curve_code': (Path(__file__).read_text()), 'dose_days': load.get('days'), 'reference': _rem(load).get('reference_points')})


def preview(d, load, base, today):
    import program_drafts
    result = review(d, load, base, today)
    if result['status'] != 'review_candidate': return result
    return program_drafts.store(base, {'kind': 'running_recovery_curve', 'review': result}, revision(d, load, base, today))


def apply(d, load, base, today, token, approved):
    import coach, program_drafts
    if approved is not True: raise ValueError('Explicit approval of the recovery preview is required')
    if not isinstance(token, str) or not token: raise ValueError('Preview the recovery curve first')
    db = program_drafts.connect(base)
    try:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT revision,expires,payload FROM drafts WHERE id=?', (token,)).fetchone()
        if not row: raise program_drafts.Conflict('Recovery draft is unavailable; preview again')
        proposal = json.loads(zlib.decompress(row[2]))
        if proposal.get('kind') != 'running_recovery_curve': raise ValueError('Choose a recovery curve draft')
        receipts = (d.get('running_recovery_calibration') or {}).get('history', [])
        prior = next((r for r in receipts if r['draft_id'] == token), None)
        if prior: return {**prior, 'already_applied': True}
        if time.time() > row[1] or row[0] != revision(d, load, base, today):
            raise program_drafts.Conflict('Training evidence or model changed; preview the recovery curve again')
        review_data = proposal['review']; candidate = review_data['candidate']
        state = d.setdefault('running_recovery_calibration', {})
        receipt = {'draft_id': token, 'date': today, 'before': review_data['current'],
                   'after': candidate['parameters'], 'evidence': copy.deepcopy(candidate),
                   'validation': review_data['validation']}
        state['profile'] = {'version': VERSION, 'time_scale': candidate['time_scale'], 'updated_on': today}
        state['used_episodes'] = sorted(set(state.get('used_episodes', [])) | set(candidate['episode_ids']))
        state['learned_report_days'] = sorted(set(state.get('learned_report_days', [])) | set(candidate['report_days']))
        state.setdefault('history', []).append(receipt)
        coach.save(d); db.commit()
        return receipt
    finally: db.close()
