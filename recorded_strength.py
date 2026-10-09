"""Source-linked strength presentation. Output estimates never depend on reported RPE."""
import copy, math, re
import lifting, strength_workouts

MODEL_VERSION='reference-friction-0.30-0.60-v1'
MOVEMENT_ALIASES={
    'tank':('tank m4','m4 tank','tank','sled push','sled pushes','tank push','tank pushes'),
    'hip thrust':('hip thrust machine','hip thrusts','hip thrusters','hip thruster','hip thrust'),
    'russian twist':('russian twists','russian twist'),
    'lat pulldown':('lat pulldowns','lat pull-downs','lat pulldown','lat pull-down'),
}

def saved_sets(log):
    if not log:return []
    result=[]
    for row in log.get('lifts',[]):
        for i,sd in enumerate(row.get('set_details') or [row]*row['sets']):
            x={**row,**sd}
            result.append({**{k:x.get(k) for k in ('name','weight','unit','reps','seconds','tempo','hold','rpe','section')},
                'planned_effort':(row.get('planned_effort') or [None]*row['sets'])[i]})
    return result

def recorded_fields(log, metadata=None):
    """Rebuild the editor from structured actuals, never from last typed prose."""
    fields={k:[] for k in ('warmup','main','cooldown')};metadata=metadata or []
    def effort(values):
        if not values or all(v is None for v in values):return ''
        return str(values[0]) if len(set(values))==1 else ', '.join('?' if v is None else str(v) for v in values)
    for i,x in enumerate(log.get('lifts',[])):
        if x.get('done') is False:continue
        sets=x.get('set_details') or [x]*x['sets'];m=metadata[i] if i<len(metadata) else {}
        # Different doses are emitted as individual lines; equal doses stay grouped.
        keys=('weight','unit','reps','seconds','tempo','hold')
        groups=[]
        for j,sd in enumerate(sets):
            if sd.get('done') is False:continue
            row={**x,**sd}
            planned=(x.get('planned_effort') or m.get('planned_effort') or [None]*len(sets))[j]
            if groups and all(groups[-1][0][0].get(k)==row.get(k) for k in keys):groups[-1].append((row,planned))
            else:groups.append([(row,planned)])
        for group in groups:
            row=group[0][0];count=len(group)
            line=f"{x['name']}: {count} x "+(str(row['reps']) if row.get('reps') else f"{row.get('seconds') or 0} seconds")
            if x.get('per_side'):line+=' per side'
            if row.get('weight') is not None:line+=f" @ {row['weight']:g} {row.get('unit') or 'lb'}"
            if row.get('tempo'):line+=' tempo '+row['tempo']
            sled=x.get('sled') or m.get('sled') or {}
            if sled.get('distance_per_trip_m'):line+=f", {sled['distance_per_trip_m']:g} m per trip"
            if sled.get('front_level') is not None and sled.get('front_level')==sled.get('rear_level'):line+=f", both magnets level {sled['front_level']}"
            line+=', planned effort: '+effort([p for _,p in group])+', reported effort: '+effort([r.get('rpe') for r,_ in group])
            how=x.get('how') or m.get('how')
            if how:line+=' — '+str(how).replace(';',',').replace('\n',' ')[:300]
            fields[x.get('section','main')].append(line)
    return {k:'\n'.join(v) for k,v in fields.items()}

def correct_text(log, metadata, text):
    """Bounded corrections on ONE card's actual sets. Ambiguity is an error.

    Supports set/exercise/section references and effort or section changes. It
    does not interpret unrestricted prose or create missing sets from a guess.
    """
    if not isinstance(text,str) or len(text)>18000:raise ValueError('Correction text must be at most 18,000 characters')
    commands=[c for c in re.split(r'[;\n]',text) if c.strip()]
    if len(commands)>30:raise ValueError('Use at most 30 correction lines at once')
    words={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'first':1,'second':2,'third':3,'fourth':4,'fifth':5,'sixth':6}
    flat=[]
    for i,x in enumerate(log['lifts']):
        for j,sd in enumerate(x.get('set_details') or [x]*x['sets']):
            if sd.get('done') is False:continue
            m=copy.deepcopy(metadata[i]) if i<len(metadata) else {}
            row={**copy.deepcopy(x),**copy.deepcopy(sd),'sets':1,'set_details':[copy.deepcopy(sd)]}
            row['planned_effort']=[(x.get('planned_effort') or m.get('planned_effort') or [None]*x['sets'])[j]]
            flat.append((row,m))
    changes=[]
    for command in commands:
        normalized=command.lower()
        for word,n in words.items():normalized=re.sub(r'\b'+word+r'\b',str(n),normalized)
        candidates=list(range(len(flat)));recognized=[]
        section=re.match(r'\s*(?:the\s+)?(warm[ -]?up|main work|cool[ -]?down)\b',normalized)
        if section:
            selected='warmup' if section[1].startswith('warm') else 'cooldown' if section[1].startswith('cool') else 'main'
            candidates=[i for i in candidates if flat[i][0].get('section','main')==selected]
        families=[]
        for family,aliases in MOVEMENT_ALIASES.items():
            used=[a for a in aliases if re.search(r'\b'+re.escape(a)+r'\b',normalized)]
            if used:families.append(family);recognized.extend(used)
        if len(families)>1:raise ValueError('Name one movement per correction line')
        if families:
            family=families[0]
            candidates=[i for i in candidates if (('tank' in flat[i][0]['name'].lower() or 'm4' in flat[i][0]['name'].lower()) if family=='tank' else family in flat[i][0]['name'].lower().replace('pull-down','pulldown'))]
        else:
            names={flat[i][0]['name'].lower() for i in candidates if flat[i][0]['name'].lower() in normalized}
            if len(names)>1:raise ValueError('Name one movement per correction line')
            if names:
                recognized.extend(names);candidates=[i for i in candidates if flat[i][0]['name'].lower() in names]
        level=re.search(r'\blevel\s*(\d+)\b',normalized)
        if level:candidates=[i for i in candidates if re.search(r'\blevel\s*'+level[1]+r'\b',flat[i][0]['name'],re.I)]
        if not candidates:raise ValueError('No matching sets in this workout; clarify the exercise, section or level')
        count=re.search(r'\b1\s+(\d+)\b',normalized) if re.search(r'\bfirst\b',command,re.I) else None
        last=re.search(r'\blast\s+(\d+)\b',normalized)
        span=re.search(r'\bsets?\s*#?\s*(\d+)\s*(?:–|-|through|to)\s*(\d+)\b',normalized)
        listed=re.search(r'\bsets\s*(\d+(?:\s*,\s*\d+)+)',normalized)
        if count or last:
            size=int((count or last)[1])
            if not 1<=size<=len(candidates):raise ValueError('That set range does not exist in this workout')
            indices=candidates[:size] if count else candidates[-size:]
        elif span:
            lo,hi=int(span[1]),int(span[2])
            if not 1<=lo<=hi<=len(candidates):raise ValueError('Set range is reversed or outside this workout')
            indices=candidates[lo-1:hi]
        elif listed:
            numbers=[int(v.strip()) for v in listed[1].split(',')]
            if any(not 1<=v<=len(candidates) for v in numbers):raise ValueError('That set does not exist in this workout')
            indices=[candidates[v-1] for v in dict.fromkeys(numbers)]
        elif re.search(r'\ball\b',normalized) and re.search(r'\bsets\b',normalized):indices=candidates
        elif re.search(r'\blast\s+set\b',normalized):indices=[candidates[-1]]
        else:
            number=re.search(r'\bset\s*#?\s*(\d+)\b',normalized) or re.search(r'\b(\d+)\s*(?:(?:tank\s*m4|m4\s*tank|tank|sled\s*push)\s*)?set\b',normalized)
            if not number:raise ValueError('Specify a set number, range, first/last N sets, or all matching sets')
            ordinal=int(number[1])
            if not 1<=ordinal<=len(candidates):raise ValueError('That set reference does not exist in this workout')
            indices=[candidates[ordinal-1]]
        efforts=list(re.finditer(r'\b(?:(planned|reported)\s+)?(?:RPE|effort)\s*(?::|was|is|of)?\s*(?:a\s+)?(\d+(?:\.\d+)?)\b',normalized,re.I))
        labels=[(e[1] or 'reported').lower() for e in efforts]
        if len(labels)!=len(set(labels)):raise ValueError('Give only one planned effort and one reported effort per correction line')
        move=re.search(r'\b(?:were|was|to|into|in|as)\s+(?:a\s+|the\s+)?(warm[ -]?up|main work|cool[ -]?down)\b',normalized)
        if not efforts and not move:raise ValueError('Correction must specify effort or a workout section')
        rest=normalized
        for alias in sorted(recognized,key=len,reverse=True):rest=rest.replace(alias,' ')
        for name in sorted({x['name'].lower() for x,_ in flat},key=len,reverse=True):rest=rest.replace(name,' ')
        rest=re.sub(r'\b(?:warm[ -]?up|main work|cool[ -]?down|planned|reported|rpe|effort|level|set|sets|tank|m4|sled|push|pushes|yo|that|this|the|a|was|were|is|to|into|in|as|on|of|move|all|last|through)\b|\d+', ' ',rest)
        if re.search(r'[a-z]',rest):raise ValueError('Unrecognized correction wording; specify the exercise, set number and planned/reported effort or section')
        # Reject unsupported actions, including dose changes hidden in prose.
        if re.search(r'\b(?:delete|remove|reps?|weight|pounds?|seconds?|minutes?|add)\b',normalized):raise ValueError('Use the full dose text to change exercises, weight, repetitions or duration')
        for i in indices:
            row,m=flat[i]
            for e in efforts:
                value=lifting.exercise_rpe(e[2]);label=(e[1] or 'reported').lower()
                if label=='planned':row['planned_effort']=[value]
                else:row['rpe']=value;row['set_details'][0]['rpe']=value
                changes.append({'set_order':i+1,'exercise':row['name'],'field':label+'_effort','value':value})
            if move:
                row['section']='warmup' if move[1].startswith('warm') else 'cooldown' if move[1].startswith('cool') else 'main'
                changes.append({'set_order':i+1,'exercise':row['name'],'field':'section','value':row['section']})
    if not changes:raise ValueError('No supported correction found')
    # Keep one row per actual set; explicit metadata prevents losing movement
    # classifications when a section move splits a formerly grouped exercise.
    fields=recorded_fields({'lifts':[x for x,_ in flat]},[m for _,m in flat])
    ordered=[(x,m) for section in ('warmup','main','cooldown') for x,m in flat if x.get('section','main')==section]
    metas=[]
    for x,m in ordered:
        m={**m,**{k:x[k] for k in ('style','regions','sled','how','equipment') if k in x}}
        m.pop('rpe',None);m['per_set_rpe']=[x.get('rpe')];m['planned_effort']=x['planned_effort']
        if m.get('sled',{}).get('distance_per_trip_m'):m['sled']['distance_m']=m['sled']['distance_per_trip_m']
        metas.append(m)
    return {'fields':fields,'exercise_metadata':metas,'changes':changes}

def source_log(d, ident):
    logs=d.get('lifting',{}).get('logs',[])
    log=next((x for x in logs if str(x.get('source_activity_id'))==str(ident)),None)
    m=re.fullmatch(r'lift-(\d{4}-\d{2}-\d{2})-(\d+)',str(ident))
    if not log and m:
        # A session logged in the Hub without a watch file: loads.py names it lift-<date>-<position in the log list>.
        i=int(m.group(2))
        if i<len(logs) and logs[i].get('date')==m.group(1):log=logs[i]
        else:log=next((x for x in logs if x.get('date')==m.group(1) and not x.get('source_activity_id')),None)
    if not log:return None
    log=copy.deepcopy(log)
    meta=d.get('activity_workouts',{}).get(str(ident),{}).get('exercise_metadata',[])
    for i,x in enumerate(log.get('lifts',[])):
        if i<len(meta):
            for k in ('kind','equipment','block','how'):
                if k in meta[i] and k not in x:x[k]=copy.deepcopy(meta[i][k])
    return log

def sled_power(sled, seconds):
    distance=sled.get('distance_per_trip_m') or sled.get('distance_per_leg_m')
    if distance is None and sled.get('distance_m') is not None:
        # Stored distance_m is total session travel. Only divide by an explicit
        # trip count; otherwise the per-effort distance remains unknown.
        trips=sled.get('trips')
        if trips:distance=sled['distance_m']/trips
    seconds=seconds or sled.get('seconds_high')
    if not distance or not seconds:return {'unknown':['Distance and duration per effort are needed']}
    if 'm4' not in str(sled.get('model','')).lower() or sled.get('front_level') not in strength_workouts.M4 or sled.get('rear_level') not in strength_workouts.M4:
        return {'unknown':['An M4 model and both magnetic settings are needed']}
    chart=strength_workouts.sled_preview({'distance_per_leg_m':distance,'seconds_low':seconds,
        'seconds_high':seconds,'front_level':sled.get('front_level'),'rear_level':sled.get('rear_level')})
    equivalent=chart['equivalent_weight_lb_low']
    result={**chart,'model_version':MODEL_VERSION,'reference_friction':[.30,.60],
        'speed_m_s':distance/seconds,'distance_m':distance,'seconds':seconds,
        'power_basis':'Conditional reference sled comparison: manufacturer equivalent mass × assumed friction 0.30–0.60 × gravity × average speed. Not measured M4 handle force or metabolic power. Turnarounds and varying speed are not resolved.'}
    if equivalent is not None:
        force=[equivalent*4.4482216152605*mu for mu in (.30,.60)]
        result.update(force_n_low=round(force[0],2),force_n_high=round(force[1],2),
            power_w_low=round(force[0]*distance/seconds,2),power_w_high=round(force[1]*distance/seconds,2))
    return result

def profile(d, ident, records=None):
    log=source_log(d,ident);detail=copy.deepcopy(d.get('activity_workouts',{}).get(str(ident),{}))
    fields=detail.get('fields') or {'main':detail.get('text','')}
    detail['editable_fields']=recorded_fields(log,detail.get('exercise_metadata')) if log else {k:strength_workouts.effort_slots(fields.get(k,''),k) for k in ('warmup','main','cooldown')}
    if not log:return {'name':detail.get('name','Recorded gym'),'details':detail,'log':None,'sets':[], 'hr':hr_trace(records or [])}
    rows=[]
    metadata=detail.get('exercise_metadata',[])
    for i,x in enumerate(log.get('lifts',[])):
        if x.get('done') is False:continue
        dose=lifting.dose_metrics([x])['exercises'][0]
        for j,ds in enumerate(dose['sets']):
            sd=(x.get('set_details') or [x]*len(dose['sets']))[j]
            row={'exercise':x['name'],'exercise_index':i,'set':j+1,'order':len(rows)+1,
                'section':x.get('section','main'),'planned_effort':(x.get('planned_effort') or (metadata[i].get('planned_effort') if i<len(metadata) else None) or [None]*len(dose['sets']))[j],
                'reported_rpe':sd.get('rpe'),'effort_note':metadata[i].get('note','') if i<len(metadata) else '',
                'volume_lb':ds['external_volume']*(2.20462262185 if ds.get('unit')=='kg' else 1) if ds['external_volume'] is not None else None,
                'active_seconds':ds['active_seconds'],'time_estimated':ds['time_estimated'],
                'weight':ds['weight'],'unit':ds['unit'],'reps':ds['reps'],'tempo':ds['tempo'],
                'power_w_low':None,'power_w_high':None}
            sled=x.get('sled') or (metadata[i].get('sled') if i<len(metadata) else None)
            if sled:
                scenario=sled_power(sled,sd.get('seconds'));row['scenario']=scenario
                row['power_w_low']=scenario.get('power_w_low');row['power_w_high']=scenario.get('power_w_high')
                row['basis']='Conditional TANK reference range'
            elif row['volume_lb'] is not None and ds['active_seconds']>0:
                energy=row['volume_lb']*.45359237*9.80665*.5
                power=round(energy/ds['active_seconds'],2)
                row.update(nominal_work_j=round(energy,2),power_w_low=power,power_w_high=power,
                    basis='Nominal external work: recorded mass × gravity × assumed 0.5 m per rep ÷ active set time. Tempo times are athlete-reported; otherwise 4 seconds per rep is assumed. Holds add time, not nominal travel.')
            else:row['basis']='Output unavailable: load or displacement is not recorded'
            rows.append(row)
    return {'name':log['session'],'details':detail,'log':{k:copy.deepcopy(v) for k,v in log.items() if k!='inputs'},
        'sets':rows,'hr':hr_trace(records or []),'model_version':MODEL_VERSION,
        'axes':'Output is by recorded set order, not synchronized to watch time. Heart rate is by elapsed recording time. No set timestamps inferred from HR.',
        'library_id':detail.get('library_id')}

def hr_trace(records):
    origin=min((r['t'] for r in records if isinstance(r.get('t'),(float,int))),default=0)
    bins={}
    for r in records:
        t=r.get('t');h=r.get('hr')
        if isinstance(t,(int,float)) and isinstance(h,(int,float)) and math.isfinite(t) and math.isfinite(h) and 30<=h<=230:
            bins.setdefault(int((t-origin)//10),[]).append(h)
    points=[{'seconds':b*10,'bpm':round(sum(v)/len(v),1)} for b,v in sorted(bins.items())]
    stride=max(1,math.ceil(len(points)/450))
    return {'points':points[::stride], 'basis':'Watch heart rate, 10-second means. Gaps stay gaps; no exercise-to-heart-rate matching.'}
