"""Validate and attach a parsed watt-based ride without altering actual records."""
import copy
import math
import coach
import workouts


def add(d, date, req, folder=None):
    blocks=req.get('ride_blocks')
    if req.get('sport')!='ride' or not isinstance(blocks,list):
        raise ValueError('Parsed power blocks require a cycling session')
    stages=workouts.flatten(blocks)
    total=sum(s['minutes'] for s in stages)
    minutes=float(req.get('minutes') or 0)
    if not math.isfinite(minutes) or abs(total-minutes)>.01:
        raise ValueError(f'Ride stages total {total:g} minutes, not {minutes:g}. Review the duration before saving.')
    candidate=copy.deepcopy(d)
    previous=(candidate.get('plans',{}).get(date) or {})
    import training_block
    sessions=copy.deepcopy(training_block.sessions(previous))
    index=req.get('index')
    if index is not None:
        if isinstance(index,bool) or not isinstance(index,int) or not 0<=index<len(sessions):
            raise ValueError('Choose an existing session to edit')
        if sessions[index].get('sport')!='ride':raise ValueError('Keep the existing session sport when editing')
    entry={k:req[k] for k in ('sport','name','steps','note','typed_workout','cadence','focus') if k in req}
    entry.update(minutes=round(total,4),bike_plan={'power_steps':stages,'basis':'Explicit parsed watts; range midpoints for forecast and ERG, bounds retained for display. Ramps use approximately 15-second stages, capped at 120 stages per ramp. Actual effort may differ.'})
    if index is None:sessions.append(entry)
    else:sessions[index]=entry
    coach.set_sessions(candidate,date,sessions)
    # All session and block validation happens before any workout file is written.
    wid=workouts.save({'name':req.get('name'),'note':req.get('note',''),'blocks':blocks,'adaptive':False},folder=folder)
    candidate['plans'][date]['sessions'][index if index is not None else -1]['workout']=wid
    return candidate,wid
