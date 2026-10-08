"""Separate execution of prescribed work from edits to the prescription.

Snapshots start when this version first observes a plan. Earlier edits cannot be
reconstructed. A skip is not a plan revision and is never credited as training.
"""
import copy
import datetime as dt

FIELDS = ('sport', 'minutes', 'name', 'steps', 'workout', 'lifts', 'bike_plan',
          'swim_recipe', 'run_recipe', 'typed_workout', 'workout_goals', 'route_id', 'cadence', 'focus')


def prescriptions(d, plan):
    import coach, training_block
    return [{k: copy.deepcopy(s[k]) for k in FIELDS if k in s}
            for raw in training_block.sessions(plan or {})
            for s in [coach.scheduled_view(d, raw)] if s.get('sport') != 'rest']


def capture(d, previous):
    """Called by the normal save boundary; includes changes made through MCP."""
    now = dt.datetime.now().isoformat(timespec='seconds')
    ledger = d.setdefault('schedule_tracking', {'started': now, 'days': {}, 'revisions': []})
    for date in sorted(set(previous.get('plans', {})) | set(d.get('plans', {}))):
        before = prescriptions(previous, previous.get('plans', {}).get(date))
        after = prescriptions(d, d.get('plans', {}).get(date))
        if date not in ledger['days']:
            ledger['days'][date] = {'initial': copy.deepcopy(before or after), 'observed_at': now}
        if before != after:
            # An initial schedule is a target, not a change to an existing target.
            if before or date in previous.get('schedule_tracking', {}).get('days', {}):
                ledger['revisions'].append({'date': date, 'at': now, 'before': before, 'after': after,
                                            'reason': 'prescription changed'})


def minutes(items):
    return sum(float(s.get('minutes') or 0) for s in items)


def summary(d, start, end, done=None, as_of=None):
    import coach, training_block
    cutoff = min(end, as_of or coach.today())  # today remains open, never auto-missed
    counts = dict(completed=0, partial=0, cancelled=0, missed=0)
    prescribed = performed = initial = 0.0
    rows = []
    ledger = d.get('schedule_tracking') or {}
    day = dt.date.fromisoformat(start)
    while day.isoformat() < cutoff:
        date = day.isoformat()
        sessions = [coach.scheduled_view(d, s) for s in training_block.sessions(d.get('plans', {}).get(date) or {})]
        coach.attach_completions(d, date, sessions, copy.deepcopy((done or {}).get(date, [])))
        for s in sessions:
            if s.get('sport') not in coach.TRAINABLE or not float(s.get('minutes') or 0):
                continue
            planned = float(s['minutes']); actual = (s.get('completion') or {}).get('minutes')
            if s.get('skipped_id'):
                status = 'cancelled'
            elif s.get('completion'):
                status = 'partial' if actual is not None and actual < planned else 'completed'
            else:
                status = 'missed'
            counts[status] += 1; prescribed += planned
            if status in ('completed', 'partial') and actual is not None:
                performed += min(planned, max(0, actual))
            rows.append({'date': date, 'name': s.get('name'), 'sport': s['sport'], 'status': status,
                         'planned_minutes': planned, 'recorded_minutes': actual})
        baseline = ledger.get('days', {}).get(date)
        initial += minutes(baseline['initial']) if baseline else minutes(prescriptions(d, d.get('plans', {}).get(date)))
        day += dt.timedelta(days=1)
    changes = [x for x in ledger.get('revisions', []) if start <= x['date'] < cutoff]
    return {'start': start, 'end_exclusive': cutoff, 'counts': counts, 'sessions': rows,
            'prescribed_minutes': round(prescribed, 1), 'matched_recorded_minutes': round(performed, 1),
            'completion_share': round(performed / prescribed, 3) if prescribed else None,
            'initial_minutes': round(initial, 1), 'target_change_minutes': round(prescribed - initial, 1),
            'plan_revision_count': len(changes), 'plan_revisions': changes,
            'tracking_started': ledger.get('started'),
            'basis': 'Finished days only. Cancellations retain their prescribed target and count as unperformed. '
                     'Plan edits are separate, tracked from first observation; earlier edits are unknown. '
                     'Recorded work and feedback describe outcomes; adherence alone does not establish progress.'}
