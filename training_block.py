"""Persistent four-week coaching block built from the athlete's existing week.

Planned minutes are exposure proxies, not tissue damage or injury probabilities.
The Sunday check-in is the review; lifting keeps its separate detailed follow-up.
"""
import copy
import datetime as dt
import re
import statistics
import math

SPORTS = ("ride", "swim", "run", "gym")
HARD_WORDS = ("hard", "interval", "threshold", "tempo", "vo2", "race", "sprint", "max")


def monday(day):
    day = dt.date.fromisoformat(day) if isinstance(day, str) else day
    return day - dt.timedelta(days=day.weekday())


def sessions(plan):
    if plan.get("sessions") is not None:
        return plan["sessions"]
    return [{"sport": plan["sport"], "minutes": plan.get("minutes") or 0,
             "name": plan["sport"].title(), "steps": [], "note": plan.get("note") or "",
             "workout":plan.get("workout"), "test":plan.get("test"), "focus":plan.get("focus"), "cadence":plan.get("cadence"), "lifts":plan.get("lifts"), "bike_plan":plan.get("bike_plan")}] if plan.get("sport") else []


def hard(session):
    # The free-text note often says what to avoid ("no hard work"). Classify the
    # prescribed name and steps only; this remains a rough scheduling flag.
    text = " ".join([str(session.get("name") or ""), *map(str, session.get("steps") or [])]).lower()
    return any(re.search(r"\b" + re.escape(word) + r"\b", text) for word in HARD_WORDS)


def running_gate(d, load=None, checkin=None):
    """The actual running decision inputs: mechanical backlog and reported response."""
    load = load or {}
    mech = (load.get("headline") or {}).get("mechanical") or {}
    remodeling = ((((load.get("systems") or {}).get("impact") or {}).get("tissue") or {}).get("remodeling") or {})
    blocks = remodeling.get("score", mech.get("remodeling_blocks"))
    limit = mech.get("block_limit", 1.5)
    forecast_days = remodeling.get("cleared_to_run_in_days")
    reports = [v for _, v in sorted((d.get("weekly") or {}).items()) if v.get("run_response")]
    response = (reports[-1].get("run_response") if reports else None) or (d.get("training_block") or {}).get("hop_status")
    readiness = {}
    if load.get("systems"):
        import loads
        readiness = (loads.readiness(load, checkin or {}).get("running") or {})
    reasons = []
    model_holds = readiness.get("verdict") == "rest" if readiness else blocks is not None and blocks > limit
    if model_holds and blocks is not None and blocks > limit:
        reasons.append(f"mechanical running load {blocks:.2f} blocks exceeds the {limit:g}-block planning limit")
    if response in ("pulling", "unresolved", "not_tested"):
        reasons.append("lower-leg response to hopping is unresolved" if response != "pulling" else "hopping still pulls")
    if readiness.get("verdict") == "rest" and not (blocks is not None and blocks > limit):
        reasons.extend(readiness.get("why") or ["running readiness says rest"])
    progression=None
    if d.get("run_progression"):
        import recovery
        progression=recovery.status(d,remodeling,(load.get("days") or [{"date":dt.date.today().isoformat()}])[-1]["date"])
        reasons.extend(progression["run_reasons"])
    # The athlete's mechanical lock is independent of a good hop report or tail exception.
    if blocks is not None and blocks>=limit and not any("mechanical running load" in x for x in reasons):
        reasons.append(f"mechanical running load {blocks:.2f} blocks must fall below {limit:g}")
    return {"progression":progression,"status": "hold" if reasons else "review" if blocks is None else "open_for_review",
            "blocks": blocks, "limit": limit, "model_days": forecast_days,
            "hop_response": response, "reasons": reasons}


def _week(d, start, done=None):
    days, totals = [], {sport: {"planned": 0, "done": 0, "exposure": 0} for sport in SPORTS}
    hard_count = 0
    lift_logs = {}
    for log in (d.get("lifting") or {}).get("logs", []):
        lift_logs.setdefault(log.get("date"), []).append(log)
    for i in range(7):
        date = (start + dt.timedelta(days=i)).isoformat()
        all_sessions = sessions(d.get("plans", {}).get(date) or {})
        ss = [s for s in all_sessions if s.get("sport") in SPORTS]
        actual = [{**s, "sport": "ride" if s.get("sport") == "bike" else s.get("sport")}
                  for s in (done or {}).get(date, []) if s.get("sport") in SPORTS or s.get("sport") == "bike"]
        logged_minutes = sum(int(x.get("minutes") or 0) for x in lift_logs.get(date, []))
        watched_minutes = sum(int(x.get("minutes") or 0) for x in actual if x["sport"] == "gym")
        if logged_minutes > watched_minutes:
            actual.append({"sport": "gym", "minutes": logged_minutes - watched_minutes})
        import coach
        marked = coach.mark_missed(d, date, coach.attach_completions(d, date, copy.deepcopy(all_sessions),
                                                                      copy.deepcopy((done or {}).get(date, []))))
        for s in ss:
            minutes = int(s.get("minutes") or 0)
            totals[s["sport"]]["planned"] += minutes
            totals[s["sport"]]["exposure"] += round(minutes * (1.8 if hard(s) else 1.0))
            hard_count += hard(s)
        for s in actual:
            totals[s["sport"]]["done"] += int(s.get("minutes") or 0)
        days.append({"date": date, "sessions": len(ss),
                     "workouts": [{"sport": s.get("sport"), "name": s.get("name"), "minutes": int(s.get("minutes") or 0),
                                   "shape": s.get("shape"), "completed": bool(s.get("completion")), "missed": bool(s.get("missed")),
                                   "missed_reason": (s.get("missed_reason") or {}).get("reason")} for s in marked],
                     "minutes": sum(int(s.get("minutes") or 0) for s in ss),
                     "hard": sum(hard(s) for s in ss), "done_minutes": sum(int(s.get("minutes") or 0) for s in actual),
                     "missed": sum(1 for s in marked if s.get("missed"))})
    return {"start": start.isoformat(), "end": (start + dt.timedelta(days=6)).isoformat(),
            "days": days, "sports": totals, "hard_sessions": hard_count,
            "total_minutes": sum(v["planned"] for v in totals.values()),
            "exposure_minutes": sum(v["exposure"] for v in totals.values()),
            "done_minutes": sum(v["done"] for v in totals.values()),
            "missed": sum(x["missed"] for x in days)}


def create(d, today, weeks=4, start_date=None, run_gate=None):
    """Repeat the *already scheduled* core week; never overwrite an existing future plan."""
    if not 4 <= int(weeks) <= 6:
        raise ValueError("block length must be 4-6 weeks")
    start = monday(start_date or today)
    if start_date and (dt.date.fromisoformat(start_date) if isinstance(start_date, str) else start_date) != start:
        raise ValueError("block start must be a Monday")
    if start < monday(today):
        raise ValueError("block start cannot be in the past")
    originals = [copy.deepcopy(d.get("plans", {}).get((start + dt.timedelta(days=i)).isoformat()) or {}) for i in range(7)]
    if not any(sessions(p) for p in originals):
        raise ValueError("schedule this week's sessions first, then start the block")
    if run_gate and run_gate.get("status") == "hold" and any(
            s.get("sport") == "run" for plan in originals for s in sessions(plan)):
        raise ValueError("The running load gate is on hold: " + "; ".join(run_gate.get("reasons") or []) +
                         ". Review the run sessions before repeating this week.")
    if d.get("training_block") and d["training_block"].get("status") == "active":
        raise ValueError("finish the current block before starting another")
    for w in range(1, int(weeks)):
        for i, original in enumerate(originals):
            if not sessions(original):
                continue
            date = (start + dt.timedelta(days=7*w+i)).isoformat()
            if sessions(d.get("plans", {}).get(date) or {}):
                continue
            copied = copy.deepcopy(sessions(original))
            for s in copied:
                s["block_id"] = start.isoformat()
            # set_sessions keeps the app's canonical session shape.
            import coach
            coach.set_sessions(d, date, copied, _trusted=True)
    import programming
    event, _ = programming.goal(d, dt.date.fromisoformat(today) if isinstance(today, str) else today)
    block = {"id": start.isoformat(), "start": start.isoformat(), "weeks": int(weeks),
             "status": "active", "reviews": {},
             "goal": {"name": event["name"], "date": event["date"], "sport": event["sport"]} if event else None}
    d["training_block"] = block
    return block


def swim_plan_forecast(d, today, load=None, done=None):
    """Conditional saved-plan estimates; never change workouts or create future symptom observations."""
    import swimload, programming
    today = dt.date.fromisoformat(today) if isinstance(today, str) else today
    load=load or {}; model=load.get("swim_recovery") or {}
    samples=[a for a in load.get("activities",[]) if a.get("sport")=="swim" and a.get("date", "")<=today.isoformat()
             and a.get("minutes",0)>0 and (a.get("swim_exposure") or {}).get("units",0)>0]
    samples=sorted(samples,key=lambda a:(a.get("date", ""),a.get("start", "")))[-10:]
    factors={"free":1,"back":.8,"breast":.7,"fly":1.3}
    def observed_factor(a):
        by=(a.get("swim_exposure") or {}).get("by_stroke") or {}
        n=sum(by.values())
        return sum(v*swimload.STROKE_FACTOR.get(k,1) for k,v in by.items())/n if n else 1
    rate=statistics.median(a["swim_exposure"]["units"]/a["minutes"] for a in samples) if samples else (load.get('planning_priors') or {}).get('swim_units_per_minute')
    factor=statistics.median(observed_factor(a) for a in samples) if samples else 1
    cardio=statistics.median(a.get("engine",0)/a["minutes"] for a in samples) if samples else ((load.get('planning_priors') or {}).get('dose_per_minute',{}).get('swim') or {}).get('engine')
    ref=model.get("reference_units")
    fast, slow=model.get("recent"), model.get("history_component")
    available=rate is not None and ref is not None and ref>0 and fast is not None and slow is not None
    profiles={p["id"]:p for p in programming.SWIM_PROFILES}
    used={}; cursor=today; out={}
    uncertain=False
    for date,plan in sorted(d.get("plans",{}).items()):
        if date<today.isoformat(): continue
        target_day=dt.date.fromisoformat(date)
        if available:
            elapsed=(target_day-cursor).days
            fast *= 2**(-elapsed/swimload.HALF_LIFE_DAYS)
            slow *= 2**(-elapsed/swimload.HISTORY_HALF_LIFE_DAYS)
            cursor=target_day
        actual=[a for a in (done or {}).get(date,[]) if a.get("sport")=="swim"]
        for index,session in enumerate(sessions(plan)):
            if session.get("sport")!="swim": continue
            n=used.get(date,0)
            if date==today.isoformat() and n<len(actual):
                used[date]=n+1; continue  # today's measured dose is already in the recovery state
            snapshot=session.get("swim_plan") or {}; pid=session.get("swim_profile")
            profile=profiles.get(pid)
            mix=snapshot.get("stroke_mix")
            work=snapshot.get("work_mix")
            why=snapshot.get("why") or session.get("note") or "Selection rationale was not recorded."
            shape=None
            if mix and work:
                stroke_factor=sum(mix.get(k,0)*v for k,v in factors.items())/max(1,sum(mix.values()))
                # Drill/swim pairs count half drill and half full stroke; kicking has no arm pulls.
                shape=(work.get("swim",0)*stroke_factor+work.get("pull",0)*stroke_factor*1.05
                       +work.get("drill_swim",0)*(.5*stroke_factor+.5*swimload.STROKE_FACTOR["drill"]))/100
            minutes=session.get("minutes") or 0
            units=rate*minutes*(shape/factor if shape is not None else 1) if rate is not None else None
            before=fast+slow if available and not uncertain else None
            raw=units/ref if units is not None and ref else None
            added=raw*(1+min(.75,.5*before)) if raw is not None and before is not None else None
            if added is not None:
                fast+=added; slow+=swimload.HISTORY_FRACTION*added
            else:
                uncertain=True
            ahead=(target_day-today).days
            out[(date,index)]={"profile_id":pid,"profile_name":profile["name"] if profile else "Profile not recorded",
                "stroke_mix":mix,"work_mix":work,"why":why,"purpose":snapshot.get("purpose") or (profile or {}).get("purpose"),
                "cardio_points":round(cardio*minutes,1) if cardio is not None else None,
                "raw_blocks":round(raw,2) if raw is not None else None,"added_blocks":round(added,2) if added is not None else None,
                "before_blocks":round(before,2) if before is not None else None,
                "after_blocks":round(fast+slow,2) if added is not None else None,
                "threshold":model.get("threshold_blocks",swimload.THRESHOLD),"days_ahead":ahead,
                "outlook":"Near-term estimate" if ahead<=7 else "Conditional forecast" if ahead<=21 else "Long-range scenario",
                "samples":len(samples),"dose_basis":("Historical swim exposure per minute" if samples else "Provisional neutral swim exposure prior")+ (" adjusted for saved stroke/work shares" if shape is not None else "; session ratios not recorded"),
                "assumptions":"All earlier planned swims completed as written; current capacity and recovery rates unchanged; no future symptom reports or unplanned workouts. Cardio and mechanical scores have different units."}
    return out


def planned_bike_dose(session, steps, ftp):
    """The same torque-squared leg formula, integrated over planned steady steps."""
    import loads, workouts
    cadence=session.get("cadence")
    if not cadence and isinstance(session.get("focus"),dict):cadence=session["focus"].get("rpm")
    cadence=cadence or [70,90]
    rpm=sum(cadence)/len(cadence) if isinstance(cadence,(list,tuple)) else float(cadence)
    if not 20<rpm<=200:raise ValueError("Planned cadence must be between 20 and 200 rpm")
    points=0
    for step in steps:
        r=step.get("rpm") or rpm
        if isinstance(r,(list,tuple)):r=sum(r)/len(r)
        watts=step.get("watts") if step.get("watts") is not None else float(step.get("pct",0))*ftp/100
        points+=float(step["minutes"])/60*12*(watts/(2*math.pi*r/60)/loads.T_REF)**2
    return workouts.stats(steps,ftp)["tss"],points,rpm


def projected_loads(d, today, dates, load=None, done=None, workouts=None):
    """Advance the saved program without changing measured history, conditioning rules or reported symptoms."""
    import loads, damage, lifting
    today=dt.date.fromisoformat(today) if isinstance(today,str) else today
    load=load or {}; done=done or {}; end=max([today]+[dt.date.fromisoformat(x) for x in dates])
    systems=load.get("systems") or {}; acts=load.get("activities") or []
    tissue=(systems.get("impact") or {}).get("tissue") or {}
    remodel=tissue.get("remodeling") or {}; short=tissue.get("event") or {}
    swim=swim_plan_forecast(d,today,load,done)
    saved={w.get("id"):w for w in workouts or []}
    history=[a for a in acts if a.get("date", "")<=today.isoformat() and a.get("minutes",0)>0]
    def rate(sport,k):
        samples=sorted([a for a in history if a.get("sport")==sport and a.get(k) is not None],key=lambda a:(a.get("date", ""),a.get("start", "")))[-10:]
        return statistics.median(a[k]/a["minutes"] for a in samples) if samples else (((load.get("planning_priors") or {}).get("dose_per_minute") or {}).get(sport) or {}).get(k)
    def estimate(s,date,index):
        sport={"ride":"bike"}.get(s.get("sport"),s.get("sport")); mins=s.get("minutes") or 0
        doses={k:0.0 for k in loads.SYSTEMS}; basis=[]; regions={}
        if sport=="rest" or not mins: return doses,regions,["Rest: no scheduled training dose"]
        for k in loads.SYSTEMS:
            r=rate(sport,k); doses[k]=r*mins if r is not None else None
        basis.append("Comparable sport median dose per minute where recorded; otherwise explicit provisional scenario prior × duration" if load.get("planning_priors") else "Recent comparable sport's median load per minute × planned duration")
        if sport in ("bike","swim","gym","test"): doses["impact"]=0.0
        if sport=="swim":
            doses["engine"]=(swim.get((date,index)) or {}).get("cardio_points")
            doses["muscle"]=mins*.05  # loads.score's existing swim-to-leg contribution
        planned_steps=None
        if sport=="bike" and s.get("workout") in saved:
            w=saved[s["workout"]]; ftp=(load.get("profile") or {}).get("ftp")
            if ftp and w.get("steps"):
                import workouts as workout_math
                planned_steps=w["steps"]
                doses["engine"],doses["muscle"],rpm=planned_bike_dose(s,planned_steps,ftp)
                basis.append(f"Saved power steps and FTP; torque-based leg dose at assumed {rpm:g} rpm unless step cadence is saved; actual ride may differ")
        if sport=="bike" and planned_steps is None and (s.get("bike_plan") or {}).get("power_steps"):
            ftp=(load.get("profile") or {}).get("ftp")
            if ftp:
                planned_steps=s["bike_plan"]["power_steps"]
                doses["engine"],doses["muscle"],rpm=planned_bike_dose(s,planned_steps,ftp)
                basis.append((s["bike_plan"].get("basis") or "Saved power stages")+f"; cadence {rpm:g} rpm unless saved per step")
        if sport=="bike" and planned_steps is None and s.get("focus"):
            import focus
            ftp=(load.get("profile") or {}).get("ftp")
            if ftp:
                f=focus.resolve(s["focus"],ftp)
                if f.get("watts"):
                    planned_steps=[{"minutes":mins,"watts":sum(f["watts"])/2}]
                    doses["engine"],doses["muscle"],rpm=planned_bike_dose({**s,"cadence":s.get("cadence") or f["rpm"]},planned_steps,ftp)
                    basis.append(f"Focus-range midpoint scenario; assumed {rpm:g} rpm, not a measured workout")
        test=s.get("test")
        if test or sport=="test":
            ftp=(load.get("profile") or {}).get("ftp")
            doses["muscle"]=rate("bike","muscle")*mins if rate("bike","muscle") is not None else None
            if ftp and test=="diagnostic":
                import coach, workouts as workout_math
                doses["engine"],doses["muscle"],_=planned_bike_dose(s,coach.TEST_STEPS,ftp)
                basis.append("Saved six-minute diagnostic protocol and current FTP")
            elif ftp and test=="ftp" and mins>=14:
                from ftptest import RampTest
                import workouts as workout_math
                ramp=RampTest(ftp,0); duration=max(4,mins-10)
                steps=[{"minutes":5,"watts":ramp.warm_w}]+[{"minutes":min(1,duration-i),"watts":ramp.start_w+ramp.increment*i} for i in range(math.ceil(duration))]+[{"minutes":5,"watts":ramp.cool_w}]
                doses["engine"],doses["muscle"],_=planned_bike_dose(s,steps,ftp)
                basis.append("FTP test scenario assumes the saved duration, current FTP and existing ramp protocol; actual stopping time is unknown")
        if sport=="gym":
            if s.get("lifts"):
                scratch=copy.deepcopy(d)
                try:
                    ls=lifting.clean(scratch,s["lifts"],draft=True)
                    if any(not x.get("scored") or x.get('kind') in lifting.MAX_BASED and x.get('weight') is None for x in ls): raise ValueError("unscored exercises or missing working weights")
                    for x in ls:
                        pts,_=lifting.points(scratch,x)
                        for key,value in lifting.spread(x,pts).items(): regions[key]=regions.get(key,0)+value
                    doses["muscle"]=sum(value for key,value in regions.items() if key in lifting.LEG_REGIONS)
                    basis.append("Regional strength and leg dose from saved exercises, sets, reps, weights and tempo; upper-body work is not charged to legs")
                except (ValueError,KeyError,TypeError): regions=None; doses["muscle"]=None; basis.append("Regional lifting dose unavailable: exercises need scoring")
            else: regions=None; doses["muscle"]=None; basis.append("Leg and regional lifting dose unavailable: no saved exercises")
        return doses,regions,basis
    current={k:{v:(systems.get(k) or {}).get(v) for v in ("fitness","fatigue")} for k in loads.SYSTEMS}
    regional=copy.deepcopy((load.get("lifting") or {}).get("regions") or {})
    regional_missing=False
    for v in regional.values(): v["value"]=v.get("blocks")
    no_run={x["date"]:x["score"] for x in remodel.get("projection",[])}
    no_short={x["date"]:x["score"] for x in short.get("projection",[])}
    run_before=remodel.get("score"); run_anchor=None; run_missing=False; new_runs=[]
    ref=remodel.get("reference_points")
    try:
        import programming
        phase_id=programming.phase(d,today)["phase"]
    except (ValueError,KeyError): phase_id="base"
    gate=running_gate(d,load,d.get("checkins",{}).get(today.isoformat()))
    goal_run="down" if gate["status"]=="hold" else "manage"
    by_date={}; previous_swim=(load.get("swim_recovery") or {}).get("score")
    swim_state=load.get("swim_recovery") or {}; sf=swim_state.get("recent"); sh=swim_state.get("history_component")
    swim_missing=sf is None or sh is None
    # Retain rolling dose windows for the same aggregate mechanical utilization as loads.headline.
    rolling={k:[(x["date"],(x.get(k) or {}).get("load")) for x in load.get("days",[]) if x["date"]<=today.isoformat()] for k in ("impact","muscle")}
    combined_before=((load.get("headline") or {}).get("mechanical") or {}).get("ratio")
    sport_rolling=[(a["date"],a.get("sport"),a.get("muscle")) for a in acts if a.get("date", "")<=today.isoformat()]
    day=today
    while day<=end:
        key=day.isoformat(); elapsed=(day-today).days; total={k:0.0 for k in loads.SYSTEMS}; region_dose={}; session_rows=[]
        prior_regional={r:v["value"] for r,v in regional.items()}
        if elapsed:
            for v in regional.values():
                if v["value"] is not None:v["value"]*=2**(-1/lifting.HALF_LIFE_DAYS)
            if not swim_missing:
                sf*=2**(-1/1.5); sh*=2**(-1/14)
        swim_add=0.0
        actual_counts={}
        for a in done.get(key,[]):
            sp={"bike":"ride"}.get(a.get("sport"),a.get("sport")); actual_counts[sp]=actual_counts.get(sp,0)+1
        gym_names={l.get("session") for l in (d.get("lifting") or {}).get("logs",[]) if l.get("date")==key}
        for index,s in enumerate(sessions(d.get("plans",{}).get(key) or {})):
            sp=s.get("sport")
            if day==today and (actual_counts.get(sp,0)>0 or sp=="gym" and s.get("name") in gym_names):
                actual_counts[sp]=max(0,actual_counts.get(sp,0)-1)
                session_rows.append({"name":s.get("name") or sp,"sport":sp,"completed":True,"why":s.get("note") or "Recorded work is already included in today's load"})
                continue
            doses,regions,basis=estimate(s,key,index)
            session_rows.append({"name":s.get("name") or sp,"sport":sp,"completed":False,"doses":doses,
                                 "why":(s.get("swim_plan") or {}).get("why") or s.get("note") or "Planning rationale not recorded", "basis":basis})
            sport_rolling.append((key,{"ride":"bike"}.get(sp,sp),doses["muscle"]))
            for k,v in doses.items(): total[k]=None if v is None or total[k] is None else total[k]+v
            if regions is None: regional_missing=True
            else:
                for r,v in regions.items():
                    if r not in regional:regional[r]={"name":lifting.regions().get(r,r),"reference":lifting.DEFAULT_REF,"value":0.0}
                    region_dose[r]=region_dose.get(r,0)+v
            if sp=="swim":
                e=swim.get((key,index)) or {}; added=e.get("added_blocks")
                if added is None: swim_missing=True; swim_add=None
                elif not swim_missing:
                    sf+=added; sh+=.1*added; swim_add=(swim_add or 0)+added
            if sp in ("run","walk"):
                if sp=="walk":
                    run_missing=True; basis.append("Walking's block allowance requires planned steps; accumulated forecast unavailable afterward")
                elif doses["impact"] is None or not ref:run_missing=True
                else:new_runs.append((key,doses["impact"]/ref))
        metrics=[]
        def row(k,name,unit,before,after,dose=None,dose_unit=None,goal="manage",method="",limit=None):
            expected="unknown" if before is None or after is None else "up" if after>before+.005 else "down" if after<before-.005 else "steady"
            metrics.append({"key":k,"name":name,"unit":unit,"before":round(before,2) if before is not None else None,
                "after":round(after,2) if after is not None else None,"session_dose":round(dose,2) if dose is not None else None,
                "dose_unit":dose_unit or unit,"expected":expected,"goal":goal,"limit":limit,
                "conflict":goal=="down" and expected=="up", "over_limit":after is not None and limit is not None and after>limit,"method":method})
        for k in loads.SYSTEMS:
            old=current[k].copy()
            if k in loads.TAU:
                tf,ta=loads.TAU[k]; lf,la=1-math.exp(-1/tf),1-math.exp(-1/ta)
            else:lf,la=2/(loads.ACWR_N[0]+1),2/(loads.ACWR_N[1]+1)
            for field,alpha in (("fitness",lf),("fatigue",la)):
                previous=current[k][field]; dose=total[k]
                # Today's recorded dose has already received today's model update; append only the pending contribution.
                current[k][field]=None if previous is None or dose is None else previous+alpha*dose if day==today else previous*(1-alpha)+alpha*dose
            if k=="engine":
                row("cardio_fatigue","Cardio fatigue","daily load",old["fatigue"],current[k]["fatigue"],total[k],"cardio points", "down" if phase_id in ("taper","recovery") else "manage", "Existing 7-day cardio fatigue model")
                row("cardio_conditioning","Cardio conditioning","daily load",old["fitness"],current[k]["fitness"],total[k],"cardio points", "manage" if phase_id in ("taper","recovery") else "up", "Existing 42-day conditioning model; a load trend, not a measured fitness gain")
            else:row(k+"_fatigue","Leg muscle load" if k=="muscle" else "Impact acute load","daily load",old["fatigue"],current[k]["fatigue"],total[k],k+" points", "manage" if k=="muscle" else goal_run, "Existing 7/28-day EWMA load model")
            if k in rolling:
                previous_actual=next((v for date,v in rolling[k] if date==key),0) if day==today else 0
                value=None if total[k] is None or previous_actual is None else previous_actual+total[k]
                rolling[k]=[(date,v) for date,v in rolling[k] if date!=key]+[(key,value)]
        def remaining(anchor,age,plateau,descent):
            if age<=plateau:return anchor
            if age<=plateau+descent:return anchor*(1-.8*(age-plateau)/descent)
            return 0.0 if age>=plateau+descent+damage.TAIL_DAYS else anchor*.2*math.exp(-5*(age-plateau-descent)/damage.TAIL_DAYS)
        run_value=None if run_missing else remaining(run_anchor[1],elapsed-run_anchor[0],run_anchor[2],run_anchor[3]) if run_anchor else remodel.get("score") if not elapsed else no_run.get(key,0.0 if remodel.get("score")==0 else None)
        run_added=0.0
        for date,raw in new_runs:
            if date!=key:continue
            if run_value is None: run_added=None; run_missing=True; break
            added=raw*damage.overlap_multiplier(run_value); run_value+=added; run_added+=added
            owed=max(0,run_anchor[0]+run_anchor[2]-elapsed) if run_anchor else max(0,(remodel.get("plateau_remaining_days") or 0)-elapsed)
            run_anchor=(elapsed,run_value,max(1,owed+5*added),max(1,3*run_value))
        row("run_mechanical","Running mechanical backlog","blocks",run_before,run_value,run_added,goal=goal_run,
            method="Existing no-new-run projection; new runs use the same overlap, owed plateau, descent and tail formulas. No future symptom changes.",limit=remodel.get("threshold_blocks",1.5))
        run_before=run_value
        short_value=short.get("score") if not elapsed else no_short.get(key,0 if short.get("score") is not None else None)
        if short_value is not None:
            short_value+=sum(raw*damage.EVENT_KERNEL[(day-dt.date.fromisoformat(date)).days] for date,raw in new_runs if 0<=(day-dt.date.fromisoformat(date)).days<len(damage.EVENT_KERNEL))
        if run_missing:short_value=None
        row("run_recent","Recent running response","reference sessions",short.get("score") if not elapsed else by_date[(day-dt.timedelta(days=1)).isoformat()]["metrics_by_key"]["run_recent"]["after"],short_value,
            goal=goal_run,method="Existing separate five-day event kernel")
        swim_value=None if swim_missing else sf+sh
        row("swim_recovery","Swim recovery load","blocks",previous_swim,swim_value,swim_add,goal="manage",method="Existing fitted swim reference, 1.5/14-day decay and overlap",limit=1.5)
        previous_swim=swim_value
        lift_before=max([v.get("blocks",0) for v in regional.values()],default=0) if not elapsed else by_date[(day-dt.timedelta(days=1)).isoformat()]["metrics_by_key"]["strength"]["after"]
        for r,v in regional.items():
            prior=v["value"]; points=region_dose.get(r,0)
            v["value"]=None if regional_missing else prior+points/(v.get("reference") or lifting.DEFAULT_REF) if prior is not None else None
            row("lift_"+r,v["name"]+" · strength","blocks",prior_regional.get(r,0.0),v["value"],points,"strength points",method="Existing region reference and lifting half-life",limit=1.5)
        lift_value=None if regional_missing else max([v["value"] for v in regional.values()],default=0)
        row("strength","Strength regional maximum","blocks",lift_before,lift_value,sum(region_dose.values()) if not regional_missing else None,"strength points",method="Highest regional lifting block; see individual regions",limit=1.5)
        ratios=[]
        for k in rolling:
            week=[v for date,v in rolling[k] if (day-dt.timedelta(days=6)).isoformat()<=date<=key]
            usual=(systems.get(k) or {}).get("usual_week")
            ratios.append(sum(week)/usual if week and all(v is not None for v in week) and usual else None)
        ratios += [run_value/1.5 if run_value is not None else None,swim_value/1.5 if swim_value is not None else None,lift_value/1.5 if lift_value is not None else None]
        combined=max(ratios) if all(v is not None for v in ratios) else None
        row("mechanical","Mechanical utilization","× limit",combined_before,combined,goal="down" if goal_run=="down" else "manage",method="Same maximum of impact, leg, running, swim and lifting utilization as the headline; unlike units stay separate",limit=1)
        combined_before=combined
        import bodymap
        regional_unknown=[]
        def week_leg(sport):
            values=[v for date,sp,v in sport_rolling if sp==sport and (day-dt.timedelta(days=6)).isoformat()<=date<=key]
            if any(v is None for v in values):regional_unknown.append(sport);return 0
            return sum(values)/(systems.get("muscle",{}).get("usual_week") or 1)
        projected_regions=bodymap.build(run_value,swim_value,week_leg("bike"),week_leg("run"),
            lift={r:v["value"] for r,v in regional.items() if v["value"] is not None}, swim_leg_ratio=week_leg("swim"))
        if run_value is None:regional_unknown.append("running backlog")
        if swim_value is None:regional_unknown.append("swim recovery")
        if regional_missing:regional_unknown.append("lifting")
        projected_regions["unavailable_sources"]=regional_unknown
        advice=[note for session in session_rows if not session.get("completed")
                for note in bodymap.overlap_advice(projected_regions,{"ride":"bike"}.get(session["sport"],session["sport"]))]
        alerts=[m["name"]+": forecast rises while the goal is recovery" for m in metrics if m["conflict"]]
        alerts.extend(dict.fromkeys(advice))
        for session in session_rows:
            if not session.get("completed") and session.get("doses",{}).get("muscle") is None:
                alerts.append(session["name"]+": leg forecast needs scored exercises or workout details; later leg estimates remain unavailable")
        if gate["status"]=="hold" and any(s["sport"]=="run" and not s.get("completed") for s in session_rows):alerts.append("Running is planned despite the current running hold; this scenario does not clear it")
        out={"date":key,"metrics":metrics,"metrics_by_key":{m["key"]:m for m in metrics},"sessions":session_rows,"alerts":alerts,
             "regional_overlap":projected_regions,"outlook":"Recorded + remaining plan" if not elapsed else "Near-term estimate" if elapsed<=7 else "Conditional forecast" if elapsed<=21 else "Long-range scenario",
             "goal_basis":"Recovery / maintenance" if phase_id in ("taper","recovery") else "Build conditioning; manage fatigue; respect running hold" if gate["status"]=="hold" else "Build conditioning; manage accumulated loads",
             "assumptions":"Saved sessions completed in order; unchanged capacity and recovery rates; no future symptom reports, extra workouts or above-allowance walking. Unknown session doses keep affected later estimates unavailable."}
        import phaseblend
        intent=phaseblend.resolve(d,key,{'running':{'verdict':'rest' if gate['status']=='hold' else 'go'}},(load or {}).get('headline'))
        out['phase_blend']=intent
        if intent['enabled']:
            out['goal_basis']='Phase roles: '+', '.join(x['name']+' '+x['role'] for x in intent['sports'].values())
            for session in session_rows:
                role=intent['sports'].get(session['sport'])
                if role:session['phase_role']=role['role'];session['phase_why']=role['why']
        by_date[key]=out;day+=dt.timedelta(days=1)
    return by_date


def recorded_load_history(load, today):
    """Recorded-model history only; never fill unavailable regional/aggregate history."""
    load=load or {}
    today=dt.date.fromisoformat(today) if isinstance(today,str) else today
    tissue=((load.get("systems") or {}).get("impact") or {}).get("tissue") or {}
    series={key:{r["date"]:r.get("score") for r in model.get("history",[])} for key,model in (
        ("run_mechanical",tissue.get("remodeling") or {}),
        ("run_recent",tissue.get("event") or {}),
        ("swim_recovery",load.get("swim_recovery") or {}))}
    days={r["date"]:r for r in load.get("days",[])}
    dates=sorted(set(days).union(*(set(v) for v in series.values())))
    out=[]
    for date in dates:
        if not (today-dt.timedelta(days=28)).isoformat()<=date<today.isoformat():continue
        day=days.get(date,{})
        values={key:(day.get(system) or {}).get(field) for key,system,field in (
            ("cardio_fatigue","engine","fatigue"),("cardio_conditioning","engine","fitness"),
            ("impact_fatigue","impact","fatigue"),("muscle_fatigue","muscle","fatigue"))}
        values.update({key:v.get(date) for key,v in series.items()})
        out.append({"date":date,"metrics":[{"key":key,"after":value} for key,value in values.items()]})
    return out


def forecast(d, today, done=None, load=None, checkin=None, workouts=None):
    """Calendar exposure, including every session on two-a-day dates."""
    block = d.get("training_block")
    goal, phases = d.get("program_goal"), d.get("phase_profiles") or []
    program = None
    if block:
        start, n = monday(block["start"]), block["weeks"]
    elif goal and phases:
        # no 4-week block: the calendar is the saved program, week by week (at most 16 weeks)
        start = monday(goal["start"])
        end = dt.date.fromisoformat(goal.get("target") or goal.get("end") or phases[-1]["end"])
        n = max(1, min(16, ((end - start).days) // 7 + 1))
        program = {"goal": goal.get("goal"), "outcome": goal.get("outcome"), "start": goal["start"],
                   "target": goal.get("target"), "hours": goal.get("hours"), "weeks": n}
    else:
        start, n = monday(today), 1
    weeks = [_week(d, start + dt.timedelta(days=7*i), done) for i in range(n)]
    swim_estimates=swim_plan_forecast(d,today,load,done)
    for week in weeks:
        for day in week["days"]:
            original=sessions(d.get("plans",{}).get(day["date"]) or {})
            for index,workout in enumerate(day["workouts"]):
                workout["steps"]=original[index].get("steps") or []
                if (day["date"],index) in swim_estimates:
                    workout["swim_outlook"]=swim_estimates[(day["date"],index)]
    projections=projected_loads(d,today,[x["date"] for w in weeks for x in w["days"]],load,done,workouts)
    for week in weeks:
        policy=(block or {}).get("progression") or {}
        if policy.get("enabled"):
            index=weeks.index(week)
            week["focus"]=("Establish a comfortable, fully scored baseline." if index==0 else
                "Consolidation week: hold increases; review whether aerobic duration should decrease." if index==n-1 else
                "Sunday review may add five easy minutes to one swim or ride; otherwise hold or reduce. Running remains separately gated.")
        if program:
            ph = next((p for p in phases if p["start"] <= week["start"] < p["end"]), None)
            shapes = [w.get("shape") for x in week["days"] for w in x["workouts"] if w.get("shape")]
            shape = max(set(shapes), key=shapes.count) if shapes else None
            label = {"peak_volume": "Peak volume", "peak_performance": "Peak performance", "consolidation": "Consolidation",
                     "test": None, "taper": None, "race": "Race week", "build": None}.get(shape)   # test/taper: the phase says it
            week["focus"] = " · ".join(x for x in (ph and ph.get("label"), label, ph and ph.get("purpose")) if x)
            week["shape"] = shape
            if goal.get("hours"):
                week["available_minutes"] = round(goal["hours"] * 60)
        import phaseblend
        week['phase_blend']=phaseblend.week(d,today,week['start'],{'running':{'verdict':'rest' if running_gate(d,load,checkin)['status']=='hold' else 'go'}},(load or {}).get('headline'))
        future=[]
        for day in week["days"]:
            day["projected_loads"]=projections.get(day["date"])
            if day["projected_loads"]:future.append(day["projected_loads"])
        if future:
            week["projected_end"]=future[-1]
            week["projected_dose"]={k:None if any(s.get("doses",{}).get(k) is None for f in future for s in f["sessions"] if not s.get("completed")) else round(sum(s["doses"][k] for f in future for s in f["sessions"] if not s.get("completed")),1) for k in ("engine","impact","muscle")}
    alerts = []
    for i, week in enumerate(weeks):
        if week["hard_sessions"] > 2:
            alerts.append(f"Week {i+1}: {week['hard_sessions']} demanding sessions across sports; review spacing and recovery.")
        for day in week["days"]:
            if day["hard"] > 1:
                alerts.append(f"{day['date']}: multiple demanding sessions on one day.")
        if i and weeks[i-1]["total_minutes"]:
            change = week["total_minutes"] / weeks[i-1]["total_minutes"] - 1
            if change > .15:
                alerts.append(f"Week {i+1}: planned time rises {change:.0%} from the prior week; check tolerance before advancing.")
    if block and block.get("reviews"):
        latest = sorted(block["reviews"].values(), key=lambda r: r["sunday"])[-1]
        if latest["decision"] == "reduce":
            alerts.append("The latest Sunday review said reduce; adjust upcoming sessions before following the repeated schedule.")
    gate = running_gate(d, load, checkin)
    if gate["status"] == "hold" and any(w["sports"]["run"]["planned"] for w in weeks):
        alerts.append("Running is scheduled while the mechanical or reported-response running gate is on hold; revise those sessions.")
    import recovery
    remodel=((((load or {}).get("systems") or {}).get("impact") or {}).get("tissue") or {}).get("remodeling") or {}
    return {"run_progression":recovery.status(d,remodel,today), "forecast_comparisons":recovery.comparisons(d,load or {},today) if d.get("load_forecasts") else [],"block": block, "weeks": weeks, "alerts": alerts, "running_gate": gate,
            "program": program, "progression_decisions":d.get("progression_decisions",[])[-12:],
            "progression_symptoms":__import__("progression").active_symptoms(d,today if isinstance(today,str) else today.isoformat()),
            "load_outlooks":list(projections.values()),
            "load_history":recorded_load_history(load,today),
            "swim_outlooks":[{"date":date,"session_index":index,**v} for (date,index),v in swim_estimates.items()],
            "suggested_start": (monday(today) + dt.timedelta(days=7)).isoformat(),
            "meaning": "Exposure minutes weight named demanding sessions 1.8× for planning only. This is an uncalibrated proxy, not tissue damage or injury prediction."}


def review(d, sunday, done, run_gate=None):
    """Attach a decision to the existing Sunday response; never infer good recovery from silence."""
    block = d.get("training_block")
    if not block or block.get("status") != "active":
        return None
    sun = dt.date.fromisoformat(sunday)
    start = monday(sun)
    index = (start - monday(block["start"])).days // 7
    if index < 0 or index >= block["weeks"]:
        return None
    wk = _week(d, start, done)
    report = d.get("weekly", {}).get(sunday) or {}
    symptoms = [report[k] for k in ("legs", "feet", "shoulders", "week") if report.get(k) is not None]
    symptoms += list((report.get("lift") or {}).values())
    matched = sum(min(v["planned"], v["done"]) for v in wk["sports"].values())
    adherence = matched / wk["total_minutes"] if wk["total_minutes"] else 0
    if not symptoms:
        decision, why = "hold", "No recovery response recorded."
    elif max(symptoms) >= 7 or report.get("week", 0) >= 7:
        decision, why = "reduce", "The athlete reported a high recovery cost."
    elif adherence < .7:
        decision, why = "repeat", "Less than 70% of scheduled time was completed; the planned dose is untested."
    elif max(symptoms) <= 4 and adherence >= .8 and report.get("week") is not None and report.get("progress"):
        if "worse" in report["progress"].values():
            decision, why = "hold", "A comparable session felt worse despite mild symptoms."
        else:
            decision, why = "advance", "At least 80% was completed, recovery was mild, and comparable work was stable or better."
    else:
        decision, why = "hold", "Recovery or completion does not yet support more load."
    sport_symptom = {"ride": "legs", "run": "feet", "swim": "shoulders"}
    by_sport = {}
    for sport, amount in wk["sports"].items():
        if not amount["planned"]:
            continue
        response = report.get(sport_symptom.get(sport)) if sport != "gym" else max((report.get("lift") or {}).values(), default=None)
        ratio = min(1, amount["done"] / amount["planned"])
        if response is not None and response >= 7:
            by_sport[sport] = "reduce"
        elif ratio < .7:
            by_sport[sport] = "repeat"
        elif decision == "advance" and response is not None and response <= 4 and report.get("progress", {}).get("bike" if sport == "ride" else sport) in ("same", "better"):
            by_sport[sport] = "advance"
        else:
            by_sport[sport] = "hold"
    if run_gate and run_gate.get("status") == "hold":
        by_sport["run"] = "hold"
        if wk["sports"]["run"]["planned"]:
            decision, why = "hold", "Running was scheduled while the running load or symptom gate was on hold."
    import phaseblend
    blend=phaseblend.resolve(d,(sun+dt.timedelta(days=1)).isoformat())
    if blend['enabled']:
        for sport,intent in blend['sports'].items():
            if by_sport.get(sport)=='advance' and not intent['can_progress']:by_sport[sport]='hold'
        if decision=='advance' and not any(v=='advance' for v in by_sport.values()):
            decision,why='hold','The next phase calls for maintenance, recovery or a pause; stable performance is success.'
    out = {"sunday": sunday, "week": index + 1, "decision": decision, "why": why,
           "planned_minutes": wk["total_minutes"], "done_minutes": wk["done_minutes"],
           "adherence": round(adherence, 2), "hard_sessions": wk["hard_sessions"],
           "reported_max": max(symptoms) if symptoms else None, "by_sport": by_sport,
           "running_gate": run_gate, "phase_blend":blend,
           "evidence": "provisional coaching rule; verify against later sessions and reports"}
    block["reviews"][sunday] = out
    # Record a recommendation. A coach or athlete reviews it before changing the next week.
    if index == block["weeks"] - 1:
        block["status"] = "complete"
    return out
