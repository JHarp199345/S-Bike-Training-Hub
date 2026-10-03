"""Local check-in album. Immutable save-time context; no retrospective model snapshots."""
import copy
import datetime as dt
import uuid


def capture(d,date,readings=None):
    import phaseblend
    forecasts=(d.get('load_forecasts') or {}).get(date) or []
    latest=forecasts[-1] if forecasts else None
    return {'captured_at':dt.datetime.now().astimezone().isoformat(timespec='seconds'),
            'readings':copy.deepcopy(readings),
            'planned_workouts':copy.deepcopy((d.get('plans') or {}).get(date)),
            'program_goal':copy.deepcopy(d.get('program_goal')),
            'phase':copy.deepcopy(phaseblend.active(d,date)),
            'forecast':copy.deepcopy(latest)}


def append(d,date,checkin,snapshot,previous=None,request_id=None):
    entries=d.setdefault('journal_entries',[])
    if request_id:
        found=next((e for e in entries if e.get('request_id')==request_id and e['date']==date),None)
        if found:return found
    latest=next((e for e in reversed(entries) if e['date']==date),None)
    if latest and latest['checkin']==checkin:
        return latest
    if previous and previous!=checkin and not any(e['date']==date for e in entries):
        entries.append({'id':'legacy-'+date,'date':date,'saved_at':None,'checkin':copy.deepcopy(previous),'snapshot':None,'legacy':True})
    entry={'id':str(uuid.uuid4()),'request_id':request_id,'date':date,
           'saved_at':dt.datetime.now().astimezone().isoformat(timespec='seconds'),
           'checkin':copy.deepcopy(checkin),'snapshot':copy.deepcopy(snapshot),'legacy':False}
    entries.append(entry)
    return entry


def view(d):
    entries=copy.deepcopy(d.get('journal_entries') or [])
    dates={e['date'] for e in entries}
    for date,c in d.get('checkins',{}).items():
        if date not in dates:entries.append({'id':'legacy-'+date,'date':date,'saved_at':None,'checkin':copy.deepcopy(c),'snapshot':None,'legacy':True})
    entries.sort(key=lambda e:(e['date'],e.get('saved_at') or '',e['id']),reverse=True)
    counts={}
    for e in entries:
        key=e['date'][:7];counts[key]=counts.get(key,0)+1
    return {'entries':entries,'months':[{'month':m,'count':n} for m,n in sorted(counts.items(),reverse=True)]}
