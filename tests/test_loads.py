"""Body-system loads: the FIT reader, per-sport scoring (run impact with weight/speed/downhill,
bike force vs cadence, gym effort, swim), heart rate calibrated to watts, the ratio zones, the
weakest-link verdict, and one activity counted once however many copies there are."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt, math, struct, tempfile
import damage, fit, loads


def fit_bytes(records, sport=2, start=None):
    """A minimal valid FIT file: a record definition + data (timestamp, HR, power, cadence, distance), and a session."""
    body = bytearray()
    # definition, local 0: record (20): 253 timestamp u32, 3 hr u8, 7 power u16, 4 cadence u8, 5 distance u32
    body += bytes([0x40, 0, 0]) + struct.pack("<H", 20) + bytes([5])
    body += bytes([253, 4, 0x86, 3, 1, 0x02, 7, 2, 0x84, 4, 1, 0x02, 5, 4, 0x86])
    for t, hr, w, rpm, d in records:
        body += bytes([0x00]) + struct.pack("<IBHBI", t - fit.FIT_EPOCH, hr, w, rpm, int(d * 100))
    # definition, local 1: session (18): 2 start_time u32, 5 sport enum, 8 total_timer_time u32, 9 total_distance u32
    body += bytes([0x41, 0, 0]) + struct.pack("<H", 18) + bytes([4]) + bytes([2, 4, 0x86, 5, 1, 0x00, 8, 4, 0x86, 9, 4, 0x86])
    t0, t1 = records[0][0], records[-1][0]
    body += bytes([0x01]) + struct.pack("<IBII", t0 - fit.FIT_EPOCH, sport, (t1 - t0) * 1000, int(records[-1][4] * 100))
    header = bytes([12, 0x10]) + struct.pack("<H", 2100) + struct.pack("<I", len(body)) + b".FIT"
    return header + bytes(body) + b"\x00\x00"


def six_dose(prof):
    """Impact points of the 30-minute, 3 km test run."""
    return loads.foot_impact({"sport": "run", "records": [], "distance_m": 3000, "minutes": 30}, prof)[0]


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    t0 = int(dt.datetime(2026, 9, 20, 9).timestamp())
    recs = [(t0 + s, 110 + s // 60, 120, 85, s * 6.0) for s in range(1800)]
    a = fit.read(fit_bytes(recs))
    check(f"FIT reader: sport, start, 1800 records ({a['sport']}, {len(a['records'])})",
          a["sport"] == "cycling" and a["start"] == t0 and len(a["records"]) == 1800)
    r = a["records"][600]
    check(f"FIT reader: heart rate, power, cadence, distance ({r})", r["heart_rate"] == 120 and r["power"] == 120 and r["cadence"] == 85 and r["distance"] == 3600)
    try:
        fit.read(b"nope nope nope"); check("not-a-FIT is refused", False)
    except fit.FitError:
        check("not-a-FIT is refused", True)

    prof = {"weight_kg": 100.0, "hr_rest": 60, "hr_max": 185, "ftp": 180}
    light = dict(prof, weight_kg=70)
    mk = lambda sport, mins, km=0.0, descent=0.0, recs=None: {"id": f"{sport}{mins}{km}", "source": "watch", "start": t0,
        "sport": sport, "minutes": mins, "distance_m": km * 1000, "descent_m": descent, "records": recs or []}
    run = mk("run", 30, 3.0)
    heavy, lite = loads.score(run, prof, 1.2), loads.score(run, light, 1.2)
    check(f"run impact rises with the 4th power of body weight (100.0 kg {heavy['impact']:.0f} vs 70 kg {lite['impact']:.0f})",
          abs(heavy["impact"] / lite["impact"] - (100.0 / 70) ** 4) < 0.01)
    f_fast, f_slow = loads.step_force(100.0, 3.3, 170), loads.step_force(100.0, 2.0, 170)
    check(f"a faster step lands harder ({f_fast / 9.81 / 100.0:.2f} vs {f_slow / 9.81 / 100.0:.2f} x body weight), "
          f"{(f_fast / f_slow) ** 4:.1f}x the damage", f_fast > f_slow)
    down = loads.score(mk("run", 30, 3.0, descent=150), prof, 1.2)
    check(f"downhill adds impact ({down['impact']:.0f})", down["impact"] > heavy["impact"])
    check(f"running loads muscle too, in proportion to weight ({heavy['muscle']:.0f} vs {lite['muscle']:.0f})",
          heavy["muscle"] > 0 and abs(heavy["muscle"] / lite["muscle"] - 100.0 / 70) < 0.01)
    # step by step from the watch: cadence counts the steps, and a jogging step lands far harder than a walking one
    mkrecs = lambda spm, v, n=1800: [{"t": t0 + s, "hr": None, "w": None, "rpm": spm / 2, "d": s * v, "alt": None, "v": v} for s in range(n)]
    jog = dict(mk("run", 30, 3.6), recs=None, records=mkrecs(160, 2.0))
    stroll = dict(mk("walk", 30, 3.6), records=mkrecs(110, 2.0))
    pj, sj, _ = loads.foot_impact(jog, prof); pw, sw2, _ = loads.foot_impact(stroll, prof)
    check(f"steps come from the watch's cadence (x2: it counts one foot) - {sj} and {sw2}", abs(sj - 160 * 30) < 20 and abs(sw2 - 110 * 30) < 20)
    check(f"per step, jogging lands {pj / sj / (pw / sw2):.0f}x harder than walking (force {2.4 / 1.2:.0f}x, to the 4th power)", pj / sj > 10 * pw / sw2)
    nocad = dict(mk("run", 60, 5.5), id="tcx")
    st_ = loads.analyse([dict(jog, id="j1"), dict(jog, id="j2", start=t0 + 86400), dict(nocad, start=t0 + 2 * 86400)], prof,
                        today=dt.date.fromtimestamp(t0 + 2 * 86400))
    old = next(x for x in st_["activities"] if x["id"] == "tcx")
    check(f"a run without cadence is scored from this rider's own runs ({old['steps']} steps, {old['equiv_km']} equivalent km)",
          abs(old["steps"] - 60 * st_["calibration"]["run_step"]["spm"]) < 2 and abs(old["impact"] - 2 * pj) < 0.05 * pj)
    spin = [{"t": t0 + s, "hr": None, "w": 120, "rpm": 90, "d": None, "alt": None} for s in range(1800)]
    grind = [dict(x, rpm=55) for x in spin]
    ms, mg = loads.bike_muscle(spin), loads.bike_muscle(grind)
    check(f"same 120 W: grinding at 55 rpm loads the legs {mg / ms:.1f}x spinning at 90 (force squared)", abs(mg / ms - (90 / 55) ** 2) < 0.01)
    check("a bike ride has no impact load", loads.score(mk("bike", 30, recs=spin), prof, 1.2)["impact"] == 0)
    gym = loads.score(mk("gym", 40), dict(prof, gym_rpe=3), 1.2)
    gym_hard = loads.score(dict(mk("gym", 40), rpe=8), prof, 1.2)
    check(f"gym: effort x minutes (RPE 3: {gym['muscle']:.0f}; RPE 8: {gym_hard['muscle']:.0f})", gym_hard["muscle"] > 2.5 * gym["muscle"])
    sw = loads.score(mk("swim", 50, 2.0), prof, 1.2)
    check(f"swimming: no impact, a trickle of muscle ({sw['muscle']:.1f})", sw["impact"] == 0 and sw["muscle"] < 5)

    # heart rate calibrated to watts on rides that have both
    ride = lambda day, w, hr: {"id": f"r{day}", "source": "watch", "start": t0 + day * 86400, "sport": "bike", "minutes": 40,
                               "distance_m": 0, "descent_m": 0,
                               "records": [{"t": t0 + day * 86400 + s, "hr": hr, "w": w, "rpm": 85, "d": None, "alt": None} for s in range(2400)]}
    acts = [ride(0, 100, 110), ride(1, 110, 115), ride(2, 100, 112)]
    k, n = loads.calibrate_hr(acts, prof)
    tss = loads.power_tss(acts[0]["records"], 180)
    check(f"calibration from {n} rides: heart-rate load of a ride ~ its watt load ({k * loads.trimp(acts[0]['records'], 60, 185):.1f} vs {tss:.1f})",
          n == 3 and abs(k * loads.trimp(acts[0]["records"], 60, 185) - tss) / tss < 0.15)
    swim = {"id": "s", "source": "watch", "start": t0 + 3 * 86400, "sport": "swim", "minutes": 40, "distance_m": 1500, "descent_m": 0,
            "records": [{"t": t0 + 3 * 86400 + s, "hr": 112, "w": None, "rpm": None, "d": None, "alt": None} for s in range(2400)]}
    st = loads.analyse(acts + [swim], prof, today=dt.date.fromtimestamp(t0 + 3 * 86400))
    sw_ = next(a for a in st["activities"] if a["sport"] == "swim")
    check(f"a swim at a similar heart rate scores a similar engine load ({sw_['engine']:.1f}, from {sw_['engine_from']})",
          sw_["engine_from"] == "heart rate" and 15 < sw_["engine"] < 40)
    check("with under two weeks of history there are no ratio zones yet", st["systems"]["muscle"]["zone"] == "building baseline")

    # three steady weeks then a spike week of running: impact goes to danger, weakest link = rest
    base = []
    for d in range(21):
        if d % 2 == 0:
            base.append(dict(mk("run", 30, 3.0), id=f"b{d}", start=t0 + d * 86400))
    spike = [dict(mk("run", 45, 6.0), id=f"s{d}", start=t0 + (21 + d) * 86400) for d in range(7)]
    st = loads.analyse(base + spike, prof, today=dt.date.fromtimestamp(t0 + 27 * 86400))
    imp = st["systems"]["impact"]
    check(f"a week of daily longer runs after easy weeks: feet {imp['tissue']['days']} days of repair backlog -> {imp['zone']}", imp["zone"] == "danger")
    check(f"the week's budget is 0.8-1.3x its usual ({imp['week_budget']}), and the week went over it ({imp['week_used']:.0f})",
          imp["week_budget"] and imp["week_used"] > imp["week_budget"][1])
    rd = loads.readiness(st, {"breathing": 2})
    check(f"feet in danger bench running ({rd['running']['verdict']}) but not the bike (bike limited by {rd['limited_by'] or 'nothing'})",
          rd["running"]["verdict"] == "rest" and "feet and bones" not in rd["limited_by"])
    six = [dict(mk("run", 30, 3.0), id=f"c{d}", start=t0 + d * 86400) for d in range(42) if d % 2 == 0]
    calm = loads.analyse(six, dict(prof, calibration={"impact": {"usual_week": 3 * 7 * 2 * six_dose(prof)}}),
                         today=dt.date.fromtimestamp(t0 + 41 * 86400))
    check(f"six steady weeks well inside capacity stay trainable ({calm['systems']['impact']['tissue']['days']} days backlog)",
          calm["systems"]["impact"]["zone"] in ("sweet spot", "room to build"))
    early = loads.analyse(base, prof, today=dt.date.fromtimestamp(t0 + 20 * 86400))
    check(f"...three weeks from zero is still a ramp by the load ratio ({early['systems']['impact']['acwr']})", early["systems"]["impact"]["acwr"] > 1.3)
    after = loads.analyse(base + spike, prof, today=dt.date.fromtimestamp(t0 + 34 * 86400))
    ta, t0a = after["systems"]["impact"]["tissue"], st["systems"]["impact"]["tissue"]
    check(f"a week after the spike the backlog is draining ({t0a['tissues']['tendon']['days']} -> {ta['tissues']['tendon']['days']} days) but not gone",
          ta["tissues"]["tendon"]["days"] < t0a["tissues"]["tendon"]["days"] and ta["tissues"]["tendon"]["days"] > 4)
    rd2 = loads.readiness(calm, {"feet": 8})
    check("your own 'feet 8/10' benches running whatever the numbers", rd2["running"]["verdict"] == "rest")
    check("your own 'legs 8/10' also benches running",
          loads.readiness(calm, {"legs": 8})["running"]["verdict"] == "rest")

    # the same session from the watch and from the bridge counts once
    tmp = pathlib.Path(tempfile.mkdtemp()); (tmp / "activities").mkdir(); (tmp / "rides").mkdir()
    (tmp / "activities" / "123.fit").write_bytes(fit_bytes(recs))
    with open(tmp / "rides" / "ride_2026-09-20_0900.csv", "w") as f:
        f.write("time,power_w,cadence_rpm\n")
        for s in range(1800):
            f.write(f"{dt.datetime.fromtimestamp(t0 + 30 + s).isoformat(timespec='seconds')},120,85\n")
    got = loads.gather(tmp / "activities", tmp / "rides")
    check(f"a ride recorded by both the watch and the bridge counts once ({[g['source'] for g in got]})", len(got) == 1)
    # tuning a system's usual week from how the body responded
    tuned = loads.analyse(base + spike, dict(prof, calibration={"impact": {"usual_week": 4000}, "muscle": {"usual_week": 50}}),
                          today=dt.date.fromtimestamp(t0 + 27 * 86400))
    ti, tm = tuned["systems"]["impact"], tuned["systems"]["muscle"]
    check("a higher tuned impact capacity lowers the block score without erasing a clustered spike",
          ti["tuned"] and ti["tissue"]["remodeling"]["score"] < st["systems"]["impact"]["tissue"]["remodeling"]["score"])
    check(f"a lower tuned muscle capacity flags the legs ({tm['zone']}, budget {tm['week_budget']})", tm["zone"] == "danger" and tm["week_budget"] == [40, 65])
    check("an untuned system keeps the model's estimate", not tuned["systems"]["engine"]["tuned"])
    tb = pathlib.Path(tempfile.mkdtemp())
    loads.set_capacity(tb, "impact", 55, "feet overdone")
    check("set_capacity saves to the profile, with the note", loads.load_profile(tb)["calibration"]["impact"]["usual_week"] == 55)
    loads.set_capacity(tb, "impact", None)
    check("and clears back to the model", "impact" not in loads.load_profile(tb)["calibration"])
    loads.set_phase(tb, "run_durability")
    check("the active phase persists for the balance grade", loads.load_profile(tb)["phase"] == "run_durability")
    try:
        loads.set_capacity(tb, "lungs", 10); check("unknown systems refused", False)
    except ValueError:
        check("unknown systems refused", True)

    # damage as a backlog: capacity-limited repair that starts slow, per tissue
    days = [(dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat() for i in range(400)]
    cap = 10.0                                                     # usual week 70 -> 10 points a day of tendon repair
    pile = damage.run([300.0] + [0.0] * 80, cap, damage.TISSUES["tendon"])
    rep = [r for _, _, r in pile]
    check(f"repair starts slow and ramps up (day 1 {rep[0]:.1f}, day 5 {rep[4]:.1f} points)", rep[0] < 0.6 * rep[4])
    check(f"a big pile drains at the capacity, not in proportion to its size (day 10: {rep[9]:.1f} of {cap:.0f} a day)", 0.85 * cap < rep[9] <= 1.05 * cap)
    clear = lambda dose, tis="tendon": next(i for i, (b_, c_, _) in enumerate(damage.run([dose] + [0.0] * 300, cap, damage.TISSUES[tis])) if b_ < 0.5 * c_)
    check(f"twice the pile takes about twice as long ({clear(300)} vs {clear(600)} days) - not a quick exponential fade",
          1.7 < clear(600) / clear(300) < 2.3)
    check(f"soft tissue clears first, tendon next, bone last ({clear(300, 'soft')}, {clear(300)}, {clear(300, 'bone')} days)",
          clear(300, "soft") < clear(300) < clear(300, "bone"))
    easy_ = damage.model(days, [5.0] * 400, 70)
    over = damage.model(days[:60], [20.0] * 60, 70)
    check(f"training at half capacity stays trainable ({easy_['tissues']['tendon']['days']} days); at double it piles up "
          f"({over['tissues']['tendon']['days']} days)", easy_["tissues"]["tendon"]["days"] < 4 and over["tissues"]["tendon"]["days"] > 7)
    spike1 = damage.model(days[:4], [300.0, 0, 0, 0], 70)
    check("unreported training and one huge run earn no conditioning credit",
          easy_["tissues"]["tendon"]["conditioning"] == 1.0
          and spike1["tissues"]["tendon"]["conditioning"] == 1.0)
    bunched = damage.model(days[:30], [0.0] * 27 + [100.0] * 3, 70)
    spread = damage.model(days[:30], [0.0] * 21 + [100.0, 0, 0, 100.0, 0, 0, 100.0, 0, 0], 70)
    check(f"the same three runs back to back pile higher ({bunched['tissues']['tendon']['peak']['days']} days) than spread out "
          f"({spread['tissues']['tendon']['peak']['days']})", bunched["tissues"]["tendon"]["peak"]["days"] > spread["tissues"]["tendon"]["peak"]["days"])
    check(f"on tissue carrying a big backlog a step does extra damage (x{bunched['tissues']['tendon']['next_step_costs']})",
          bunched["tissues"]["tendon"]["next_step_costs"] > 1.0)
    check("unconditioned repair capacity is estimated from body weight when not tuned",
          damage.base_capacity(None, 100.0) > damage.base_capacity(None, 70) and damage.base_capacity(140, 100.0) == 20)
    check(f"1,000-lb steps: a point is ~3.1 of them ({damage.STEPS_1000LB_PER_POINT:.2f})", 3.0 < damage.STEPS_1000LB_PER_POINT < 3.2)
    # The short response follows each event; the accumulated backlog survives it.
    ev = damage.model(days[:6], [100.0, 0, 0, 0, 0, 0], 160)
    check("single-run exertion response peaks the next day and fades after five days",
          ev["event"]["history"][1]["score"] > ev["event"]["history"][0]["score"]
          and ev["event"]["history"][4]["score"] > 0 and ev["event"]["score"] == 0
          and ev["tissues"]["tendon"]["days"] > 0)
    repeat = damage.model(days[:5], [100.0, 0, 0, 100.0, 0], 160)
    check("another run restarts the short response and raises the long backlog",
          repeat["event"]["score"] > ev["event"]["score"]
          and repeat["tissues"]["tendon"]["days"] > ev["tissues"]["tendon"]["days"])
    long_one = damage.remodeling_response(days[:8], [100.0] + [0.0] * 7, 160)
    long_two = damage.remodeling_response(days[:8], [100.0, 0, 0, 100.0] + [0.0] * 4, 160)
    h = long_one["history"]
    pj = long_one["projection"]
    check(f"one block holds five days, descends over three, then a ~4-month tail (projection {len(pj)} days, ends at {pj[-1]['score']})",
          long_one["plateau_days"] == 5 and long_one["descent_days"] == 3
          and all(h[i]["score"] == 1 for i in range(6))
          and h[7]["score"] < h[5]["score"] and 120 <= len(pj) <= 125 and pj[-1]["score"] == 0 and pj[60]["score"] > 0)
    check("separate events compound in the accumulated mechanical score",
          long_two["score"] > long_one["score"])
    consecutive = damage.remodeling_response(days[:3], [100.0] * 3, 300)
    blocks = consecutive["components"]
    check("three equal consecutive runs add one, two, then three provisional blocks",
          [b["added_blocks"] for b in blocks] == [1, 2, 3]
          and consecutive["score"] == 6 and consecutive["plateau_days"] == 30
          and consecutive["descent_days"] == 18)
    recovered = damage.remodeling_response(days[:10], [100.0] + [0.0] * 9, 300)
    check("a later run starts from the remaining long-tail block rather than zero",
          0 < recovered["history"][8]["score"] < 1)
    reports = {days[i]: 7 for i in (3, 4, 5)}
    reported = damage.remodeling_response(days[:8], [100.0] + [0.0] * 7, 160, feet_reports=reports)
    check("three high feet check-ins add half a day each to the provisional plateau",
          reported["plateau_days"] == long_one["plateau_days"] + 1.5
          and reported["checkins_used"] == 3)
    reassuring = damage.remodeling_response(days[:8], [100.0] + [0.0] * 7, 160,
                                             feet_reports={days[i]: 2 for i in (3, 4, 5)})
    check("reassuring reports shorten the estimate by only half a day after three observations",
          reassuring["plateau_days"] == long_one["plateau_days"] - 0.5)
    leg_reports = {days[i]: {"feet": 3, "legs": 7} for i in (3, 4, 5)}
    leg_heavy = damage.remodeling_response(days[:8], [100.0] + [0.0] * 7, 160,
                                            feet_reports=leg_reports)
    check("heavy legs keep the plateau conservative despite fine feet",
          leg_heavy["plateau_days"] == long_one["plateau_days"] + 1.5)
    beyond_anchor = damage.remodeling_response(days[:6], [100.0] * 6, 300)
    check(f"timing keeps scaling past six blocks: {beyond_anchor['score']} blocks -> {beyond_anchor['plateau_days']} day plateau, "
          f"{beyond_anchor['descent_days']} day decline",
          beyond_anchor["score"] > 6 and beyond_anchor["plateau_days"] == round(5 * beyond_anchor["score"], 1)
          and beyond_anchor["descent_days"] == round(3 * beyond_anchor["score"], 1))
    # three 100-point runs set the block (100), then a 13-block run lands once they've fully cleared
    thirteen = damage.remodeling_response(days[:171], [100.0] * 3 + [0.0] * 167 + [1300.0], 160)
    tail_day = damage.remodeling_response(days[:171 + 106], [100.0] * 3 + [0.0] * 167 + [1300.0] + [0.0] * 106, 160)
    check(f"13 blocks: running cleared in {thirteen['cleared_to_run_in_days']} days - in the tail once under 1.65, "
          f"a week sooner than under 1.5 ({thirteen['below_threshold_in_days']})",
          tail_day["phase"] == "tail" and thirteen["cleared_to_run_in_days"] < thirteen["below_threshold_in_days"])
    st_tail = {"systems": {"impact": {"tissue": {"remodeling": tail_day, "event": {"score": 0}}, "acwr": None},
                           "engine": {"acwr": 0.9, "tuned": True, "form": 0, "last7": 1, "prev7": 1},
                           "muscle": {"acwr": 0.9, "tuned": True, "form": 0, "last7": 1, "prev7": 1}},
               "days": [], "history_days": 30}
    over_ = loads.readiness(st_tail, {})["running"]["verdict"]
    good = loads.readiness(st_tail, {"feet": 2, "legs": 1})["running"]["verdict"]
    check(f"early in the tail ({tail_day['score']} blocks, over 1.65): rest ({over_}); feeling particularly good: easy ({good})",
          tail_day["score"] > 1.65 and over_ == "rest" and good == "easy")
    plateau_good = dict(st_tail, systems={**st_tail["systems"], "impact": {"tissue": {"remodeling": thirteen, "event": {"score": 0}}, "acwr": None}})
    check("in the plateau, feeling good doesn't clear running", loads.readiness(plateau_good, {"feet": 1, "legs": 1})["running"]["verdict"] == "rest")
    th = (thirteen["history"] + thirteen["projection"])[170:]
    check(f"13 blocks: flat 65 days ({th[65]['score']}), down to 20% by day 104 ({th[104]['score']}), tail still there at 5 months "
          f"({th[150]['score']}), gone after ~7 ({th[-1]['score']})",
          th[65]["score"] == 13 and abs(th[104]["score"] - 2.6) < 0.01 and 0 < th[150]["score"] < 1 and th[-1]["score"] == 0)
    spaced = [100.0 if i in (0, 10, 20, 30, 40) else 0.0 for i in range(46)]
    clean_reports = {days[i + age]: 2 for i in (0, 10, 20, 30, 40) for age in (2, 3)}
    confirmed = damage.remodeling_response(days[:46], spaced, 160, feet_reports=clean_reports)
    check("repeated recovered sessions over weeks can earn modest conditioning credit",
          confirmed["confirmed_recoveries"] == 5 and 0 < confirmed["conditioning_credit"] <= 0.1)
    ts = st["systems"]["impact"]["tissue"]
    check(f"the spike week leaves an elevated accumulated running score ({ts['remodeling']['score']} blocks)",
          ts["remodeling"]["score"] > 1.5)
    rb = loads.readiness({**st, "systems": {**st["systems"],
        "muscle": {**st["systems"]["muscle"], "acwr": None, "last7": 0, "prev7": 0},
        "impact": {**imp, "tissue": {**ts,
        "event": {**ts["event"], "score": 0}, "remodeling": {**ts["remodeling"], "score": 0}, "tissues": {
        "bone": dict(ts["tissues"]["bone"], zone="danger", days=50)}}}}}, {})
    check(f"the old bone clock alone does not set the running verdict ({rb['running']['verdict']})",
          rb["running"]["verdict"] == "go")

    # walking: daily steps outside runs, weighted by their own force, over a shrinking allowance
    wpps = loads.REF_POINTS_PER_STEP * (loads.step_force(100.0, 1.3, 105) / loads.REF_FORCE) ** 4
    jpps = loads.REF_POINTS_PER_STEP * (loads.step_force(100.0, 2.2, 150) / loads.REF_FORCE) ** 4
    check(f"a walking step does about a tenth of a jogging step's damage ({wpps / jpps:.2f})", 0.05 < wpps / jpps < 0.2)
    fresh, loaded = damage.walking_day(8000, wpps, wpps / jpps, 0), damage.walking_day(8000, wpps, wpps / jpps, 13)
    check(f"fresh: no overlap cost (x{fresh['multiplier']}), the full normal day allowed ({fresh['allowance_steps']})",
          fresh["multiplier"] == 1 and fresh["allowance_steps"] == 6000)
    check(f"loaded (13 blocks): a run would cost x4, a walk only x{loaded['multiplier']}; allowance down to {loaded['allowance_steps']}",
          1 < loaded["multiplier"] < 1.5 and loaded["allowance_steps"] < 6000 and loaded["points"] > fresh["points"])
    deep = damage.walking_day(8000, wpps, wpps / jpps, 60)
    check(f"deep in overtraining the allowance bottoms out at a quarter ({deep['allowance_steps']})", deep["allowance_steps"] == 1500)
    check("a quiet day under the allowance adds nothing", damage.walking_day(3000, wpps, wpps / jpps, 5)["points"] == 0)
    wd = [(dt.date(2026, 3, 1) + dt.timedelta(days=i)).isoformat() for i in range(120)]
    runs3 = [223.6] * 3 + [0.0] * 117                              # three reference runs: 6 blocks, a 30-day plateau
    W = lambda steps, days=wd: {"steps": {d: steps for d in days}, "pts_per_step": wpps, "severity": 0.094}
    under = lambda r: next((i for i, x in enumerate(r["history"]) if i > 5 and x["score"] < 1.5), None)
    none_, quiet = damage.remodeling_response(wd, runs3), damage.remodeling_response(wd, runs3, walking=W(3000))
    normal, busy = damage.remodeling_response(wd, runs3, walking=W(6000)), damage.remodeling_response(wd, runs3, walking=W(12000))
    check(f"quiet days (3,000 steps) under the allowance change nothing (under the limit on day {under(quiet)} vs {under(none_)})",
          under(quiet) == under(none_))
    check(f"a normal 6,000 a day while loaded slows recovery (day {under(normal)}); 12,000 a day with no rest never clears "
          f"({busy['history'][-1]['score']} blocks after 4 months)", under(normal) > under(none_) and under(busy) is None)
    short = wd[:21]
    base21 = damage.remodeling_response(short, runs3[:21])
    one_day = damage.remodeling_response(short, runs3[:21], walking={"steps": {wd[10]: 13000}, "pts_per_step": wpps, "severity": 0.094})
    check(f"one big walking day pushes the plateau out by under a day ({base21['plateau_remaining_days']} -> "
          f"{one_day['plateau_remaining_days']}) - it doesn't restart it",
          0 < one_day["plateau_remaining_days"] - base21["plateau_remaining_days"] < 2)
    capped = damage.remodeling_response(short, runs3[:21], walking=W(40000, short))
    check(f"however much walking, the plateau left never exceeds 5 days per block carried ({capped['plateau_remaining_days']} days, "
          f"{capped['score']} blocks)", capped["plateau_remaining_days"] <= 5 * capped["score"] + 0.1)
    # the steps file, and a run's steps are taken out of the day's count
    ts_ = pathlib.Path(tempfile.mkdtemp())
    loads.set_steps(ts_, {"2026-09-26": 12975}); loads.set_steps(ts_, {"2026-09-27": 4491})
    check("step counts are saved and merged by day", loads.load_steps(ts_) == {"2026-09-26": 12975, "2026-09-27": 4491})
    try:
        loads.set_steps(ts_, {"yesterday": 5}); check("bad dates refused", False)
    except ValueError:
        check("bad dates refused", True)
    wi = loads.walking_inputs([{"sport": "run", "date": "2026-09-23", "steps": 3618}], {"2026-09-23": 13943, "2026-09-24": 8013}, prof)
    check(f"walking = the day's steps minus run steps ({wi['steps']})", wi["steps"] == {"2026-09-23": 10325, "2026-09-24": 8013})
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
