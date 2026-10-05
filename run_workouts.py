"""Local running outline parser. Targets are prescriptions, never completed activity."""
import copy
import math
import re

MODES = ('run_walk', 'steady', 'speed')
NUM = r'\d+(?:\.\d+)?'
TIME = re.compile(r'(?P<n>'+NUM+r')\s*(?P<u>minutes?|mins?|seconds?|secs?)\b', re.I)
DIST = re.compile(r'(?P<n>'+NUM+r')\s*(?P<u>km|kilometers?|kilometres?|miles?|mi|meters?|metres?|m)\b', re.I)


def parse(fields, repeats=1, mode='run_walk'):
    if not isinstance(fields, dict) or mode not in MODES:
        raise ValueError('Use running fields and choose run/walk, steady, or speed')
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 10:
        raise ValueError('Repeat count must be 1–10')
    source = {k: str(fields.get(k) or '') for k in ('warmup', 'main', 'cooldown')}
    if any(len(v) > 6000 for v in source.values()):
        raise ValueError('Keep each section under 6,000 characters')
    rows, notes, issues = [], [], []
    for section, text in source.items():
        for line in re.split(r'[\n;]+', text):
            line = line.strip()
            if not line:
                continue
            first_index = len(rows)
            group = re.fullmatch(r'(\d+)\s*[x×]\s*\((.+)\)(.*)', line, re.I)
            simple = re.match(r'(\d+)\s*[x×]\s*(.+)',line,re.I) if not group else None
            count = int(group[1]) if group else int(simple[1]) if simple else 1
            chunks = re.split(r'\s*/\s*(?!km\b|mi\b)', group[2],flags=re.I) if group else [simple[2] if simple else line]
            if group:
                chunks = [c + ' ' + group[3] for c in chunks]
            if not 1 <= count <= 100:
                issues.append('Interval repetitions must be 1–100'); continue
            for chunk in chunks:
                tm, ds = TIME.search(chunk), DIST.search(chunk)
                if not tm and not ds:
                    notes.append({'section': section, 'text': chunk}); continue
                # A line with multiple separate efforts needs a separator or a grouped interval.
                if len(TIME.findall(chunk)) > 1 or len(DIST.findall(chunk)) > 1:
                    issues.append('Separate each effort with a new line, semicolon, or a repeated (run / walk) block: '+chunk); continue
                minutes = float(tm['n']) / (60 if tm['u'].lower().startswith('s') else 1) if tm else None
                distance = float(ds['n']) * (1000 if ds['u'].lower().startswith('k') else 1609.344 if ds['u'].lower().startswith('mi') else 1) if ds else None
                pace = re.search(r'\bpace\s*(\d{1,2}):(\d{2})\s*/\s*km\b', chunk, re.I)
                if pace:
                    seconds = int(pace[1])*60+int(pace[2])
                    if int(pace[2]) >= 60 or not 120 <= seconds <= 1800:
                        issues.append('Review the running pace: '+chunk); continue
                    if distance is not None and minutes is None: minutes = distance/1000*seconds/60
                    elif minutes is not None and distance is None: distance = minutes*60/seconds*1000
                kind = 'walk' if re.search(r'\bwalk(?:ing)?\b', chunk, re.I) else 'run' if re.search(r'\b(?:run(?:ning)?|jog(?:ging)?|stride|sprint)\b', chunk, re.I) else 'mobility' if re.search(r'\b(?:mobility|stretch|roll|swing)\b', chunk, re.I) else 'run' if section == 'main' else 'movement'
                zone = re.search(r'\b(?:zone|z)\s*([1-5])\b', chunk, re.I)
                hr = re.search(r'('+NUM+r')\s*[-–]\s*('+NUM+r')\s*bpm\b', chunk, re.I)
                cadence = re.search(r'('+NUM+r')\s*(?:steps?\s*/\s*min|spm)\b', chunk, re.I)
                row = {'section': section, 'kind': kind, 'text': chunk.strip(), 'minutes': minutes, 'distance_m': distance,
                       'zone': int(zone[1]) if zone else None, 'hr': [float(hr[1]), float(hr[2])] if hr else None,
                       'cadence': float(cadence[1]) if cadence else None}
                if minutes is not None and not 0 < minutes <= 600 or distance is not None and not 0 < distance <= 100000:
                    issues.append('Duration or distance is out of range: '+chunk); continue
                if row['hr'] and not 30 <= row['hr'][0] <= row['hr'][1] <= 240 or row['cadence'] is not None and not 30 <= row['cadence'] <= 300:
                    issues.append('Review heart rate or steps per minute: '+chunk); continue
                rounds = count*(repeats if section == 'main' else 1)
                for n in range(rounds): rows.append({**row, 'round': n+1 if rounds>1 else None})
            if group:
                rows[first_index:] = sorted(rows[first_index:],key=lambda r:r['round'] or 1)
    if len(rows)>200:
        raise ValueError('Maximum 200 running stages')
    minutes = sum(r['minutes'] or 0 for r in rows)
    distance = sum(r['distance_m'] or 0 for r in rows)
    return {'fields': source, 'repeats': repeats, 'mode': mode, 'stages': rows, 'notes': notes, 'issues': issues,
            'valid': bool(rows) and any(r['section']=='main' for r in rows) and not issues,
            'minutes': round(minutes,4), 'distance_m': round(distance,2),
            'time_complete': all(r['minutes'] is not None for r in rows) and not notes,
            'distance_complete': all(r['distance_m'] is not None for r in rows if r['kind'] in ('run','walk'))}


def validate(recipe):
    if not isinstance(recipe, dict): raise ValueError('Running recipe must be an object')
    out = parse(recipe.get('fields'), recipe.get('repeats',1), recipe.get('mode','run_walk'))
    if not out['valid']: raise ValueError('; '.join(out['issues']) or 'Write a timed or distance-based main running set')
    return out


def exposure(recipe, profile):
    """Same impact proxy as imported activities; show unknowns rather than invent speed."""
    import loads
    recipe = validate(recipe)
    steps = points = 0.0
    assumptions, unknown = [], []
    mass = profile.get('weight_kg')
    if not isinstance(mass,(int,float)) or isinstance(mass,bool) or not math.isfinite(mass) or not 20 <= mass <= 350: mass = None
    prior = profile.get('run_cadence',150)
    if not isinstance(prior,(int,float)) or not math.isfinite(prior) or not 30 <= prior <= 300: prior = 150
    for r in recipe['stages']:
        if r['kind'] not in ('run','walk'): continue
        cadence = r['cadence'] or (105 if r['kind']=='walk' else prior)
        if not r['cadence']: assumptions.append(f"{r['kind'].title()} steps assume {cadence:g} steps/min; actual cadence may differ.")
        if r['minutes'] is not None: steps += r['minutes']*cadence
        else: unknown.append('A distance-only stage needs duration or pace to estimate steps.')
        if not r['distance_m'] or not r['minutes'] or mass is None:
            unknown.append('Impact needs distance and time for every run/walk stage, plus body weight. Missing inputs keep the estimate incomplete.'); continue
        pts, _, _ = loads.foot_impact({'sport':r['kind'],'minutes':r['minutes'],'distance_m':r['distance_m'],'records':[],'descent_m':0}, {'weight_kg':mass,'run_cadence':cadence})
        # foot_impact uses a fixed walking prior unless a cadence stream is supplied.
        if r['kind']=='walk' and r['cadence']:
            n = r['minutes']*cadence
            pts=n*(loads.step_force(mass,r['distance_m']/(r['minutes']*60),cadence)/loads.REF_FORCE)**loads.POWER*loads.REF_POINTS_PER_STEP
        points += pts
    return {'estimated_steps':round(steps) if not any('distance-only' in x for x in unknown) else None,
            'impact_points':round(points,2) if not unknown else None,
            'assumptions':list(dict.fromkeys(assumptions)), 'unknown':list(dict.fromkeys(unknown)),
            'basis':'Existing Hub step-impact exposure model on level ground. A planning estimate, not measured tissue force or recovery clearance.'}


def add(d,date,req):
    import coach,training_block
    recipe=validate(req.get('run_recipe'))
    minutes=float(req.get('minutes') or recipe['minutes'])
    if not math.isfinite(minutes) or not 1<=minutes<=600 or minutes+0.01<recipe['minutes']:
        raise ValueError('Session time must include all running stages')
    if recipe['time_complete'] and abs(minutes-recipe['minutes'])>.05:
        raise ValueError(f"Running stages total {recipe['minutes']:g} minutes. Review session duration.")
    candidate=copy.deepcopy(d);items=copy.deepcopy(training_block.sessions(candidate['plans'].get(date) or {}))
    index=req.get('index')
    entry={k:req[k] for k in ('sport','name','note','steps','typed_workout') if k in req}
    entry.update(sport='run',minutes=minutes,run_recipe=recipe)
    if index is None:items.append(entry)
    elif isinstance(index,int) and not isinstance(index,bool) and 0<=index<len(items) and items[index]['sport']=='run':items[index]=entry
    else:raise ValueError('Choose an existing running session')
    coach.set_sessions(candidate,date,items,draft=True)
    return candidate,index if index is not None else len(items)-1
