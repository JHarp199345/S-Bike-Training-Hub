"""Deterministic strength transcription and bounded equipment/HR evidence.
No capacity references or recovery gates are changed here.
"""
import re, math, statistics
import lifting

HEAD = re.compile(r'(?:^|(?<=[;\n]))\s*(warm[ -]?up|main (?:work(?:out)?|set)|cool[ -]?down)\b\s*:?',re.I)
ITEM = re.compile(r'\b(\d+)\s*(?:x|×|sets?\s*(?:of)?)\s*(\d+)\s*(?:reps?)?(?:\s*(?:per|each)\s+side)?(?:\s*(?:at|@|with)\s*(\d+(?:\.\d+)?)\s*(lb(?:s)?|pounds?|kg))?(?:\s*(?:tempo\s*)?(\d+-\d+-\d+(?:-\d+)?))?|\b(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?)\b',re.I)
ALIASES={
 'touch your toes':('Supported toe-reach stretch','Use support and reach only as far as comfortable; do not force the stretch.'),
 'quad stretch':('Supported standing quad stretch','Hold a stable support; gently bend one knee if comfortable. Choose another position if balance or knee comfort limits you.'),
 'easy mobility':('Easy mobility','Move through a comfortable range without forcing it.')}

def _parse_dose(text, section='main'):
    lifts=[];unresolved=[];substitutions=[]
    if not isinstance(text,str) or len(text)>18000:raise ValueError('Workout text must be at most 18,000 characters')
    for part in HEAD.split(text.replace('\r',' ')):
        if HEAD.fullmatch(part):
            section='warmup' if part.lower().startswith('warm') else 'cooldown' if part.lower().startswith('cool') else 'main';continue
        start=0
        while True:
            m=ITEM.search(part,start)
            if not m:break
            name=part[start:m.start()].strip(' \n,;.*•-:')
            name=re.sub(r'^(?:and|then|this is the)\s+','',name,flags=re.I).strip()
            end=m.end()
            if not name:unresolved.append(m.group());start=end;continue
            alias=ALIASES.get(name.lower());how=''
            if alias:substitutions.append({'from':name,'to':alias[0]});name,how=alias
            sets=int(m[1] or 1);reps=int(m[2]) if m[2] else None
            seconds=float(m[6])*(60 if m[7].lower().startswith('min') else 1) if m[6] else None
            timed=re.match(r'\s*(seconds?|secs?|s)\b',part[end:],re.I) if m[1] else None
            if timed:seconds=reps;reps=None;end+=timed.end()
            side=bool(re.search(r'\b(?:per|each)\s+side\b',m.group(),re.I))
            extra=re.match(r'\s*(?:per|each)\s+side\b',part[end:],re.I)
            if extra:side=True;end+=extra.end()
            weight=float(m[3]) if m[3] else None;unit='kg' if (m[4] or '').lower()=='kg' else 'lb'
            extra=re.match(r'\s*(?:@|at|with)\s*(\d+(?:\.\d+)?)\s*(lb(?:s)?|pounds?|kg)\b',part[end:],re.I)
            if extra:weight=float(extra[1]);unit='kg' if extra[2].lower()=='kg' else 'lb';end+=extra.end()
            description=re.match(r'\s*(?:—|--)\s*([^;\n]*)',part[end:])
            if description:how=description[1].strip()[:300];end+=description.end()
            x={'name':name,'section':section,'sets':sets,'reps':reps,'seconds':int(seconds) if seconds else None,
               'weight':weight,'unit':unit,'tempo':m[5],'hold':None,'per_side':side,'how':how,'scored':False}
            if len(name)>80 or sets>20 or (reps and reps>100) or (seconds and seconds>600) or (weight and weight>1000):unresolved.append(part[start:end].strip())
            else:lifts.append(x)
            start=end
        tail=part[start:].strip(' \n,;:.')
        if tail:unresolved.append(tail)
    return {'lifts':lifts,'unresolved':unresolved,'substitutions':substitutions}

def parse(text, section='main'):
    """The same text grammar feeds athlete fields and MCP previews.

    Annotations are explicit observations, not inferred from exercise names or
    effort. Unknown notes still need a dash; unrecognized dose stays unresolved.
    """
    if not isinstance(text,str) or len(text)>18000:raise ValueError('Workout text must be at most 18,000 characters')
    out={'lifts':[],'unresolved':[],'substitutions':[]}
    for part in HEAD.split(text.replace('\r',' ')):
        if HEAD.fullmatch(part):
            section='warmup' if part.lower().startswith('warm') else 'cooldown' if part.lower().startswith('cool') else 'main';continue
        for line in re.split(r'[;\n]',part):
            if not line.strip(' ,:'):continue
            note_parts=re.split(r'\s*(?:—|--)\s*',line,maxsplit=1)
            line=note_parts[0];free_note=note_parts[1] if len(note_parts)>1 else None
            meta={};sled={};observations={};effort_note=''
            def effort(m):
                nonlocal effort_note
                label=(m[1] or '').lower();key='planned_effort' if label=='planned' else 'per_set_rpe'
                if key in observations:raise ValueError('Give one '+(label or 'reported')+' effort annotation per exercise line')
                values=[None if v.strip()=='?' else lifting.exercise_rpe(v.strip()) for v in m[2].split(',')]
                if m[3]:
                    b=lifting.exercise_rpe(m[3]);a=values[0]
                    if a is None or a>b:raise ValueError('Effort range is reversed')
                    values=[b]
                    if key=='per_set_rpe':effort_note=f'Athlete reported RPE {a}–{b}; upper endpoint {b} retained for provisional scoring. Output does not use effort.'
                observations[key]=values;return ''
            line=re.sub(r'\b(?:(planned|reported)\s+)?(?:RPE|effort)\s*:?\s*((?:\d+(?:\.\d+)?|\?)(?:\s*,\s*(?:\d+(?:\.\d+)?|\?))*)\s*(?:(?:–|-|to)\s*(\d+(?:\.\d+)?))?(?:\s*/\s*10)?',effort,line,flags=re.I)
            line=re.sub(r'\b(?:(?:planned|reported)\s+)?(?:RPE|effort)\s*:\s*(?=,|$|—|--)', '',line,flags=re.I)
            def distance(m):
                if 'distance_per_trip_m' in sled:raise ValueError('Give one distance per effort')
                sled['distance_per_trip_m']=float(m[1])*(.9144 if m[2].lower().startswith(('y','yard')) else 1);return ''
            line=re.sub(r'\b(\d+(?:\.\d+)?)\s*(yd|yards?|m|meters?|metres?)\s+(?:per|each)\s+(?:round[ -]?trip|trip|push|set)\b',distance,line,flags=re.I)
            def magnets(m):
                level=int(m[1])
                if not 0<=level<=3:raise ValueError('TANK magnet levels are 0–3')
                if sled.get('front_level',level)!=level or sled.get('rear_level',level)!=level:raise ValueError('Conflicting magnet settings')
                sled.update(front_level=level,rear_level=level);return ''
            line=re.sub(r'\bboth\s+magnets?\s*(?:at\s+)?(?:level\s*)?(\d+)\b',magnets,line,flags=re.I)
            line=re.sub(r',\s*(?=[,—]|$)','',line).strip(' ,:')
            if free_note is not None:line+=' — '+free_note
            parsed=_parse_dose(line,section)
            if not parsed['lifts'] and not parsed['unresolved'] and (sled or observations):
                if not out['lifts'] or out['lifts'][-1]['section']!=section:raise ValueError('Put annotations after their exercise dose')
                rows=[out['lifts'][-1]]
            else:rows=parsed['lifts']
            if (sled or observations) and len(rows)!=1:raise ValueError('Put one annotated exercise on each line')
            for x in rows:
                meta=dict(x.get('text_metadata',{}))
                for key,efforts in observations.items():
                    if len(efforts) not in (1,x['sets']):raise ValueError('Give one effort for all sets, or one per set')
                    meta[key]=efforts*x['sets'] if len(efforts)==1 else efforts
                if effort_note:meta['note']=effort_note
                if sled:
                    if not re.search(r'\b(?:tank\s*m4|m4\s*tank)\b',x['name'],re.I):raise ValueError('TANK distance/magnet annotations require a TANK M4 exercise')
                    combined={**meta.get('sled',{}),**sled,'model':'TANK M4'}
                    if combined.get('distance_per_trip_m'):combined['distance_m']=combined['distance_per_trip_m']*x['sets']
                    if x.get('seconds'):combined.update(seconds_low=x['seconds'],seconds_high=x['seconds'],duration_basis='Athlete-entered time per effort')
                    # Both magnets must be explicit before consulting the chart.
                    meta['sled']=lifting.sled_metadata(combined) if 'front_level' in combined and 'rear_level' in combined else combined
                    x['sled']=meta['sled'];x['equipment']='Torque TANK M4'
                if meta:x['text_metadata']=meta
            out['lifts'].extend(parsed['lifts'])
            for k in ('unresolved','substitutions'):out[k].extend(parsed[k])
    return out

def preview(d,req):
    fields=req.get('fields') or {'main':req.get('text','')};repeat=req.get('repeats',1)
    if not isinstance(fields,dict) or isinstance(repeat,bool) or int(repeat)!=repeat or not 1<=repeat<=10:raise ValueError('Give section fields and an integer repeat count 1–10')
    out={'lifts':[],'steps':[],'unresolved':[],'substitutions':[],'exercise_metadata':[]}
    for section in ('warmup','main','cooldown'):
        text=fields.get(section,'');block=''
        if not isinstance(text,str):raise ValueError('Each workout section must be text')
        for part in re.split(r'\b((?:interval|block|circuit)\s+\d+)\s*:?',text,flags=re.I):
            if re.fullmatch(r'(?:interval|block|circuit)\s+\d+',part,re.I):block=part;continue
            if not part.strip():continue
            parsed=parse(part,section);times=repeat if section=='main' else 1
            for x in parsed['lifts']:
                x['sets']*=times;x['block']=block;x['block_repeats']=times
                if x['sets']>20:out['unresolved'].append(x['name']+': repeated sets exceed 20');continue
                meta=x.pop('text_metadata',{})
                for k in ('per_set_rpe','planned_effort'):
                    if meta.get(k):meta[k]*=times
                if meta.get('sled',{}).get('distance_per_trip_m'):
                    meta['sled']['distance_m']=meta['sled']['distance_per_trip_m']*x['sets'];x['sled']=meta['sled']
                out['exercise_metadata'].append(meta)
                out['lifts'].append(x)
            for key in ('unresolved','substitutions'):out[key].extend(parsed[key])
            out['steps'].extend(section+': '+line.strip() for line in re.split(r'\n|;',part) if line.strip())
    if len(out['lifts'])>30 or len(out['steps'])>30:out['unresolved'].append('Maximum 30 exercises or outline lines per session')
    if out['lifts'] and not out['unresolved']:out['lifts']=lifting.clean(d,out['lifts'],draft=True)
    for x,m in zip(out['lifts'],out['exercise_metadata']):
        x['planned_effort']=m.get('planned_effort',m.get('per_set_rpe',[None]*x['sets']))
    out['editable_fields']={k:effort_slots(v,k) for k,v in fields.items() if k in ('warmup','main','cooldown')}
    out['valid']=bool(out['lifts']) and not out['unresolved']
    out['dose']=lifting.dose_metrics(out['lifts'])
    out['evaluation']=lifting.evaluate(d,out['lifts']) if out['valid'] else None
    return out

def effort_slots(text, section='main'):
    """Prepare editable text once, never rewrite text while the athlete types."""
    lines=[]
    for line in re.split(r'[;\n]',text):
        if line.strip() and not re.search(r'\b(?:RPE|effort)\s*[:\d]',line,re.I):
            try:p=_parse_dose(line,section)
            except ValueError:p={}
            if len(p.get('lifts',[]))==1 and not p.get('unresolved'):
                chunks=re.split(r'\s*(—|--)\s*',line,maxsplit=1)
                chunks[0]=chunks[0].rstrip()+', planned effort: , reported effort: '
                line=''.join(chunks)
        lines.append(line)
    return '\n'.join(lines)

def actuals(d,req,date):
    """Text corrections must identify every planned exercise, without replacing its prescription."""
    out=preview(d,req)
    if not out['valid']:raise ValueError('Clarify workout text: '+ '; '.join(out['unresolved']))
    gyms=[s for s in d.get('plans',{}).get(date,{}).get('sessions',[]) if s.get('sport')=='gym' and s.get('lifts')]
    index=req.get('session_index',0)
    if not 0<=index<len(gyms):raise ValueError('Choose a saved gym session')
    remaining=list(out['lifts']);done=[]
    for x in gyms[index]['lifts']:
        matches=[r for r in remaining if lifting.key(r['name'])==lifting.key(x['name'])]
        if not matches:raise ValueError('Text must include every recorded exercise; missing '+x['name'])
        for r in matches:remaining.remove(r)
        details=[]
        for r in matches:
            efforts=out['exercise_metadata'][out['lifts'].index(r)].get('per_set_rpe')
            for i in range(r['sets']):
                detail={k:r.get(k) for k in ('weight','reps','seconds','tempo','hold')}
                if efforts is not None:detail['rpe']=efforts[i]
                details.append(detail)
        for detail in details:detail['hold']=detail['hold'] or 0
        done.append({'set_details':details})
    if remaining:raise ValueError('Text names an exercise outside this session: '+remaining[0]['name'])
    return done

def completed(d, req, activity, ctx=None):
    """Parse an imported gym's actual exercise details, never create a prescription.

    Work on a copy so previews and rejected requests cannot mutate library/strength
    state. The caller persists only the returned lifting state and annotation.
    """
    import copy
    candidate=copy.deepcopy(d)
    ident=str(activity['id']);date=activity['date']
    prior=next((l for l in lifting.state(candidate)['logs'] if str(l.get('source_activity_id'))==ident),None)
    prior_before=copy.deepcopy(prior)
    previous=candidate.get('activity_workouts',{}).get(ident,{})
    edit_text=req.get('text') or '\n'.join(str(v) for v in (req.get('fields') or {}).values())
    changes=[]
    contains_dose=re.search(r'\d+\s*(?:x|×|sets\s*(?:of)?)\s*\d+|\d+\s*(?:seconds?|secs?|minutes?|mins?)\b',edit_text,re.I)
    if prior and edit_text.strip() and not contains_dose:
        import recorded_strength
        correction=recorded_strength.correct_text(recorded_strength.source_log(candidate,ident),previous.get('exercise_metadata',[]),edit_text)
        req={**req,'fields':correction['fields'],'exercise_metadata':correction['exercise_metadata']}
        changes=correction['changes']
    parsed=preview(candidate,req)
    if not parsed['valid']:
        raise ValueError('Clarify workout text: '+ '; '.join(parsed['unresolved']))
    parsed['changes']=changes
    # Preserve classifications and athlete effort when correcting dose text. Match
    # by movement and occurrence, never transfer an old effort to a new movement.
    old_rows=list((prior or {}).get('lifts',[]));old_meta=previous.get('exercise_metadata',[])
    inherited=[]
    for x in parsed['lifts']:
        match=next((i for i,r in enumerate(old_rows) if r and lifting.key(r['name'])==lifting.key(x['name'])),None)
        m=copy.deepcopy(old_meta[match]) if match is not None and match<len(old_meta) else {}
        if match is not None:
            row=old_rows[match];old_rows[match]=None
            for k in ('kind','style','regions','equipment','how','sled'):
                if k in row and k not in m:m[k]=copy.deepcopy(row[k])
            efforts=[r.get('rpe') for r in row.get('set_details',[])]
            m.pop('rpe',None);m['per_set_rpe']=(efforts+[None]*x['sets'])[:x['sets']]
        inherited.append(m)
    metadata=req.get('exercise_metadata',inherited)
    if not isinstance(metadata,list) or len(metadata)!=len(parsed['lifts']):
        raise ValueError('Give one metadata entry per parsed exercise, in order')
    allowed={'kind','style','regions','equipment','how','sled','rpe','per_set_rpe','planned_effort','note'}
    # Text observations override inherited observations on an edit. Conflicting
    # explicit MCP metadata is rejected, so entry route cannot change the result.
    import copy
    metadata=copy.deepcopy(metadata)
    for i,text_meta in enumerate(parsed['exercise_metadata']):
        if not isinstance(metadata[i],dict):raise ValueError('Exercise metadata must be an object')
        if 'exercise_metadata' in req:
            for k,v in text_meta.items():
                if k=='sled':
                    for field,value in v.items():
                        old=metadata[i].get('sled',{}).get(field)
                        equal=math.isclose(old,value,rel_tol=1e-9) if isinstance(old,(int,float)) and isinstance(value,(int,float)) else old==value
                        if old is not None and not equal:raise ValueError('Text and metadata disagree about TANK '+field)
                elif k in ('per_set_rpe','planned_effort'):
                    declared=metadata[i].get(k,[metadata[i].get('rpe') if k=='per_set_rpe' else None]*parsed['lifts'][i]['sets'])
                    if not isinstance(declared,list):raise ValueError('Effort metadata must be one value per set')
                    if any(r is not None for r in declared) and declared!=v:raise ValueError('Text and metadata disagree about '+('reported' if k=='per_set_rpe' else 'planned')+' effort')
        metadata[i]={**metadata[i],**text_meta,**({'sled':{**metadata[i].get('sled',{}),**text_meta['sled']}} if 'sled' in text_meta else {})}
    lifts=[]; done=[]
    for x,m in zip(parsed['lifts'],metadata):
        if not isinstance(m,dict) or set(m)-allowed:
            raise ValueError('Exercise metadata describes classification/effort only; dose comes from parsed text')
        if x.get('how'):m['how']=x['how']
        if x.get('equipment') and not m.get('equipment'):m['equipment']=x['equipment']
        x={**x,**{k:v for k,v in m.items() if k not in ('per_set_rpe','note','planned_effort')}}
        efforts=m.get('per_set_rpe',[m.get('rpe')]*x['sets'])
        if not isinstance(efforts,list) or len(efforts)!=x['sets']:
            raise ValueError('Give one effort value per set, or omit unknown effort')
        details=[{**{k:x.get(k) for k in ('weight','reps','seconds','tempo')},
                  'hold':x.get('hold') or 0,'rpe':lifting.exercise_rpe(r)} for r in efforts]
        x['planned_effort']=m.get('planned_effort',[None]*x['sets'])
        lifts.append(x);done.append({'set_details':details})
    lifts=lifting.clean(candidate,lifts,draft=True)
    logs=lifting.state(candidate)['logs']
    name=str(req.get('name') or (prior or {}).get('session') or 'Recorded strength · '+ident).strip()
    if not name or len(name)>120:raise ValueError('Give a workout name of 1–120 characters')
    if any(l['date']==date and l['session']==name and str(l.get('source_activity_id'))!=ident for l in logs):
        raise ValueError('Choose a distinct session name; another completed session already uses it')
    def unchanged():
        if not prior or len(prior['lifts'])!=len(lifts):return False
        if req.get('rpe',prior.get('rpe'))!=prior.get('rpe') or req.get('wellness',prior.get('wellness'))!=prior.get('wellness'):return False
        keys=('weight','reps','seconds','tempo','hold','rpe')
        for i,(old,new,actual) in enumerate(zip(prior['lifts'],lifts,done)):
            old_sets=old.get('set_details') or [old]*old['sets']
            if len(old_sets)!=len(actual['set_details']):return False
            for a,b in zip(old_sets,actual['set_details']):
                if any((a.get(k) or (0 if k=='hold' else None))!=(b.get(k) or (0 if k=='hold' else None)) for k in keys):return False
            for k in ('name','style','regions','per_side','unit'):
                if old.get(k)!=new.get(k):return False
            if i<len(old_meta) and old_meta[i].get('kind')!=new.get('kind'):return False
        return True
    if unchanged():
        # Presentation-only corrections must not rescore a past performance
        # against the strength anchors that performance itself updated.
        entry=prior;entry['session']=name
        for row,x in zip(entry['lifts'],lifts):
            row.update(section=x['section'],how=x['how'],equipment=x['equipment'],planned_effort=x['planned_effort'])
            for sd in row.get('set_details',[]):sd['section']=x['section']
    else:
        if prior:prior['session']=name
        entry=lifting.log(candidate,date,done,req.get('rpe',(prior or {}).get('rpe')),req.get('wellness',(prior or {}).get('wellness')),ctx=ctx,
                          source_activity_id=ident,_actual_session={'name':name,'sport':'gym',
                          'minutes':activity['minutes'],'lifts':lifts})
        for row,x in zip(entry['lifts'],lifts):row['planned_effort']=x['planned_effort']
        if prior:
            # A partial edit retains the historical calculation for every
            # unchanged set, including when moving sets splits exercise rows.
            old_sets={};seen={}
            signature_keys=('name','weight','unit','reps','seconds','tempo','hold','rpe','style','regions','per_side','kind')
            def signature(row):return tuple(str(row.get(k) or (0 if k=='hold' else None)) for k in signature_keys)
            for index,row in enumerate(prior['lifts']):
                for sd in row.get('set_details') or [row]*row['sets']:
                    key=lifting.key(row['name']);seen[key]=seen.get(key,0)+1
                    old_sets[(key,seen[key])]={**row,**sd,'kind':old_meta[index].get('kind') if index<len(old_meta) else None}
            seen={};kept=0
            for row,x in zip(entry['lifts'],lifts):
                details=row.get('set_details') or [row]
                for sd in details:
                    key=lifting.key(row['name']);seen[key]=seen.get(key,0)+1;old=old_sets.get((key,seen[key]))
                    if old and signature(old)==signature({**row,**sd,'kind':x.get('kind')}):
                        for k in ('points','why','method','intensity'):
                            if k in old:sd[k]=copy.deepcopy(old[k])
                        kept+=1
                row['points']=round(sum(sd['points'] for sd in details),1)
            if kept:
                reg={}
                for row in entry['lifts']:
                    for region,value in lifting.spread(row,row['points']).items():reg[region]=reg.get(region,0)+value
                entry['points_total']=round(sum(x['points'] for x in entry['lifts']),1)
                entry['regions']={r:round(v,1) for r,v in reg.items()}
                entry['leg_points']=round(sum(v for r,v in reg.items() if r in lifting.LEG_REGIONS),1)
                entry['restorative_share']=lifting.restorative_share(entry['lifts'],[x['points'] for x in entry['lifts']])
                if kept==len(old_sets)==sum(len(x.get('set_details') or [x]) for x in entry['lifts']):
                    for k in ('points_total','regions','leg_points','restorative_share'):entry[k]=copy.deepcopy(prior[k])
    parsed['lifts']=lifts;parsed['dose']=entry['dose'];parsed['evaluation']=lifting.evaluate(candidate,lifts)
    annotation={**previous,'name':name,'text':str(req.get('text') or ''),'fields':req.get('fields') or {},
                'note':str(req.get('note',previous.get('note','')))[:4000],
                'summary':str(req.get('summary',previous.get('summary','')))[:600],
                'source':'athlete-reported workout details', 'exercise_metadata':metadata,
                'load_basis':'One imported gym recording linked to its actual exercise log; no second session or prescription.',
                'dose':entry['dose']}
    candidate.setdefault('activity_workouts',{})[ident]=annotation
    import recorded_strength
    annotation['fields']=recorded_strength.recorded_fields(recorded_strength.source_log(candidate,ident),metadata)
    before=recorded_strength.saved_sets(prior_before)
    after=recorded_strength.saved_sets(entry)
    if before!=after or (previous.get('name') and previous['name']!=name):
        import datetime
        annotation['edit_history']=[*previous.get('edit_history',[]),{'at':datetime.datetime.now().isoformat(timespec='seconds'),
            'before':before,'after':after,'changes':changes,'name':name}]
    output=recorded_strength.profile(candidate,ident)
    return {'activity_id':ident,'date':date,'valid':True,'parsed':parsed,
            'log':{k:v for k,v in entry.items() if k!='inputs'},'details':annotation,'output':output},candidate['lifting']

# Transcribed manufacturer M4/MX table; units are FRICTION SLED WEIGHT EQUIVALENT, not lbf.
CHART_SOURCE='https://www.torquefitness.com/pages/tank-faq'
M4={0:[6,7,9,10,12,13,14,16,17,19,20,22,23,25,26,27,29,30,32,33,35],
1:[33,41,49,58,66,74,82,91,99,107,115,124,132,140,148,157,165,173,181,190,198],
2:[86,107,128,150,171,192,214,235,257,278,299,321,342,364,385,406,428,449,470,492,513],
3:[116,145,174,203,232,260,289,318,347,376,405,434,463,492,521,550,579,608,637,666,695]}

def sled_preview(req):
    distance=float(req['distance_per_leg_m']);lo=float(req['seconds_low']);hi=float(req['seconds_high'])
    front=req['front_level'];rear=req['rear_level']
    if not all(math.isfinite(v) and v>0 for v in (distance,lo,hi)) or lo>hi:raise ValueError('Give positive distance and ordered time bounds')
    if front not in M4 or rear not in M4:raise ValueError('Magnet levels are 0–3')
    low,high=distance/hi/0.44704,distance/lo/0.44704
    def equivalent(speed):
        if front!=rear or not 1<=speed<=6:return None
        q=(speed-1)/.25;i=min(19,int(q));return round(M4[front][i]+(M4[front][i+1]-M4[front][i])*(q-i),1)
    return {'model':'TANK M4','speed_mph_low':round(low,3),'speed_mph_high':round(high,3),
            'equivalent_weight_lb_low':equivalent(low),'equivalent_weight_lb_high':equivalent(high),
            'source':CHART_SOURCE,'chart_speed_mph':[1,6],
            'basis':'Approximate friction-sled weight equivalent from the manufacturer table, linearly interpolated within its range. Not pushing force or lifted poundage.',
            'unknown':(['Different front/rear settings are not specified by this chart'] if front!=rear else [])+(['Some speeds fall outside the chart; those estimates remain unknown'] if low<1 or high>6 else []),
            'scoring':'Use the Hub’s existing time-and-reported-effort model. This chart does not establish a conversion to tissue-load points.'}

def hr_windows(records):
    """Candidate cardiovascular response windows. No invented exercise identities or exact work times."""
    bins={};origin=min((r['t'] for r in records),default=0)
    for r in records:
        hr=r.get('hr')
        if hr and 30<=hr<=230:bins.setdefault(int((r['t']-origin)//10),[]).append(hr)
    data=[(i*10,statistics.median(v)) for i,v in sorted(bins.items()) if len(v)>=3]
    smooth=[(t,statistics.median([h for tt,h in data if abs(tt-t)<=10])) for t,_ in data]
    windows=[];start=None;peak=None;prev=None
    for t,hr in smooth:
        if prev and t-prev[0]>20:start=peak=None
        earlier=next((h for tt,h in reversed(smooth) if tt<=t-20),None)
        delta=hr-earlier if earlier is not None else 0
        if start is None and delta>=5:start=(max(0,t-20),earlier);peak=(t,hr)
        if start:
            if hr>peak[1]:peak=(t,hr)
            if delta<=-5 and t-start[0]>=30:
                if peak[1]-start[1]>=15:
                    windows.append({'response_start_s':start[0],'response_peak_s':peak[0],
                                    'response_fall_s':t,'response_duration_s':t-start[0],
                                    'start_hr':start[1],'peak_hr':peak[1],'rise_bpm':peak[1]-start[1],
                                    'classification':'candidate HR response; effort start/end not measured'})
                start=peak=None
        prev=(t,hr)
    if start and peak[1]-start[1]>=15:
        windows.append({'response_start_s':start[0],'response_peak_s':peak[0],'response_fall_s':None,
                        'response_duration_s':None,'start_hr':start[1],'peak_hr':peak[1],
                        'rise_bpm':peak[1]-start[1],'classification':'incomplete HR response'})
    return {'windows':windows[:20],'method':'10-second medians, smoothed over 30 seconds; rise ≥5 bpm/20 seconds, prominence ≥15 bpm, fall ≥5 bpm/20 seconds. These configurable heuristics identify HR responses, not mechanical work.',
            'timing_priority':['timed effort','athlete-estimated duration','candidate heart-rate response'],
            'limitations':'Heart-rate lag, rests, drift, sensor noise and overlapping exercises prevent precise effort timing or identification. No force estimate or automatic training-log change is made.'}
