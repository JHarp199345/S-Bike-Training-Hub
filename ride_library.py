"""Read-only ride menu: schedule, existing load guidance, and saved ride history."""
import copy
import csv
import datetime as dt
import math
from pathlib import Path
import coach
import routes
import workouts


def recent_use(base):
    """An explicit start event is evidence of use, not proof of completion."""
    used={}
    for file in sorted((Path(base)/'rides').glob('ride_*_events.csv'),reverse=True)[:60]:
        try:
            with file.open() as f:
                for n,row in enumerate(csv.DictReader(f)):
                    if n>=20000:break
                    event=row.get('event','');key=None
                    if event.startswith('Workout started: '):key=('workout',event[17:].rsplit(' (at FTP ',1)[0])
                    if event.startswith('Route started: '):key=('route',event[15:].split(' at ',1)[0])
                    if key:used[key]=max(used.get(key,''),row.get('time','')[:10])
        except (OSError,UnicodeError,csv.Error):continue
    return used


def listing(bridge):
    import rider, loads, programming, mapserver
    base=Path(bridge.csv_path).resolve().parent.parent
    date=coach.today();d=coach.load(base/'coach.json');profile={**rider.load(base/'profile.json'),**bridge.profile}
    saved=copy.deepcopy(workouts.list_all(profile['ftp']));terrain=copy.deepcopy(routes.list_routes());used=recent_use(base)
    warning=None;context={};scheduled=[];failed=False
    try:
        state=mapserver.load_state(base)
        if state.get('systems'):
            ready=loads.readiness(state,d['checkins'].get(date))
            context=programming.programming(d,profile,'bike',dt.date.fromisoformat(date),ready,state.get('headline'))
        else: warning='Log rides and check-ins to build your load guidance. For now, compare the displayed ride estimates.'
        today=next(x for x in coach.week(d,date,mapserver.done_by_day(base,d)) if x['date']==date)
        scheduled=[s for s in today['sessions'] if s.get('sport')=='ride' and not s.get('completion') and not s.get('skipped')]
    except Exception:
        failed=True
        warning='Current load guidance could not refresh. Review the Fitness dashboard before choosing a demanding ride.'
        scheduled=[s for s in (d['plans'].get(date) or {}).get('sessions',[]) if s.get('sport')=='ride' and not s.get('skipped')]
    schedule_workouts={s.get('workout') for s in scheduled};schedule_routes={s.get('route_id') for s in scheduled}
    # Compare real calculated TSS and intensity to saved prescribed power stages.
    targets=[]
    for s in scheduled:
        stages=(s.get('bike_plan') or {}).get('power_steps')
        if stages:targets.append(workouts.stats(stages,profile['ftp']))
        elif s.get('workout'):
            match=next((w for w in saved if w['id']==s['workout']),None)
            if match:targets.append(match['stats'])
    basis="today's prescribed power stages" if targets else 'the current cycling template suggested by the Hub'
    if not targets:
        for t in context.get('templates',[]):
            if t.get('tier')==context.get('suggested_tier') and (t.get('bike_plan') or {}).get('power_steps'):
                targets.append(workouts.stats(t['bike_plan']['power_steps'],profile['ftp']))
    for w in saved:
        st=w['stats'];w['last_used']=used.get(('workout',w['name']));w['scheduled']=w['id'] in schedule_workouts
        # A dimensional comparison, not an injury probability or safety certificate.
        w['fit_distance']=min((math.log((st['tss']+1)/(t['tss']+1))**2 + math.log((st['if']+.01)/(t['if']+.01))**2 for t in targets),default=None)
        w['match_basis']=basis if w['fit_distance'] is not None else None
    saved.sort(key=lambda w:(not w['scheduled'],w['fit_distance'] if w['fit_distance'] is not None else w['stats']['tss'],w['last_used'] or '',w['name']))
    for r in terrain:r.update(last_used=used.get(('route',r['id'])),scheduled=r['id'] in schedule_routes)
    terrain.sort(key=lambda r:(not r['scheduled'],r['last_used'] or '',r.get('climb_m',0),r.get('km',0),r['name']))
    return {'date':date,'ftp':profile['ftp'],'workouts':saved,'routes':terrain,
            'scheduled':[{'name':s['name'],'minutes':s.get('minutes'),'workout':s.get('workout'),'route_id':s.get('route_id')} for s in scheduled],
            'guidance':{'load_state':context.get('load_state'),'phase':(context.get('phase') or {}).get('phase'),
                        'suggested_tier':context.get('suggested_tier'),'tier_cap':context.get('tier_cap'),
                        'not_ready':context.get('not_ready',False),'why':context.get('load_why',[]),'warning':warning,
                        'review_required':failed,
                        'basis':'Load matching orders choices; it does not certify readiness. Routes are ordered by schedule, recorded use, then climb and distance. Terrain alone cannot forecast your effort.'}}
