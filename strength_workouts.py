"""Deterministic strength transcription and bounded equipment/HR evidence.
No capacity references or recovery gates are changed here.
"""
import re, math, statistics
import lifting

HEAD = re.compile(r'\b(warm[ -]?up|main (?:work(?:out)?|set)|cool[ -]?down)\b\s*:?',re.I)
ITEM = re.compile(r'\b(\d+)\s*(?:x|×|sets?\s*(?:of)?)\s*(\d+)\s*(?:reps?)?(?:\s*(?:per|each)\s+side)?(?:\s*(?:at|@|with)\s*(\d+(?:\.\d+)?)\s*(lb(?:s)?|pounds?|kg))?(?:\s*(?:tempo\s*)?(\d+-\d+-\d+(?:-\d+)?))?|\b(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?)\b',re.I)
ALIASES={
 'touch your toes':('Supported toe-reach stretch','Use support and reach only as far as comfortable; do not force the stretch.'),
 'quad stretch':('Supported standing quad stretch','Hold a stable support; gently bend one knee if comfortable. Choose another position if balance or knee comfort limits you.'),
 'easy mobility':('Easy mobility','Move through a comfortable range without forcing it.')}

def parse(text, section='main'):
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

def preview(d,req):
    fields=req.get('fields') or {'main':req.get('text','')};repeat=req.get('repeats',1)
    if not isinstance(fields,dict) or isinstance(repeat,bool) or int(repeat)!=repeat or not 1<=repeat<=10:raise ValueError('Give section fields and an integer repeat count 1–10')
    out={'lifts':[],'steps':[],'unresolved':[],'substitutions':[]}
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
                out['lifts'].append(x)
            for key in ('unresolved','substitutions'):out[key].extend(parsed[key])
            out['steps'].extend(section+': '+line.strip() for line in re.split(r'\n|;',part) if line.strip())
    if len(out['lifts'])>30 or len(out['steps'])>30:out['unresolved'].append('Maximum 30 exercises or outline lines per session')
    if out['lifts'] and not out['unresolved']:out['lifts']=lifting.clean(d,out['lifts'],draft=True)
    out['valid']=bool(out['lifts']) and not out['unresolved']
    out['dose']=lifting.dose_metrics(out['lifts'])
    out['evaluation']=lifting.evaluate(d,out['lifts']) if out['valid'] else None
    return out

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
        details=[{k:r.get(k) for k in ('weight','reps','seconds','tempo','hold')} for r in matches for _ in range(r['sets'])]
        for detail in details:detail['hold']=detail['hold'] or 0
        done.append({'set_details':details})
    if remaining:raise ValueError('Text names an exercise outside this session: '+remaining[0]['name'])
    return done

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
