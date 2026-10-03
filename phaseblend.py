"""Phase priorities and automatic goal blending, distinct from measured load or time.

Maintenance evidence informs guidance, not validated four-sport percentages. Existing
recovery gates remain authoritative; priority never creates a dose or clears running.
"""
import copy
import datetime as dt
import math

SPORTS=('ride','swim','gym','run')
NAMES={'ride':'Cycling','swim':'Swimming','gym':'Strength / physique','run':'Running'}
PROFILES={'balanced':'Balanced development','ride':'Cycling emphasis','swim':'Swimming emphasis',
          'gym':'Strength / physique emphasis','run':'Running emphasis','recovery':'Recovery'}
MODES=('improve','maintain','pause')
KINDS=('base','build','recovery','taper')
SOURCES=[{'title':'Maintaining physical performance (2021)','url':'https://pubmed.ncbi.nlm.nih.gov/33629972/'},
         {'title':'Reduced-dose resistance maintenance (2011)','url':'https://pubmed.ncbi.nlm.nih.gov/21131862/'},
         {'title':'Concurrent strength and endurance (2022)','url':'https://pmc.ncbi.nlm.nih.gov/articles/PMC8891239/'}]

def date(value):
    return value if isinstance(value,dt.date) else dt.date.fromisoformat(value)


def save(d,fields,today):
    start=date(fields.get('start') or today)
    weeks=math.ceil(fields['days']/7) if isinstance(fields.get('days'),int) and not isinstance(fields.get('days'),bool) else fields.get('weeks',4)
    if isinstance(weeks,bool) or not isinstance(weeks,int) or not 1<=weeks<=53:raise ValueError('Phase length is 1–53 weeks')
    profile=fields.get('profile','balanced');kind=fields.get('kind','base')
    if profile not in PROFILES or kind not in KINDS:raise ValueError('Choose a recognized profile and phase type')
    modes=fields.get('modes')
    if modes is None:modes={s:'improve' if profile in ('balanced',s) else 'maintain' for s in SPORTS}
    if not isinstance(modes,dict) or set(modes)!=set(SPORTS) or any(m not in MODES for m in modes.values()):raise ValueError('Give improve, maintain or pause for each sport')
    weights=fields.get('weights') or {}
    if not isinstance(weights,dict) or any(s not in SPORTS for s in weights):raise ValueError('Unknown priority weight')
    for value in weights.values():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<value<=100:raise ValueError('Advanced weights are positive numbers, at most 100')
    days=fields.get('days',weeks*7)
    if isinstance(days,bool) or not isinstance(days,int) or not 1<=days<=366:raise ValueError('Phase length is 1–366 days')
    end=start+dt.timedelta(days=days)
    entry={'id':start.isoformat(),'start':start.isoformat(),'end':end.isoformat(),'weeks':round(days/7,2),'days':days,'profile':profile,'kind':kind,
           'modes':copy.deepcopy(modes),'weights':copy.deepcopy(weights),'label':str(fields.get('label') or PROFILES[profile])[:100]}
    if 'locked' in fields:entry['locked']=bool(fields['locked'])
    phases=d.get('phase_profiles',[])
    previous=next((p for p in phases if p['id']==entry['id']),{})
    if fields.get('color') and fields['color'] not in ('teal','blue','purple','orange','gold'):raise ValueError('Choose one of the five phase colors')
    if fields.get('stage') and fields['stage'] not in ('assessment','recovery','base','build','specific','taper'):raise ValueError('Choose a recognized training purpose')
    for key in ('purpose','color','art','stage'):
        if key in fields or key in previous:entry[key]=str(fields.get(key,previous.get(key,'')))[:300]
    for key in ('review_criteria','weekly_pattern'):
        value=fields.get(key,previous.get(key))
        if value is None:continue
        if key=='review_criteria':
            if not isinstance(value,list) or len(value)>8 or any(not isinstance(x,str) or len(x)>500 for x in value):raise ValueError('Use at most eight short phase review criteria')
        else:
            if not isinstance(value,list) or len(value)!=7:raise ValueError('Weekly placement has seven days, Monday through Sunday')
            for day_slots in value:
                slots=day_slots if isinstance(day_slots,list) else [day_slots]
                if not 1<=len(slots)<=3 or any(not isinstance(x,dict) or x.get('sport') not in (*SPORTS,'rest') or not isinstance(x.get('purpose'),str) or len(x['purpose'])>300 for x in slots):raise ValueError('Give up to three recognized sports and short purposes for each day')
        entry[key]=copy.deepcopy(value)
    placements=fields.get('date_placements',previous.get('date_placements'))
    if placements is not None:
        if not isinstance(placements,dict) or len(placements)>366:raise ValueError('Provide dated placements within the phase')
        for day,slots in placements.items():
            if not start<=date(day)<end:raise ValueError('Dated placement is outside its phase; review it after changing dates')
            if not isinstance(slots,list) or not 1<=len(slots)<=3 or any(not isinstance(x,dict) or x.get('sport') not in (*SPORTS,'rest') or not isinstance(x.get('purpose'),str) or len(x['purpose'])>300 for x in slots):raise ValueError('Give up to three sports and purposes per date')
        entry['date_placements']=copy.deepcopy(placements)
    for p in phases:
        if p['id']!=entry['id'] and start<date(p['end']) and end>date(p['start']):raise ValueError('Phase dates overlap; edit the existing phase or start after it ends')
    # Stable start-date identifier supports intentional edits without dropping other phases.
    d['phase_profiles']=sorted([p for p in phases if p['id']!=entry['id']]+[entry],key=lambda p:p['start'])
    return entry


def active(d,today):
    t=date(today).isoformat()
    return next((p for p in d.get('phase_profiles',[]) if p['start']<=t<p['end']),None)


def events(d,today):
    t=date(today);result=[]
    for e in d.get('events',[]):
        if e.get('kind') not in ('race','goal'):continue
        if date(e['date'])<t:continue
        sport={'bike':'ride','strength':'gym','lift':'gym'}.get(e.get('sport'),e.get('sport'))
        typ=(e.get('detail') or {}).get('type')
        if typ=='swim_meet':sport='swim'
        elif typ=='lift_meet':sport='gym'
        elif typ=='run_race':sport='run'
        involved=list(SPORTS[:2])+['run'] if sport=='tri' or typ=='triathlon' else [sport] if sport in SPORTS else []
        for s in involved:result.append({'sport':s,'name':e['name'],'date':e['date'],'days':(date(e['date'])-t).days})
    return sorted(result,key=lambda e:e['date'])


def resolve(d,today,readiness=None,headline=None):
    """Same resolver for settings, session planning, forecasts and progression."""
    p=active(d,today);result={'enabled':bool(p),'profile':p,'sports':{},'sources':SOURCES,
       'meaning':'Priority shares guide planning opportunities; they are not training-time shares, physiological load ratios or proven optimal percentages. Preserve meaningful maintenance stimuli and evaluate the complete program.'}
    if not p:return result
    evs=events(d,today);mech=(headline or {}).get('mechanical') or {};ready=readiness or {}
    for s in SPORTS:
        mode=p['modes'][s];role=mode;why=[];es=[e for e in evs if e['sport']==s]
        phase=p['kind'];weight=p['weights'].get(s,3 if p['profile']==s and mode=='improve' else 2 if mode=='improve' else 1)
        if mode=='pause':weight=0;why.append('Paused by phase preference; no automatic maintenance or progression')
        elif p['profile']=='recovery' or phase=='recovery':role='recover';weight=0;why.append('Recovery phase: consolidate; no automatic increase')
        elif es:
            if mode=='maintain':role='prepare';weight=max(weight,1.5)
            why.append('Keep event preparation present for '+es[0]['name']+' on '+es[0]['date'])
            if es[0]['days']<=14:phase='taper';why.append('Event is near: preserve freshness')
        if phase=='taper' and mode!='pause':role='recover';weight=0;why.append('Taper protects freshness; priority does not authorize extra work')
        if es and mode=='pause':why.append('Event preparation gap: paused sport has an upcoming goal')
        if mode=='maintain' and role=='maintain':why.append('Preserve established performance with a smaller meaningful dose; do not add volume merely because it feels easy')
        if mode=='improve' and role=='improve':why.append('Progress when completed work, delayed response and full-program forecasts permit')
        r=ready.get('running' if s=='run' else 'swimming' if s=='swim' else 'verdict')
        verdict=r.get('verdict') if isinstance(r,dict) else r
        if s=='gym':verdict=((ready.get('systems') or {}).get('engine') or {}).get('level')
        held=verdict=='rest'
        if s=='run':
            blocks=mech.get('remodeling_blocks');limit=mech.get('block_limit',1.5)
            held=held or blocks is not None and blocks>=limit
        if held:role='hold';weight=0;why.append('Existing readiness or mechanical restriction takes precedence')
        result['sports'][s]={'name':NAMES[s],'mode':mode,'role':role,'phase':phase,'weight':weight,
            'can_progress':role in ('improve','prepare') and phase in ('base','build') and verdict not in ('easy','rest'),
            'events':es,'why':why,'maintenance':maintenance(s)}
    total=sum(x['weight'] for x in result['sports'].values())
    for x in result['sports'].values():x['priority_share']=round(100*x['weight']/total,1) if total else 0
    result['blend_name']=' + '.join(NAMES[s] for s,x in result['sports'].items() if x['role'] in ('improve','prepare')) or 'Maintenance / recovery'
    return result


def maintenance(sport):
    if sport=='gym':return 'Retain meaningful relative resistance. Reduced weekly volume can maintain adaptations; calibrate working sets against actual strength and physique, age and training history.'
    if sport=='run':return 'Aerobic transfer does not guarantee maintained running skill or impact tolerance. A running hold remains a hold; no minimum exposure overrides it.'
    return 'General endurance maintenance studies support lower frequency or duration with intensity retained. Use established tolerated sessions and sport-specific performance checks; two sessions is a research starting point, not a guaranteed athlete minimum.'


def week(d,today,start,readiness=None,headline=None):
    import training_block as B
    first=date(start);counts={s:0 for s in SPORTS};minutes={s:0 for s in SPORTS}
    roles={s:[] for s in SPORTS};changes=[];last_id=None
    for j in range(7):
        day=(first+dt.timedelta(days=j)).isoformat();b=resolve(d,day,readiness,headline)
        ident=(b.get('profile') or {}).get('id')
        if j and ident!=last_id:changes.append(day)
        last_id=ident
        for s,r in b['sports'].items():
            if r['role'] not in roles[s]:roles[s].append(r['role'])
        for session in B.sessions(d.get('plans',{}).get(day) or {}):
            s=session['sport']
            if s in SPORTS:counts[s]+=1;minutes[s]+=session.get('minutes',0)
    total=sum(minutes.values());alerts=[]
    for s in SPORTS:
        if any(r in ('improve','prepare','maintain') for r in roles[s]) and not counts[s]:alerts.append(NAMES[s]+': no scheduled exposure for this phase role; review the plan')
        if 'pause' in roles[s] and counts[s]:alerts.append(NAMES[s]+': scheduled work remains despite a pause preference; review the plan')
        if 'hold' in roles[s] and counts[s]:alerts.append(NAMES[s]+': sessions are scheduled despite the current restriction; review before training')
    return {'start':first.isoformat(),'total_minutes':total,'sports':{s:{'name':NAMES[s],'sessions':counts[s],'minutes':minutes[s],
            'time_share':round(minutes[s]/total*100,1) if total else 0,'roles':roles[s]} for s in SPORTS},
            'phase_changes':changes,'alerts':alerts,'basis':'Saved workout time only. Strength sets, intensity and unlike load scores are not converted into equivalent minutes.'}


def view(d,today,readiness=None,headline=None):
    first=date(today)-dt.timedelta(days=date(today).weekday())
    return {'current':resolve(d,today,readiness,headline),'phases':d.get('phase_profiles',[]),'profiles':PROFILES,'sports':NAMES,'sources':SOURCES,
            'weeks':[week(d,today,first+dt.timedelta(weeks=i),readiness,headline) for i in range(4)]}
