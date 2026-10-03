"""Lifting and functional strength: plans, scoring, the check-off, the steer, rules, follow-ups (lifting.py)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt
import coach, lifting

new = lambda: {"checkins": {}, "plans": {}, "ratings": {}}


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    bench = {"name": "Bench press", "kind": "barbell", "sets": 3, "reps": 10, "weight": 185,
             "regions": {"pecs": 50, "shoulders": 25, "triceps": 25}}
    dead = {"name": "Deadlift", "kind": "barbell", "sets": 3, "reps": 5, "weight": 275,
            "regions": {"lower_back": 30, "glutes": 25, "hamstrings": 20, "quads": 15, "forearms": 10}}
    hang = {"name": "Dead hang", "kind": "bodyweight", "sets": 3, "seconds": 30, "regions": {"forearms": 40, "lats": 40, "shoulders": 20}}
    day = "2026-10-05"
    d = new()
    lifting.set_session(d, day, [bench, dead, hang], name="Strength A")
    s = d["plans"][day]["sessions"][0]
    check(f"a scored gym session lands on the plan ({s['name']}, {len(s['lifts'])} lifts, ~{s['minutes']} min)",
          s["sport"] == "gym" and all(x["scored"] for x in s["lifts"]))
    check("a timed hold is marked restorative, a heavy lift build", s["lifts"][2]["style"] == "restorative" and s["lifts"][0]["style"] == "build")
    v = lifting.evaluate(d, [dead])
    e = v["exercises"][0]
    check(f"the movement's strain is shared by the AI's percentages (deadlift {e['points']} points: lower back {v['regions']['lower_back']}, quads {v['regions']['quads']})",
          abs(v["regions"]["lower_back"] - 0.30 * e["points"]) < 0.2 and abs(sum(v["regions"].values()) - e["points"]) < 0.3)
    sw = lambda w: lifting.evaluate(d, [{"name": "Cable rotational swing", "kind": "power", "sets": 1, "reps": 10, "weight": w, "per_side": True,
                                         "regions": {"obliques": 60, "abs": 40}}])["points_total"]
    check(f"power moves (swings, chops) go by effort and weight, so a heavier set counts more ({sw(20)} < {sw(30)} < {sw(40)})", sw(20) < sw(30) < sw(40))
    slow = lifting.evaluate(d, [dict(bench, tempo="3-0-3")])["points_total"]
    check(f"tempo 3-0-3 counts as more strain per rep ({slow} vs {lifting.evaluate(d, [bench])['points_total']})",
          slow > lifting.evaluate(d, [bench])["points_total"] * 1.5)
    # holds (the rider's report, 2026-10-03): time under the full load counts as reps, not as a capped tempo bonus
    fly = {"name": "Rear delt fly", "kind": "cable", "sets": 3, "reps": 10, "weight": 15, "unit": "lb", "regions": {"shoulders": 70, "scapula": 30}}
    p0, ph, pt = (lifting.evaluate(d, [x])["points_total"] for x in (fly, dict(fly, hold=9), dict(fly, tempo="1-9-1")))
    check(f"a 9 s hold in every rep counts as 3 more reps each ({p0} -> {ph}; as tempo it was capped at {pt})",
          abs(ph - 4 * p0) < 0.5 and ph > pt * 1.5)
    try:
        lifting.clean(d, [dict(hang, hold=5)]); bad = False
    except ValueError:
        bad = True
    check("a hold needs reps (a static hold is given in seconds)", bad)
    dc = new(); dc["lifting"] = {"strength": {"cable curl": {"name": "Cable curl", "e1rm_kg": 36.0, "date": day, "from": "test"}}}
    curl = {"name": "Cable curl", "kind": "cable", "sets": 3, "seconds": 10, "weight": 120, "unit": "lb", "regions": {"biceps": 70, "forearms": 30}}
    eh = lifting.evaluate(dc, [curl])["exercises"][0]
    check(f"a heavy static hold is judged against the max, above it if need be ({eh['points']} points at {eh.get('intensity_pct')}%)",
          eh["method"] == "hold against max" and eh["intensity_pct"] == 130 and eh["points"] > 2 * lifting.evaluate(new(), [curl])["points_total"])
    df = new(); lifting.set_session(df, day, [dict(bench, name="Incline press")])
    lf = lifting.log(df, day, [{"failure": True}], 7, 8)
    dn = new(); lifting.set_session(dn, day, [dict(bench, name="Incline press")])
    ln = lifting.log(dn, day, [{}], 7, 8)
    rm = lambda x: lifting.state(x)["strength"]["incline press"]["e1rm_kg"]
    check(f"a set to failure has no reps in reserve, so the max isn't inflated ({rm(df)} kg vs {rm(dn)} kg at effort 7)",
          rm(df) < rm(dn) and lf["lifts"][0]["failure"])
    for bad_actual in ({"hold": -1}, {"hold": 121}, {"failure": "false"}):
        invalid = new(); lifting.set_session(invalid, day, [bench])
        try:
            lifting.log(invalid, day, [bad_actual], 7, 8); rejected = False
        except ValueError:
            rejected = True
        check(f"bad hold/failure report is rejected: {bad_actual}", rejected)
    ds = new(); ds["lifting"] = {"strength": {"cable curl": {"e1rm_kg": 36.0}}}
    lifting.set_session(ds, day, [curl])
    ls = lifting.log(ds, day, [{"seconds": 20}], 7, 8)
    check("actual static-hold duration reaches scoring and the saved log", ls["lifts"][0]["seconds"] == 20 and ls["lifts"][0]["hold_reps"] == 6.7)
    dz = new(); lifting.set_session(dz, day, [dict(bench, hold=9)])
    lz = lifting.log(dz, day, [{"hold": 0}], 7, 8)
    check("reporting no hold removes the planned pause", lz["lifts"][0]["hold"] == 0 and not lz["lifts"][0].get("hold_reps"))
    dk = new(); dk["lifting"] = {"strength": {"bench press": {"name": "Bench press", "e1rm_kg": 112.0, "date": day, "from": "test"}}}
    base, heavy = lifting.evaluate(dk, [bench])["points_total"], lifting.evaluate(dk, [dict(bench, weight=205)])["points_total"]
    check(f"with a known max, a heavier plan is more load ({heavy} vs {base})", heavy > base)

    # the rider's plain list, then the AI scores it
    dr = new()
    lifting.set_session(dr, day, [{"name": "Kneeling rainbow throw", "sets": 3, "reps": 8, "weight": 10}], draft=True)
    x = dr["plans"][day]["sessions"][0]["lifts"][0]
    check("the rider's plain list is saved unscored, and shows up for the AI to score", not x["scored"]
          and lifting.unscored_sessions(dr, dt.date(2026, 10, 1))[0]["name"] == "Strength")
    try:
        lifting.set_session(dr, day, [{"name": "Kneeling rainbow throw", "sets": 3, "reps": 8}])
        strict = False
    except ValueError:
        strict = True
    check("the AI's own plans must be scored (kind and regions)", strict)
    early = lifting.log(dr, day, [{}], 7, 8)
    check("checked off before it's scored: recorded, load pending", early["points_total"] == 0 and early["unscored"])
    lifting.set_session(dr, day, [{"name": "Kneeling rainbow throw", "kind": "medicine_ball", "sets": 3, "reps": 8, "weight": 10,
                                   "per_side": True, "regions": {"obliques": 50, "abs": 30, "shoulders": 20}}])
    after = lifting.state(dr)["logs"][-1]
    check(f"...and once the AI scores it, the checked-off load is filled in ({after['points_total']} points)", after["points_total"] > 0 and not after["unscored"])
    lifting.set_session(dr, "2026-10-09", [{"name": "Kneeling rainbow throw", "sets": 2, "reps": 6}], draft=True)
    check("next time the rider lists it, the library scores it by name", dr["plans"]["2026-10-09"]["sessions"][0]["lifts"][0]["scored"])

    # rules
    lifting.add_rule(d, "No squats")
    lifting.add_rule(d, "Favorite lift: incline dumbbell press")
    kinds = {r["text"]: r["kind"] for r in lifting.rules(d)}
    check(f"rules read as never / favourite / note ({kinds})", kinds == {"No squats": "never", "Favorite lift: incline dumbbell press": "favourite"})
    try:
        lifting.set_session(d, day, [dict(bench, name="Back squat")])
        refused = False
    except ValueError as err:
        refused = "No squats" in str(err)
    check("'No squats' refuses a back squat, and says which rule", refused)
    try:
        coach.set_sessions(d, "2026-10-06", [{"sport": "gym", "minutes": 30, "lifts": [dict(bench, name="Goblet squats")]}])
        refused2 = False
    except ValueError:
        refused2 = True
    check("...also when the AI plans through set_plan sessions", refused2)
    db = new(); lifting.add_rule(db, "No barbell squats", "too much force on the back")
    def ok_plan(ex):
        try:
            lifting.clean(db, [ex]); return True
        except ValueError:
            return False
    check("'No barbell squats' refuses a back squat done with a barbell, and 'barbell squat' by name",
          not ok_plan(dict(bench, name="Back squat")) and not ok_plan(dict(bench, name="Barbell squat", kind="other")))
    check("...but not a goblet squat with a kettlebell", ok_plan(dict(bench, name="Goblet squat", kind="kettlebell")))
    lifting.remove_rule(d, "squats")
    check("and a rule can be removed by what it excludes", len(lifting.rules(d)) == 1)
    legacy = new(); legacy["lifting"] = {"exclusions": [{"name": "cartwheels", "key": "cartwheels", "why": "can't", "date": day}]}
    check("the first version's won't-do list carries over as rules", lifting.rules(legacy)[0]["text"] == "No cartwheels")

    # the check-off
    try:
        lifting.log(d, day, [{"weight": 170}, {}, {}], 8, 7)
        asked = False
    except ValueError as err:
        asked = "why" in str(err) and "Bench press" in str(err)
    check("lighter than planned without a reason: it asks why", asked)
    planned_pts = lifting.evaluate(d, [bench])["points_total"]
    lg = lifting.log(d, day, [{"weight": 170, "why": "too_heavy"}, {}, {}], 8, 7)
    b = lg["lifts"][0]
    rm = lifting.state(d)["strength"]["bench press"]["e1rm_kg"]
    check(f"too heavy: the load stays as planned ({b['points']} vs {planned_pts}) and the 1RM comes down ({rm} kg)",
          abs(b["points"] - planned_pts) < 0.5 and abs(rm - lifting.one_rm(170 * lifting.KG["lb"], 10)) < 0.2)
    d2 = new(); lifting.set_session(d2, day, [bench])
    lazy = lifting.log(d2, day, [{"weight": 135, "why": "chose"}], 5, 8)["lifts"][0]
    check(f"chose lighter: the load is what was lifted ({lazy['points']} < {planned_pts})", lazy["points"] < planned_pts * 0.8)
    d3 = new(); lifting.set_session(d3, day, [bench])
    more = lifting.log(d3, day, [{"weight": 200}], 7, 8)["lifts"][0]
    check(f"15 lb more: more load ({more['points']}), and a higher strength estimate", more["points"] > planned_pts
          and lifting.state(d3)["strength"]["bench press"]["e1rm_kg"] > lifting.one_rm(185 * lifting.KG["lb"], 10))
    check("the leg regions' points are counted for the leg budget", lg["leg_points"] > 0)

    # the steer
    fresh = lifting.steer(new(), {"headline": {"mechanical": {"remodeling_ratio": 0.2, "impact_ratio": 0.3, "muscle_ratio": 0.4, "swim_ratio": 0.1}}})
    beat = lifting.steer(new(), {"headline": {"mechanical": {"remodeling_ratio": 1.3, "impact_ratio": 0.5, "muscle_ratio": 0.7, "swim_ratio": 0.2}}})
    easy = lifting.steer(new(), {"headline": {"mechanical": {"muscle_ratio": 0.3}}, "verdict": "easy"})
    check(f"fresh: build, ~5-10% restorative ({fresh['mode']}, {fresh['restorative_share']})", fresh["mode"] == "build" and fresh["restorative_share"] <= 0.1)
    check(f"running blocks over the limit: restorative, ~80% ({beat['mode']}, {beat['restorative_share']}; {beat['why'][0]})",
          beat["mode"] == "restorative" and beat["restorative_share"] >= 0.75 and "running blocks" in beat["why"][0])
    check(f"an easy day leans restorative ({easy['restorative_share']})", easy["restorative_share"] >= 0.5)
    core = lifting.steer(new(), {"headline": {"mechanical": {"remodeling_ratio": 8.8, "muscle_ratio": 0.9}}, "verdict": "easy", "engine_level": "go"},
                         ["obliques", "abs", "lower_back"])
    legday = lifting.steer(new(), {"headline": {"mechanical": {"remodeling_ratio": 8.8, "muscle_ratio": 0.9}}, "verdict": "easy", "engine_level": "go"},
                           ["quads", "glutes"])
    check(f"a core session doesn't carry the running blocks ({core['mode']} {core['restorative_share']}); a leg session does ({legday['mode']} {legday['restorative_share']})",
          core["mode"] == "build" and legday["mode"] == "restorative")
    kneel = lifting.steer(new(), {"headline": {"mechanical": {"remodeling_ratio": 8.8}}, "verdict": "easy", "engine_level": "go"},
                          {"obliques": 25, "shoulders": 13, "abs": 12, "lower_back": 8, "glutes": 6})
    check(f"kneeling core work with a little glute doesn't carry the running blocks ({kneel['mode']})", kneel["mode"] == "build")
    ev = lifting.evaluate(new(), [bench, dead], ctx={"headline": {"mechanical": {"remodeling_ratio": 1.3}}})
    check(f"evaluate says when a session grinds more than the steer suggests ({ev['fits_steer']})", ev["fits_steer"].startswith("more grinding"))
    dl = new()
    for k in range(4):                                         # grinding sessions on beat-up days that left them wrecked
        dd = f"2026-10-{10 + 3 * k:02d}"
        lifting.set_session(dl, dd, [bench])
        lifting.log(dl, dd, [{}], 9, 3, ctx={"headline": {"mechanical": {"remodeling_ratio": 0.8}}})
    moved = lifting.steer(dl, {"headline": {"mechanical": {"remodeling_ratio": 0.8}}})
    base_ = lifting.steer(new(), {"headline": {"mechanical": {"remodeling_ratio": 0.8}}})
    check(f"poor reports after grinding sessions move the curve toward restorative ({base_['restorative_share']} -> {moved['restorative_share']})",
          moved["restorative_share"] > base_["restorative_share"] and moved["learned_offset"] > 0)
    lifting.set_session(dl, "2026-10-30", [bench], override="Feeling great, going heavy")
    check("the rider's override is kept with the plan", dl["plans"]["2026-10-30"]["sessions"][0]["override"].startswith("Feeling great"))

    # recovery blocks and the follow-up
    check("two days after a session the follow-up isn't due yet", lifting.pending_followup(d, dt.date(2026, 10, 7)) is None)
    today = dt.date(2026, 10, 8)
    pf = lifting.pending_followup(d, today)
    check(f"three days later the follow-up is due ({[r['key'] for r in pf['regions']]})", pf and pf["log_date"] == day)
    m0 = lifting.model(d, today)["regions"]["pecs"]
    lifting.followup(d, day, {"pecs": 9}, "harder", today=today)
    m1 = lifting.model(d, today)["regions"]["pecs"]
    check(f"very sore chest two days on: the chest's block shrinks ({m0['reference']} -> {m1['reference']})", m1["reference"] < m0["reference"])
    check("no follow-up due once it's answered", lifting.pending_followup(d, today) is None)
    check("still open on day 5, gone on day 6", lifting.pending_followup(new() | {"lifting": {"logs": [{"date": day, "session": "x", "regions": {"abs": 5}}], "followups": {}}}, dt.date(2026, 10, 10)) is not None
          and lifting.pending_followup(new() | {"lifting": {"logs": [{"date": day, "session": "x", "regions": {"abs": 5}}], "followups": {}}}, dt.date(2026, 10, 11)) is None)
    # the Sunday check-in
    import weekly
    dw = new(); lifting.set_session(dw, "2026-10-07", [dead]); lifting.log(dw, "2026-10-07", None, 7, 7)
    done = {"2026-10-06": [{"sport": "bike", "minutes": 40}], "2026-10-08": [{"sport": "swim", "minutes": 45}], "2026-10-07": [{"sport": "gym", "minutes": 30}]}
    q = weekly.due(dw, dt.date(2026, 10, 11), done)
    keys = [x["key"] for x in q["questions"]]
    check(f"Sunday asks only about what the week held: riding, swimming, the lifted muscles, the week ({keys})",
          "legs" in keys and "shoulders" in keys and "feet" not in keys and "lift:lower_back" in keys and keys[-1] == "week")
    check("open through Tuesday, not Wednesday", weekly.due(dw, dt.date(2026, 10, 13), done) and weekly.due(dw, dt.date(2026, 10, 14), done) is None)
    weekly.record(dw, "2026-10-11", {"legs": 4, "shoulders": 3, "lift": {"lower_back": 8}, "week": 6})
    check("answered: it fills that Sunday's check-in, and isn't asked again", dw["checkins"]["2026-10-11"]["legs"] == 4
          and weekly.due(dw, dt.date(2026, 10, 12), done) is None)
    m2 = lifting.model(dw, dt.date(2026, 10, 11))["regions"]["lower_back"]
    dw2 = new(); lifting.set_session(dw2, "2026-10-07", [dead]); lifting.log(dw2, "2026-10-07", None, 7, 7)
    m1 = lifting.model(dw2, dt.date(2026, 10, 11))["regions"]["lower_back"]
    check(f"a sore lower back on Sunday refits its lifting block ({m1['reference']} -> {m2['reference']}, {m2['reference_from']})",
          m2["follow_ups_used"] == 1 and m2["reference"] < m1["reference"])
    check("kilograms work too", lifting.clean(d, [dict(bench, unit="kg", weight=84)])[0]["unit"] == "kg")
    # lifting carries over into each sport's verdict, by how much the muscle works in that sport
    import loads
    sysd = {x: {"tuned": True, "acwr": 1.0, "last7": 0, "prev7": 0} for x in loads.SYSTEMS}
    st = {"systems": sysd, "history_days": 30, "days": [],
          "lifting": {"regions": {"shoulders": {"name": "Shoulders", "blocks": 2.0}, "obliques": {"name": "Obliques", "blocks": 0.4}}}}
    rd = loads.readiness(st, {})
    check(f"shoulders carrying 2 blocks from lifting: swimming rests, and says why ({rd['swimming']['verdict']}: {rd['swimming']['why']})",
          rd["swimming"]["verdict"] == "rest" and "lifting: shoulders" in rd["swimming"]["why"][0])
    check(f"...but the bike and running barely use shoulders: they stay go ({rd['verdict']}, {rd['running']['verdict']})",
          rd["verdict"] == "go" and rd["running"]["verdict"] == "go")
    st["lifting"]["regions"] = {"quads": {"name": "Quadriceps", "blocks": 1.2}}
    rd = loads.readiness(st, {})
    check(f"quads carrying 1.2 blocks: the bike goes easy ({rd['verdict']}, {rd['limited_by']})", rd["verdict"] == "easy" and any("quadriceps" in w for w in rd["limited_by"]))
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
