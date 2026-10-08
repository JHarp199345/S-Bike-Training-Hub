"""Pure, preview-only model comparisons. No Hub imports, files, network or writes.

Predicted report ratings are an exploratory continuous approximation of an
ordinal scale. They do not measure tissue repair or establish a run clearance.
"""
import datetime as dt
import math
import statistics as st

MODELS=('training_mean','last_report','legacy_curve','single_decay','duration_decay',
        'distance_decay','two_component','nonlinear_dose','shared_legs',
        'recent_fit','report_update','report_anchor')

def finite(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def nonnegative(v):
    value=float(v)
    if not math.isfinite(value) or value<0:raise ValueError('Exposure must be finite and nonnegative')
    return value

def prepare(evidence, as_of):
    today=dt.date.fromisoformat(as_of)
    days=sorted((d for d in evidence['days'] if d['date']<=as_of),key=lambda d:d['date'])
    if not days:raise ValueError('No dated exposure history')
    start=dt.date.fromisoformat(days[0]['date'])
    length=(today-start).days+1
    day=lambda date:(dt.date.fromisoformat(date)-start).days
    dose={k:[0.]*length for k in ('impact','duration','distance','shared')}
    for d in days:
        i=day(d['date']);run=d.get('sports',{}).get('run',{})
        dose['impact'][i]=nonnegative(run.get('impact',0))/100
        dose['duration'][i]=nonnegative(run.get('minutes',0))/30
        dose['shared'][i]=sum(nonnegative(v.get('muscle',0)) for k,v in d.get('sports',{}).items() if k!='run')/100
    for a in evidence.get('activities',[]):
        if a.get('sport')=='run' and start.isoformat()<=a['date']<=as_of:
            dose['distance'][day(a['date'])]+=nonnegative(a.get('km',0))
    rem=evidence.get('systems',{}).get('impact',{}).get('tissue',{}).get('remodeling',{})
    legacy=[None]*length
    for r in rem.get('history',[]):
        if start.isoformat()<=r['date']<=as_of:legacy[day(r['date'])]=float(r['score'])
    # Freeze the known walking contribution to isolate running equation changes.
    # This inherits its input assumptions; a new walking dose is not identified here.
    walk=[0.]*length
    ref=float(rem.get('reference_points') or 100)
    for r in rem.get('walking',[]):
        if start.isoformat()<=r['date']<=as_of:walk[day(r['date'])]=nonnegative(r.get('added_blocks',0))*ref/100
    reports=[]
    for date,c in sorted(evidence.get('checkins',{}).items()):
        if max(start,today-dt.timedelta(days=89)).isoformat()<=date<=as_of:
            reports.append({'date':date,'day':day(date),**{k:float(c[k]) for k in ('legs','feet') if finite(c.get(k)) and 1<=c[k]<=10}})
    return {'start':start,'as_of':today,'length':length,'dose':dose,'walk':walk,
            'legacy':legacy,'reports':reports,'evidence':evidence}

def decay(dose,tau):
    out=[];x=0.;rho=math.exp(-1/tau)
    for v in dose:x=x*rho+v;out.append(x)
    return out

def curve(data,model,params,include_today=False):
    if model=='legacy_curve':return data['legacy']
    name='duration' if model=='duration_decay' else 'distance' if model=='distance_decay' else 'impact'
    raw=data['dose'][name]
    if model=='nonlinear_dose':raw=[v**params.get('beta',1) for v in raw]
    raw=[v+w for v,w in zip(raw,data['walk'])]
    tau=params.get('tau',7)
    if model=='two_component':
        fast=decay(raw,params['fast']);slow=decay(raw,params['slow']);f=params['fraction']
        if not include_today:
            fast=[0.]+[v*math.exp(-1/params['fast']) for v in fast[:-1]]
            slow=[0.]+[v*math.exp(-1/params['slow']) for v in slow[:-1]]
        return [f*a+(1-f)*b for a,b in zip(fast,slow)]
    out=decay(raw,tau)
    if model=='shared_legs':
        shared=decay(data['dose']['shared'],tau)
        out=[v+params['shared_weight']*s for v,s in zip(out,shared)]
    if not include_today:out=[0.]+[v*math.exp(-1/tau) for v in out[:-1]]
    return out

def mapping(series,rows,metric,weights):
    xx=[series[r['day']] for r in rows];yy=[r[metric] for r in rows]
    if any(v is None for v in xx):raise ValueError('Missing legacy history for report')
    total=sum(weights);xm=sum(w*x for w,x in zip(weights,xx))/total;ym=sum(w*y for w,y in zip(weights,yy))/total
    var=sum(w*(x-xm)**2 for w,x in zip(weights,xx));choices=[(max(1,ym),0.)]
    if var>1e-12:
        a=sum(w*(x-xm)*(y-ym) for w,x,y in zip(weights,xx,yy))/var;b=ym-a*xm
        if a>=0 and b>=1:choices.append((b,a))
    den=sum(w*x*x for w,x in zip(weights,xx))
    choices.append((1.,max(0,sum(w*x*(y-1) for w,x,y in zip(weights,xx,yy))/den) if den else 0.))
    loss=lambda ba:sum(w*(clip(ba[0]+ba[1]*x)-y)**2 for w,x,y in zip(weights,xx,yy))/total
    b,a=min(choices,key=loss)
    return b,a,loss((b,a))

def clip(v):return min(10.,max(1.,v))

def fit(data,model,rows,metric):
    rows=[r for r in rows if metric in r]
    if len(rows)<3:raise ValueError('At least three dated reports needed for exploratory fitting')
    if model=='training_mean':return {'model':model,'b':st.mean(r[metric] for r in rows),'a':0,'params':{},'mse':None}
    if model=='last_report':return {'model':model,'b':rows[-1][metric],'a':0,'params':{},'mse':None}
    taus=[.5+i*.5 for i in range(120)]
    if model=='legacy_curve':grid=[{}]
    elif model=='two_component':grid=[{'fast':f,'slow':s,'fraction':p} for f in (1,3,5,7) for s in (10,20,40,60) for p in (.25,.5,.75)]
    elif model=='nonlinear_dose':grid=[{'tau':t,'beta':b} for t in taus for b in (.75,1.,1.25)]
    elif model=='shared_legs':grid=[{'tau':t,'shared_weight':w} for t in taus for w in (0,.25,.5,1.)]
    else:grid=[{'tau':t} for t in taus]
    weights=[math.exp(-math.log(2)*(rows[-1]['day']-r['day'])/14) if model=='recent_fit' else 1 for r in rows]
    candidates=[]
    for params in grid:
        series=curve(data,model,params);b,a,mse=mapping(series,rows,metric,weights)
        candidates.append((mse,params,b,a))
    mse,params,b,a=min(candidates,key=lambda c:c[0])
    return {'model':model,'b':b,'a':a,'params':params,'mse':mse,
            'identifiable_decay':a>1e-8,'training_last_date':rows[-1]['date']}

def predictions(data,model,training,evaluation,metric,noise_fraction=.1):
    fitted=fit(data,model,training,metric)
    series=None if model in ('last_report','training_mean') else curve(data,model,fitted['params'])
    forecasts=[]
    if model in ('report_update','report_anchor'):
        tau=fitted['params']['tau'];rho=math.exp(-1/tau);b,a=fitted['b'],fitted['a']
        # Filtering predicts reports: correction can differ from physical dose.
        rating_noise=max(.25,fitted['mse']);variance=rating_noise;state=b
        training_days={r['day']:r for r in training if metric in r}
        target_days={r['day']:r for r in evaluation if metric in r}
        for i in range(max(target_days)+1):
            if i:state=b+(state-b)*rho;variance=rho*rho*variance+rating_noise*noise_fraction
            predicted=clip(state)
            if i in target_days:forecasts.append({'date':target_days[i]['date'],'predicted':predicted,'actual':target_days[i][metric]})
            observed=training_days.get(i) or target_days.get(i)
            if observed:
                gain=1. if model=='report_anchor' else variance/(variance+rating_noise)
                state=clip(state+gain*(observed[metric]-state));variance=(1-gain)*variance
            # Unverified same-day exposure occurs after this forecast/report.
            state+=a*(data['dose']['impact'][i]+data['walk'][i])
    else:
        prior=[r for r in training if metric in r]
        for r in evaluation:
            pred=prior[-1][metric] if model=='last_report' else fitted['b'] if model=='training_mean' else clip(fitted['b']+fitted['a']*series[r['day']])
            forecasts.append({'date':r['date'],'predicted':pred,'actual':r[metric]});prior.append(r)
    return {'fit':fitted,'forecasts':forecasts,'mae':st.mean(abs(v['predicted']-v['actual']) for v in forecasts)}

def compare(evidence,as_of):
    data=prepare(evidence,as_of)
    # Same-day ordering of workout and check-in is unverified: exclude today
    # from delayed-recovery error scores rather than leaking future-dose timing.
    rows=[r for r in data['reports'] if r['date']<as_of and all(k in r for k in ('legs','feet'))]
    if len(rows)<5:raise ValueError('Need at least five prior report dates for chronological comparison')
    results={}
    for model in MODELS:
        results[model]={}
        for metric in ('legs','feet'):
            hold=predictions(data,model,rows[:4],rows[4:],metric)
            rolling=[predictions(data,model,rows[:i],[rows[i]],metric) for i in range(3,len(rows))]
            hold['rolling_mae']=st.mean(v['mae'] for v in rolling)
            hold['rolling_forecasts']=[v['forecasts'][0] for v in rolling]
            results[model][metric]=hold
    return {'as_of':as_of,'source':evidence.get('source'),'prior_report_dates':[r['date'] for r in rows],
            'results':results,'limits':['One broad recovery episode; repeated reports are correlated.',
                                     'Chronological retrospective backtest, not prospective validation.',
                                     'Same-day October 6 report excluded from delayed-recovery scoring.',
                                     'Other report forecasts use prior-day exposure; same-day order unverified.',
                                     'Known walking dose frozen; later walking/standing incomplete.',
                                     'No personal band, clearance date or athlete change.']}

def preview(evidence,as_of,model='report_anchor'):
    if model not in MODELS:raise ValueError('Unknown candidate model')
    data=prepare(evidence,as_of)
    prior=[r for r in data['reports'] if r['date']<as_of and all(k in r for k in ('legs','feet'))]
    fits={m:fit(data,model,prior,m) for m in ('legs','feet')}
    return {'status':'experiment_preview','as_of':as_of,'model':model,'fits':fits,
            'personal_band':None,'clearance_date':None,'applied':False,
            'same_day_reports':[r for r in data['reports'] if r['date']==as_of],
            'meaning':'Exploratory reported-response model; measured workload is preserved. No clearance or scheduling decisions.',
            'evidence':{'activities':len(evidence.get('activities',[])),'report_days_used':len(prior),'primary_window_days':90}}


def hybrid_preview(evidence,as_of):
    """Best current evidence combination, explicitly an experiment, not clearance."""
    result=preview(evidence,as_of,'report_anchor')
    data=prepare(evidence,as_of)
    prior=[r for r in data['reports'] if r['date']<as_of and all(k in r for k in ('legs','feet'))]
    result['model']='hybrid_candidate_v1'
    result['fits']['feet']=fit(data,'last_report',prior,'feet')
    result['selection']={'legs':'report_anchor','feet':'last_report',
        'reason':'Leg anchor improves both chronological comparisons; feet last-report has best rolling error. Foot ranking changes with protocol.',
        'scope':'Selection is retrospective and provisional; future dated reports must test it.'}
    result['latest_observed']={}
    for metric in ('legs','feet'):
        rows=[r for r in data['reports'] if metric in r]
        result['latest_observed'][metric]={'date':rows[-1]['date'],'rating':rows[-1][metric]} if rows else None
    fitted=result['fits']['legs']
    # A descriptive error profile, deliberately not a probability interval.
    profiles=[]
    for t in (.5+i*.5 for i in range(120)):
        ss=curve(data,'single_decay',{'tau':t})
        _,_,loss=mapping(ss,prior,'legs',[1.]*len(prior))
        profiles.append({'tau_days':t,'training_mse':loss})
    best=min(v['training_mse'] for v in profiles)
    # Reporting a transparent sensitivity set in rating-error units avoids
    # presenting it as a clinically validated confidence interval.
    eligible=[v['tau_days'] for v in profiles if v['training_mse']<=best+.25]
    result['decay_sensitivity']={'minimum_mse':best,'mse_tolerance':.25,
        'tau_days_span':[min(eligible),max(eligible)],'profile':profiles,
        'meaning':'Descriptive sensitivity using a 0.25 squared-rating error allowance, not a confidence or recovery-day interval.'}
    result['unresolved']=['Raw dose equation and shared leg contribution are not identified by these reports.',
        'No personal tolerance band, return date, calibrated probability or capacity growth has been established.',
        'Latest same-day report is observed current response, not a delayed recovery endpoint.',
        'Report anchoring can overreact to noisy reports; physiological parameters remain pooled across the episode.',
        'Unrecorded activity is unknown; this calculation represents recorded exposures only.']
    return result
