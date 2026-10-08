"""Versioned running response: shared decay parameters, fast report anchoring.

Observed soreness, modeled exposure and timing uncertainty stay separate.
No fitted tolerance band, injury probability or automatic clearance date.
Only the normal reviewed API apply path activates or refits the model.
"""
import copy,datetime as dt,json,math,time,zlib
from pathlib import Path
import response_model as core
MODEL='report-anchored-decay-v1'


def workload_context(load,today):
    """Recorded work rate AND sport mix, kept in separate compatible domains.

    Closed calendar windows avoid treating a just-started day as a full day.
    Missing exposure days make a rate unknown; they are not zero work.
    This records inputs for later response analysis, not a new readiness gate.
    """
    end=dt.date.fromisoformat(today)-dt.timedelta(days=1)
    days={r['date']:r for r in load.get('days',[])}
    windows=[]
    for n in (1,3,7):
        start=end-dt.timedelta(days=n-1)
        dates=[(start+dt.timedelta(days=i)).isoformat() for i in range(n)]
        observed=[days[x] for x in dates if x in days]
        coverage_complete=len(observed)==n;domains={}
        for domain in ('engine','impact','muscle'):
            sports={};complete=coverage_complete
            for row in observed:
                for sport,dose in row.get('sports',{}).items():
                    value=dose.get(domain,0)
                    if value is None:complete=False;continue
                    sports[sport]=sports.get(sport,0)+core.nonnegative(value)
            total=sum(sports.values())
            domains[domain]={'known_total':round(total,3),
                'complete':complete,
                'points_per_day':round(total/n,3) if complete else None,
                'sport_share_percent':{k:round(100*v/total,2) for k,v in sports.items() if v>0} if total else {},
                'unit':'modeled '+domain+' exposure points per calendar day'}
        windows.append({'start':start.isoformat(),'end':end.isoformat(),'days':n,
                        'covered_days':len(observed),'complete':all(x['complete'] for x in domains.values()),'domains':domains})
    return {'windows':windows,'current_day_in_progress':days.get(today),
        'meaning':'Work rate and sport mix are paired inputs. Cardio, impact and muscle exposure remain separate; no common physical unit or capacity threshold is implied.'}


def evidence(d,load,today):
    import journal
    return {**load,'checkins':{date:journal.effective(c) for date,c in d.get('checkins',{}).items() if date<=today},
            'source':'Hub recorded exposures and explicit check-ins'}


def state(d,load,today,profile=None):
    profile=profile or (d.get('running_response_model') or {}).get('profile')
    if not profile or profile.get('model')!=MODEL:return None
    data=core.prepare(evidence(d,load,today),today)
    fitted=profile['legs'];tau=fitted['params']['tau'];b=fitted['b'];a=fitted['a'];rho=math.exp(-1/tau)
    rows={r['day']:r for r in data['reports']}
    low=high=b;history=[];latest={};latest_run=None
    for i in range(data['length']):
        date=(data['start']+dt.timedelta(days=i)).isoformat()
        if i:low=b+(low-b)*rho;high=b+(high-b)*rho
        predicted=core.clip((low+high)/2)
        report=rows.get(i,{})
        for key in ('legs','feet'):
            if key in report:latest[key]={'date':date,'rating':report[key]}
        if 'legs' in report:low=high=report['legs']
        dose=data['dose']['impact'][i]+data['walk'][i]
        if data['dose']['impact'][i]>0:latest_run=date
        # Date-only reports cannot tell whether same-day work preceded them.
        # These endpoints represent order ambiguity, not a confidence interval.
        if 'legs' in report and dose>0:high+=a*dose
        else:low+=a*dose;high+=a*dose
        low=core.clip(low);high=core.clip(high)
        history.append({'date':date,'predicted_before_report':round(predicted,3),
            'legs_report':report.get('legs'),'feet_report':report.get('feet'),
            'estimate_low':round(low,3),'estimate_high':round(high,3),'exposure':round(dose,3)})
    observed=latest.get('legs');feet=latest.get('feet');projection=[]
    for i in range(1,15):
        low=b+(low-b)*rho;high=b+(high-b)*rho
        projection.append({'date':(dt.date.fromisoformat(today)+dt.timedelta(days=i)).isoformat(),
                           'estimate_low':round(core.clip(low),3),'estimate_high':round(core.clip(high),3)})
    row=history[-1]
    result={'active':True,'model':MODEL,'as_of':today,'window_days':90,'parameters':copy.deepcopy(fitted),
        'legs':observed,'feet':feet,'estimate':{'low':row['estimate_low'],'high':row['estimate_high'],
            'unit':'reported-response scale (1–10)','meaning':'Estimated leg response; range reflects unknown report/workout ordering, not a probability interval'},
        'recorded_exposure':row['exposure'],'last_run_date':latest_run,'history':history,'projection':projection,
        'personal_band':None,'clearance_date':None,'validation':'provisional; retrospective selection, prospective accuracy not established',
        'note':'Feet/bones response stays with running; leg work is shared with cycling, lifting and kicking. Shared-dose coefficients remain provisional. Missing reports are unknown.',
        'parameter_updated_on':profile.get('updated_on'),
        'feedback':copy.deepcopy(d.get('running_response_feedback',[])[-10:]),
        'workload_context':workload_context(load,today)}
    import program_drafts
    result['context_token']=program_drafts.digest({k:result[k] for k in ('model','as_of','parameters','history','workload_context')})
    return result


def record_feedback(d,load,today,fields):
    """Retain subjective corrections as evidence, without manufacturing a score delta."""
    current=state(d,load,today)
    if not current:raise ValueError('Activate and read the running response estimate first')
    if fields.get('context_token')!=current['context_token']:
        raise ValueError('The estimate changed. Refresh it before answering')
    direction=fields.get('direction')
    if direction not in ('matches','too_high','too_low','unsure'):
        raise ValueError('Choose matches, too_high, too_low or unsure')
    note=fields.get('note','')
    if not isinstance(note,str) or len(note)>1000:raise ValueError('Use a note of at most 1000 characters')
    entry={'date':today,'saved_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'direction':direction,'note':note,'context_token':current['context_token'],
        'estimate':current['estimate'],'parameters':current['parameters'],
        'legs':current['legs'],'feet':current['feet'],
        'workload_context':current['workload_context']}
    records=d.setdefault('running_response_feedback',[])
    if records and all(records[-1].get(k)==entry[k] for k in ('context_token','direction','note')):
        return records[-1]
    records.append(entry)
    return entry


def progression_input(load):
    response=load.get('running_response')
    if response and response.get('active'):
        return {'response_model':True,'last_run_date':response.get('last_run_date'),'response':response}
    return (((load.get('systems') or {}).get('impact') or {}).get('tissue') or {}).get('remodeling') or {}


def review(d,load,base,today):
    fit_evidence=evidence(d,load,today)
    # A same-day run report remains a current observation, never silently
    # becomes a delayed-recovery outcome just because the calendar advances.
    run_dates={r['date'] for r in load.get('days',[]) if r.get('sports',{}).get('run',{}).get('impact',0)>0}
    fit_evidence['checkins']={date:c for date,c in fit_evidence['checkins'].items() if date not in run_dates}
    try:p=core.hybrid_preview(fit_evidence,today)
    except ValueError as e:return {'status':'more_evidence_needed','reason':str(e),'active':state(d,load,today),'candidate':None}
    fitted=p['fits']['legs']
    if not fitted.get('identifiable_decay'):return {'status':'more_evidence_needed','reason':'No identifiable decay in the current report window','candidate':None}
    profile={'model':MODEL,'legs':fitted,'feet_method':'latest_report','updated_on':today,
             'sensitivity':p['decay_sensitivity'],'report_days_used':p['evidence']['report_days_used']}
    return {'status':'review_candidate','as_of':today,'current':copy.deepcopy((d.get('running_response_model') or {}).get('profile')),
        'candidate':profile,'preview':state(d,load,today,profile),'validation':p['unresolved'],
        'subjective_feedback':copy.deepcopy(d.get('running_response_feedback',[])[-10:]),
        'notice':'Activates the selected advisory response model. Retires block countdowns, not symptom reports or protected return-to-running checks. No personal band or clearance date.'}


def revision(d,load,base,today):
    import program_drafts
    return program_drafts.digest({'context':program_drafts.revision(d,base,{},[],today),
        'days':load.get('days'),'code':Path(__file__).read_text(),'core':Path(core.__file__).read_text()})


def preview(d,load,base,today):
    import program_drafts
    r=review(d,load,base,today)
    if r['status']!='review_candidate':return r
    return program_drafts.store(base,{'kind':'running_response_model','review':r},revision(d,load,base,today))


def apply(d,load,base,today,token,approved):
    import coach,program_drafts
    if approved is not True:raise ValueError('Approval of the selected model preview is required')
    if not isinstance(token,str) or not token:raise ValueError('Preview the model first')
    db=program_drafts.connect(base)
    try:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT revision,expires,payload FROM drafts WHERE id=?',(token,)).fetchone()
        if not row:raise program_drafts.Conflict('Response draft unavailable; preview again')
        payload=json.loads(zlib.decompress(row[2]))
        if payload.get('kind')!='running_response_model':raise ValueError('Choose a running response draft')
        saved=d.get('running_response_model') or {}
        prior=next((r for r in saved.get('history',[]) if r['draft_id']==token),None)
        if prior:return {**prior,'already_applied':True}
        if time.time()>row[1] or row[0]!=revision(d,load,base,today):raise program_drafts.Conflict('Evidence or model changed; preview again')
        r=payload['review'];entry={'draft_id':token,'date':today,'before':r['current'],'after':r['candidate'],
            'validation':r['validation']}
        saved=d.setdefault('running_response_model',{})
        saved['profile']=copy.deepcopy(r['candidate']);saved.setdefault('history',[]).append(entry)
        coach.save(d);db.commit();return entry
    finally:db.close()
