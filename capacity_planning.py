"""Goal demand and observed training evidence, without predicting event results.

Energy, mechanical exposure and repeated training tolerance stay separate.
No read operation changes calibration, a hold, or the active program.
"""
import datetime as dt
import math

SPORTS = ('run', 'ride', 'swim', 'gym')
NOTICE = ('These are estimated demands and observed training, not a predicted finish time '
          'or proof of recovery. Meeting an estimate does not guarantee the event result.')


def number(value, name, low=0, high=1e7):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low < value <= high:
        raise ValueError(f'{name} must be a finite number greater than {low} and at most {high}')
    return float(value)


def goals(raw):
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > 12:
        raise ValueError('Provide at most 12 capacity demands')
    out = []
    for item in raw:
        if not isinstance(item, dict) or item.get('sport') not in SPORTS:
            raise ValueError('Each demand needs run, ride, swim or gym')
        row = {'sport': item['sport'], 'label': str(item.get('label') or item['sport'])[:100]}
        for key in ('distance_m', 'duration_min', 'power_w', 'weight_kg', 'reps', 'sets', 'weekly_minutes'):
            if item.get(key) is not None:
                row[key] = number(item[key], key)
        if not any(k in row for k in ('distance_m', 'duration_min', 'weight_kg', 'weekly_minutes')):
            raise ValueError('A demand needs distance, duration, lifting weight or weekly minutes')
        if 'power_w' in row and row['sport'] != 'ride':
            raise ValueError('Power targets apply to cycling')
        if any(k in row for k in ('weight_kg', 'reps', 'sets')) and row['sport'] != 'gym':
            raise ValueError('Lifting weight, reps and sets apply to strength')
        if row['sport'] == 'gym' and 'weight_kg' in row and 'reps' not in row:
            raise ValueError('A lifting weight demand also needs repetitions')
        grade = item.get('grade', 0)
        if isinstance(grade, bool) or not isinstance(grade, (int, float)) or not math.isfinite(grade) or not 0 <= grade <= .25:
            raise ValueError('Running grade is a fraction from 0 to 0.25; downhill needs a separate model')
        row['grade'] = float(grade)
        out.append(row)
    return out


def demand(row, profile):
    result = {'target': row, 'confidence': 'provisional', 'energy': None,
              'mechanical': None, 'unknown': [], 'assumptions': []}
    minutes, distance = row.get('duration_min'), row.get('distance_m')
    mass = profile.get('weight_kg')
    if mass is not None:mass = number(mass, 'Athlete body weight', high=500)
    if row['sport'] == 'run' and minutes and distance:
        speed = distance / minutes
        result['pace_seconds_per_km'] = round(minutes * 60 * 1000 / distance, 1)
        # ACSM steady running cost equation; do not extrapolate to walking,
        # downhill, sprinting, or infer VO2max from a requested goal.
        if 134 <= speed <= 300:
            oxygen = .2 * speed + .9 * speed * row['grade'] + 3.5
            result['oxygen_cost_ml_kg_min'] = round(oxygen, 2)
            result['assumptions'].append('Steady running at the requested speed and grade; 5 kcal per litre of oxygen. Individual running economy is unknown.')
            if mass is not None:
                mass = number(mass, 'Athlete body weight', high=500)
                result['energy'] = {'gross_kcal': round(oxygen * mass / 1000 * 5 * minutes, 1),
                                    'net_kcal': round((oxygen - 3.5) * mass / 1000 * 5 * minutes, 1),
                                    'gross_kcal_per_hour': round(oxygen * mass / 1000 * 5 * 60, 1),
                                    'formula': 'VO2 = 0.2 × speed_m_min + 0.9 × speed_m_min × grade + 3.5; kcal = VO2 × kg / 1000 × 5 × minutes',
                                    'source': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC3743617/'}
            else:
                result['unknown'].append('Body weight is missing; energy and impact are not estimated.')
        else:
            result['unknown'].append('Requested speed falls outside this conservative steady-running equation range.')
        if mass is not None:
            import loads
            cadence = profile.get('run_cadence', 150)
            number(cadence, 'Running cadence', high=300)
            pts, steps, equivalent = loads.foot_impact({'sport': 'run', 'minutes': minutes, 'distance_m': distance, 'records': []}, {'weight_kg': mass, 'run_cadence': cadence})
            result['mechanical'] = {'impact_points': round(pts, 1), 'estimated_steps': steps,
                                    'runner_equivalent_km': round(equivalent, 2), 'model': 'loads.foot_impact',
                                    'meaning': 'Custom exposure proxy, not tissue force, injury risk or recovery clearance.'}
            result['assumptions'].append(f'Impact assumes {cadence} steps/min and no downhill; uphill impact is not modeled here.')
    elif row['sport'] == 'ride' and minutes and row.get('power_w'):
        kj = row['power_w'] * minutes * 60 / 1000
        result['energy'] = {'mechanical_kj': round(kj, 1),
                            'metabolic_kcal_range': [round(kj / (.25 * 4.184), 1), round(kj / (.20 * 4.184), 1)],
                            'metabolic_kcal_per_hour_range': [round(kj / (.25 * 4.184) * 60 / minutes, 1), round(kj / (.20 * 4.184) * 60 / minutes, 1)],
                            'formula': 'mechanical_kJ = watts × seconds / 1000; kcal = kJ / (efficiency × 4.184)',
                            'source': 'https://pubmed.ncbi.nlm.nih.gov/3425344/'}
        result['assumptions'].append('Constant power; illustrative gross efficiency range 20–25%, not an individual fitted value.')
        result['unknown'].append('Cadence, posture and regional tolerance are needed for mechanical load.')
    elif row['sport'] == 'gym' and row.get('weight_kg'):
        result['mechanical'] = {'external_volume_kg': row['weight_kg'] * row['reps'] * row.get('sets', 1),
                                'meaning': 'External weight × repetitions × sets; not mechanical work, regional load or calories.'}
        result['unknown'].append('Exercise, effort, tempo, range and equipment calibration are needed for regional loading.')
    else:
        result['unknown'].append('Energy and tissue exposure need sport-specific intensity and technique evidence.')
    return result


def review(d, load, today, raw=None, athlete=None):
    now = dt.date.fromisoformat(today)
    profile = {**(athlete or {}), **(load.get('profile') or {})}
    targets = goals(raw if raw is not None else (d.get('program_goal') or {}).get('capacity_demands'))
    rows = []
    for target in targets:
        sport = target['sport']
        activities = [a for a in load.get('activities', []) if ('ride' if a.get('sport') == 'bike' else a.get('sport')) == sport
                      and a.get('date') and 0 <= (now - dt.date.fromisoformat(a['date'])).days <= 42]
        weekly = []
        for offset in range(6):
            end = now - dt.timedelta(days=7 * offset)
            start = end - dt.timedelta(days=6)
            weekly.append({'start': start.isoformat(), 'end': end.isoformat(),
                           'minutes': round(sum(a.get('minutes') or 0 for a in activities if start.isoformat() <= a['date'] <= end.isoformat()), 1)})
        evidence = [{'date': a['date'], 'id': a.get('id'), 'minutes': a.get('minutes'),
                     'distance_m': a.get('distance_m') or (a.get('km') or 0) * 1000,
                     'engine_points': a.get('engine'), 'impact_points': a.get('impact')} for a in activities]
        longest = max((a.get('minutes') or 0 for a in activities), default=None)
        farthest = max((a['distance_m'] for a in evidence), default=None)
        gaps = {}
        if target.get('duration_min'):
            gaps['duration_min'] = None if longest is None else round(max(0, target['duration_min'] - longest), 1)
        if target.get('distance_m'):
            gaps['distance_m'] = None if farthest is None else round(max(0, target['distance_m'] - farthest), 1)
        if target.get('weekly_minutes'):
            gaps['weekly_minutes'] = None if not activities else round(max(0, target['weekly_minutes'] - weekly[0]['minutes']), 1)
        # Do not combine the fastest short effort and longest slow session into
        # an invented demonstration of the target effort.
        comparable = [a for a in evidence if target.get('distance_m') and target.get('duration_min')
                      and a['distance_m'] >= target['distance_m'] and a.get('minutes')
                      and a['minutes'] * 60 / a['distance_m'] <= target['duration_min'] * 60 / target['distance_m']]
        description = ('You have recorded a comparable effort. We still need to review how you recovered before choosing maintenance or more training.' if comparable else 'This goal is not yet demonstrated by your recent training. We will build toward handling its effort and recovering from it.' if activities else 'We need recent workouts or an assessment to judge how demanding this goal is for you.')
        rows.append({**demand(target, profile), 'observed': {'sessions': len(evidence),
                     'longest_minutes': longest, 'farthest_m': farthest, 'weeks': weekly,
                     'recent_sessions': sorted(evidence, key=lambda a: a['date'], reverse=True)[:8]},
                     'exposure_gaps': gaps, 'matching_efforts': comparable[-3:], 'explanation': description,
                     'next_step': 'Review maintenance and delayed recovery' if comparable else 'Build or assess the missing abilities within current constraints',
                     'tolerance': 'Unconfirmed: exposure does not establish repeated recovery tolerance.'})
    import progression
    return {'as_of': today, 'mode': 'capacity', 'demands': rows, 'notice': NOTICE,
            'tolerance_trends': tolerance_trends(d, load, today),
            'profile': {k: profile.get(k) for k in ('weight_kg', 'experience', 'start_state')},
            'experience_rule': 'Experience informs initial planning confidence, not a calorie discount or recovery clearance.',
            'active_symptoms': progression.active_symptoms(d, today),
            'workflow': ['Read goal demand, recent training and calibration gaps',
                         'Review per-sport eligibility and shared-system constraints',
                         'Draft phase intent and session budgets',
                         'Compare whole-calendar load projections and repair conflicts',
                         'Detail the coming week using sport templates',
                         'Review and apply the exact draft, then read it back',
                         'Reassess at check-ins using actual dose and delayed response'],
            'planning_rule': 'Capacity gaps guide priorities; current holds, recovery/taper purpose and available time govern prescriptions. No gap grants permission to exceed a limit.'}


def record_followup(d, date, index, fields, done, today):
    """Explicit delayed response; never changes limits or clears symptoms."""
    import coach, training_block, copy
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError('Choose a session index')
    age = (dt.date.fromisoformat(today) - dt.date.fromisoformat(date)).days
    if not 1 <= age <= 14:
        raise ValueError('Delayed recovery is recorded 1–14 days after the workout')
    key = f'{date}:{index}'
    report = d.get('training_feedback', {}).get(key)
    if not report:
        raise ValueError('Record the completed session effort report first')
    value = fields.get('recovery')
    if value not in ('good', 'difficult', 'uncertain'):
        raise ValueError('Recovery is good, difficult or uncertain')
    sessions = training_block.sessions(d.get('plans', {}).get(date) or {})
    marked = coach.attach_completions(d, date, copy.deepcopy(sessions), copy.deepcopy(done.get(date, [])))
    if index >= len(marked) or not marked[index].get('completion'):
        raise ValueError('A recorded completion is required')
    if marked[index].get('name') != report.get('session_name'):
        raise ValueError('The session has changed; review its effort report first')
    entry = {'session_date': date, 'session_index': index, 'reported_on': today,
             'recovery': value, 'note': str(fields.get('note') or '')[:1000]}
    store = d.setdefault('capacity_followups', {})
    if key in store:
        d.setdefault('capacity_followup_history', []).append(store[key])
    store[key] = entry
    return entry


def tolerance_trends(d, load, today):
    """Six-week comparison evidence, not automatic readiness or clearance."""
    import statistics
    now = dt.date.fromisoformat(today)
    result = []
    for sport in SPORTS:
        series = []
        for a in load.get('activities', []):
            if ('ride' if a.get('sport') == 'bike' else a.get('sport')) != sport or not a.get('date'):
                continue
            age = (now - dt.date.fromisoformat(a['date'])).days
            if not 0 <= age < 42 or not a.get('minutes'):
                continue
            reports = [r for r in d.get('training_feedback', {}).values() if r.get('date') == a['date'] and r.get('sport') == sport]
            peers = [x for x in load.get('activities', []) if x.get('date') == a['date'] and x.get('sport') == a.get('sport')]
            report = reports[0] if len(reports) == 1 and len(peers) == 1 else None
            follow = d.get('capacity_followups', {}).get(f"{a['date']}:{report['session_index']}") if report else None
            calories = a.get('calories_kcal')
            valid = isinstance(calories, (int, float)) and not isinstance(calories, bool) and math.isfinite(calories) and calories > 0
            bad = bool(report and (report.get('heart_rate_issue') or any(x.get('severity', 0) > 0 for x in report.get('symptoms', [])) or report.get('effort') == 'too_hard'))
            series.append({'date': a['date'], 'id': a.get('id'), 'minutes': a['minutes'],
                           'kcal_per_hour': round(calories * 60 / a['minutes'], 1) if valid else None,
                           'energy_basis': a.get('calories_basis'), 'source': a.get('source'),
                           'engine_points': a.get('engine'), 'rpe': (report or {}).get('rpe'),
                           'delayed_recovery': (follow or {}).get('recovery'), 'negative_report': bad,
                           'clean_followup': bool(report and follow and follow['recovery'] == 'good' and not bad)})
        recent = [x for x in series if (now - dt.date.fromisoformat(x['date'])).days < 21]
        earlier = [x for x in series if (now - dt.date.fromisoformat(x['date'])).days >= 21]
        signal = 'insufficient evidence'
        why = 'Compare repeated same-sport efforts, duration, effort and explicit delayed recovery; missing follow-ups are unknown.'
        if any(x['negative_report'] or x['delayed_recovery'] == 'difficult' for x in recent):
            signal = 'recovery concern'
            why = 'A recent adverse report needs review; reduced workload alone is not declining capacity.'
        else:
            clean_new = [x for x in recent if x['clean_followup'] and x['kcal_per_hour'] is not None and x['rpe'] is not None]
            clean_old = [x for x in earlier if x['clean_followup'] and x['kcal_per_hour'] is not None and x['rpe'] is not None]
            if len(clean_new) >= 3 and len(clean_old) >= 3:
                sources = {(x['source'], x['energy_basis']) for x in clean_new + clean_old}
                median = lambda rows, key: statistics.median(x[key] for x in rows)
                ratio = median(clean_new, 'minutes') / median(clean_old, 'minutes')
                if len(sources) == 1 and None not in next(iter(sources)) and .8 <= ratio <= 1.25:
                    rate_ratio = median(clean_new, 'kcal_per_hour') / median(clean_old, 'kcal_per_hour')
                    if rate_ratio >= 1.1 and median(clean_new, 'rpe') <= median(clean_old, 'rpe'):
                        signal = 'improving tolerance signal'
                        why = 'Repeated higher estimated energy rates, similar duration, no higher reported effort and good delayed recovery. Review conditions and technique before changing training.'
                    else:
                        signal = 'no clear change'
                        why = 'Comparable recorded efforts do not establish an increase. Recovery phases can support adaptation without higher exposure.'
        result.append({'sport': sport, 'signal': signal, 'why': why,
                       'series': sorted(series, key=lambda x: x['date']),
                       'assumptions': 'Two 21-day comparison windows; at least three explicitly recovered efforts per window; duration within 20–25%, energy rate increase of 10%. Provisional comparison filters, not physiological thresholds.',
                       'notice': 'Device calories are estimates. This signal does not establish readiness, change calibration or clear a hold.'})
    return result
