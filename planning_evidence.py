"""Bounded, read-only calendar and model evidence using the app's calculators."""
import datetime as dt
import hashlib
import json
from pathlib import Path

MODELS = {
 'cardio_fatigue': ('engine','loads.py','F_next = F_previous × exp(-1/7) + daily_dose × (1-exp(-1/7))', 'Daily weighted training load, not measured exhaustion.'),
 'cardio_conditioning': ('engine','loads.py','C_next = C_previous × exp(-1/42) + daily_dose × (1-exp(-1/42))','A weighted load history, not a direct measurement of improved performance.'),
 'impact_fatigue': ('impact','loads.py','acute_next = acute_previous × (1-2/8) + impact_dose × 2/8','Impact dose uses body-weight/speed/step proxies; it does not measure tissue damage.'),
 'muscle_fatigue': ('muscle','loads.py','acute_next = acute_previous × (1-2/8) + muscle_dose × 2/8','Shared leg demand proxy; different sports contribute without making shoulder and leg load identical.'),
 'run_mechanical': ('impact','damage.py','new_blocks = (run_impact / block_reference) × overlap_multiplier(existing_blocks); plateau → decline → tail','Custom recovery assumptions and reported responses; no validated injury-clearance time.'),
 'run_recent': ('impact','damage.py','sum(raw_run_blocks × age_kernel); age_kernel = (0.6, 1, 0.85, 0.6, 0.3)','Separate short response, not the accumulated recovery curve.'),
 'swim_recovery': ('swim','swimload.py','pull exposure / fitted reference; fast decay + 0.10 history contribution; overlap on new work','Stroke/pace/effort/equipment estimates and a personal fitted reference; not measured shoulder force.'),
 'strength': ('lifting','lifting.py','max(regional_blocks); each region receives allocated relative-intensity points / its reference','Highest regional lifting load; allocations and recovery rates are provisional.'),
 'mechanical': ('shared','loads.py','max(impact/limit, leg/limit, running_blocks/block_limit, swim_blocks/block_limit, lifting_blocks/block_limit)','A maximum of different normalized readings, not their mean or sum; missing inputs can make the forecast unavailable.'),
}

def dates(start,days,today):
    if isinstance(days,bool) or not 1<=days<=14:raise ValueError('Request 1–14 calendar days')
    first=dt.date.fromisoformat(start);now=dt.date.fromisoformat(today)
    if abs((first-now).days)>366 or (first+dt.timedelta(days=days)-now).days>367:raise ValueError('Choose a window within one year of today')
    return [(first+dt.timedelta(days=i)).isoformat() for i in range(days)]

def sid(date,index,session):
    h=hashlib.sha256(json.dumps(session,sort_keys=True).encode()).hexdigest()[:12]
    return f'{date}:{index}:{h}'

def calendar(d,load,done,workouts,today,start,days=7):
    import training_block as B, progression
    window=dates(start,days,today)
    future=[x for x in window if x>=today]
    projections=B.projected_loads(d,today,future,load,done,workouts) if future else {}
    rows=[]
    gate=B.running_gate(d,load,d.get('checkins',{}).get(today))
    for date in window:
        sessions=B.sessions(d.get('plans',{}).get(date) or {})
        projection=projections.get(date)
        if projection:
            projection={k:projection.get(k) for k in ('date','sessions','alerts','confidence','goal_basis','assumptions')} | {'metrics':[{k:r.get(k) for k in ('key','unit','before','after','session_dose','dose_unit','goal','expected','over_limit','limit')} for r in projections[date]['metrics'] if not r['key'].startswith('lift_') or r.get('over_limit')]}
        import coach
        marked=coach.mark_missed(d,date,coach.attach_completions(d,date,[dict(s) for s in sessions],[dict(x) for x in done.get(date,[])]),today)
        rows.append({'date':date,'sessions':[{'id':sid(date,i,s),'index':i,'prescription':s,'missed':bool(marked[i].get('missed')),'missed_reason':marked[i].get('missed_reason'),'context':progression.context(d,date,s['sport'],s),'execution_hold':s['sport']=='run' and gate['status']!='open_for_review'} for i,s in enumerate(sessions)],
                     'completed':done.get(date,[]),'projection':projection,
                     'checkin':d.get('checkins',{}).get(date),'feedback':[x for x in d.get('training_feedback',{}).values() if x.get('date')==date]})
    return {'start':start,'days':days,'as_of':today,'calendar':rows,
            'running_gate':gate,'active_symptoms':progression.active_symptoms(d,today),'detail_hint':'Use explain_training_reading for formulas, regional lifting readings and calculation evidence. Calendar includes headline readings and any over-limit region.',
            'notice':'Saved prescriptions and imported/logged completions; future readings are scenarios, not promised outcomes. Past forecasts are not recreated from today’s state.'}

def explain(d,load,done,workouts,today,date,metric):
    import loads, damage, swimload, lifting, training_block as B, bodymap
    model=MODELS.get(metric)
    if metric.startswith('lift_') and metric[5:] in lifting.regions():
        model=('lifting','lifting.py','region_next = decayed_region + allocated_points / regional_reference','Regional lifting estimate; not direct tissue force.')
    if model is None:raise ValueError('Choose a metric from: '+', '.join(MODELS)+' or lift_<region>')
    dates(date,1,today)
    system,source,formula,meaning=model
    forecast=B.projected_loads(d,today,[date],load,done,workouts).get(date) if date>=today else None
    reading=next((r for r in (forecast or {}).get('metrics',[]) if r['key']==metric),None)
    systems=load.get('systems') or {}
    baseline=load.get('swim_recovery') if system=='swim' else load.get('lifting') if system=='lifting' else load.get('headline') if system=='shared' else systems.get(system)
    if metric=='run_mechanical':baseline=((systems.get('impact') or {}).get('tissue') or {}).get('remodeling')
    if metric=='run_recent':baseline=((systems.get('impact') or {}).get('tissue') or {}).get('event')
    activities=[a for a in load.get('activities',[]) if a.get('date','')<=min(date,today) and (system in ('engine','muscle','shared') or system=='impact' and a.get('sport') in ('run','walk') or system=='swim' and a.get('sport')=='swim' or system=='lifting' and a.get('sport')=='gym')]
    activities=sorted(activities,key=lambda a:(a.get('date',''),a.get('id','')))
    contributors=[{k:a.get(k) for k in ('id','date','sport','minutes','engine','impact','muscle','engine_from','swim_exposure','swim_kick')} for a in activities[-20:]]
    # Keep regional/component detail inspectable, but explicitly report truncation.
    baseline=json.loads(json.dumps(baseline or {}))
    trimmed={}
    for k,v in list(baseline.items()):
        if isinstance(v,list) and len(v)>20:trimmed[k]=len(v)-20;baseline[k]=v[-20:]
    profile={k:(load.get('profile') or {}).get(k) for k in ('weight_kg','ftp','hr_rest','hr_max','swim_css','calibration')}
    constants={'cardio_time_constants_days':loads.TAU['engine'],'impact_muscle_ewma_days':loads.ACWR_N,
               'run_event_kernel':damage.EVENT_KERNEL,'run_tail_days':damage.TAIL_DAYS,
               'swim_half_life_days':swimload.HALF_LIFE_DAYS,'swim_history_half_life_days':swimload.HISTORY_HALF_LIFE_DAYS,
               'swim_history_fraction':swimload.HISTORY_FRACTION,'swim_stroke_factors':swimload.STROKE_FACTOR,
               'fin_kick_prior':swimload.FIN_KICK_FACTOR,'lifting_default_reference':lifting.DEFAULT_REF}
    return {'metric':metric,'date':date,'as_of':today,'reading':reading,'current_baseline':baseline,
            'definition':meaning,'formula':formula,'constants':constants,'profile_inputs':profile,
            'recorded_contributors':contributors,'omitted_older_activities':max(0,len(activities)-20),'truncated_baseline_lists':trimmed,
            'planned_contributions':(forecast or {}).get('sessions',[]),'assumptions':(forecast or {}).get('assumptions'),
            'unknown':reading is None or reading.get('after') is None,'body_overlap':bodymap.from_state(load) if metric=='mechanical' else None,
            'historical_daily_reading':next((x for x in load.get('days',[]) if x.get('date')==date),None) if date<today else None,
            'source':{'file':source,'url':'https://github.com/JHarp199345/S-Bike-Training-Hub/blob/main/'+source,
                      'sha256':hashlib.sha256((Path(__file__).parent/source).read_bytes()).hexdigest()},
            'notice':'Formula describes the implemented model, not established biological truth. Current baseline is as of today, even when inspecting a past date. Recorded contributors are input doses, not decomposed shares of today’s score. Unknown is not zero.'}
