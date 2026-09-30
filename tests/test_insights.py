"""What the watch saw beyond the loads: stroke breakdown, run form, ride recovery, pauses (insights.py)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt
import insights

T0 = 1790000000.0


def swim_act(sets, rest=60):
    """sets: lists of (seconds, strokes). Builds the lengths, rests between sets, and a heart rate that falls in rests."""
    lengths, recs, t = [], [], T0
    for si, s in enumerate(sets):
        for sec, n in s:
            lengths.append({"length_type": 1, "start_time": t, "total_timer_time": sec, "total_elapsed_time": sec,
                            "total_strokes": n, "swim_stroke": 0, "avg_swimming_cadence": round(n * 60 / sec)})
            recs += [{"t": t + i, "hr": 140} for i in range(int(sec))]; t += sec
        if si < len(sets) - 1:
            lengths.append({"length_type": 0, "start_time": t, "total_timer_time": rest, "total_elapsed_time": rest})
            recs += [{"t": t + i, "hr": 140 - min(30, i * 0.5)} for i in range(rest)]; t += rest
    return {"id": "s", "source": "watch", "sport": "swim", "start": T0, "minutes": (t - T0) / 60, "records": recs,
            "swim_lengths": lengths, "pool_length_m": 25.0, "events": []}


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    steady = [(25, 7)] * 16
    s = insights.swim(swim_act([steady, steady]))
    check(f"a steady swim: the stroke held, never broke down ({s['kind']}, held {s['held_m']} of {s['total_m']} m)",
          s["kind"] == "held" and s["broke_down"] is None and s["held_m"] == s["total_m"] == 800)
    check(f"SWOLF is seconds + strokes ({s['swolf_avg']}); heart rate fell {s['rest_drop_60']} in a minute's rest",
          s["swolf_avg"] == 32 and 26 <= s["rest_drop_60"] <= 30)
    fade = [(25 + 0.25 * i, 7) for i in range(16)]
    g = insights.swim(swim_act([steady, fade]))
    check(f"a slow drift over a set reads as gradual, with no step ({g['sets'][1]['fade_pct']}%)",
          g["sets"][1]["kind"] == "gradual" and g["sets"][1]["step"] is None and g["kind"] == "gradual")
    snap = [(25, 7)] * 8 + [(26, 9)] * 8
    d = insights.swim(swim_act([steady, snap]))
    st = d["sets"][1]["step"]
    check(f"a step between neighbouring lengths reads as sudden, and says what changed ({st})",
          d["kind"] == "sudden" and st and st["length_in_set"] == 8 and "more strokes" in st["what"])
    check(f"...and that is where it broke down ({d['broke_down']})", d["broke_down"] and 550 <= d["broke_down"]["at_m"] <= 650)
    fresh = [(20, 6)] + [(25, 7)] * 15
    f = insights.swim(swim_act([steady, fresh]))
    check("a fast first length off the wall doesn't fake a fade", f["sets"][1]["kind"] == "held")
    merged = [(25, 7)] * 8 + [(50, 14)] + [(25, 7)] * 7
    m = insights.swim(swim_act([steady, merged]))
    check("two lengths the watch merged into one are left out", m["kind"] == "held" and m["lengths_read"] == 29)
    rows = [{"date": f"2026-09-{20 + i}", "total_m": 2000, "held_m": 800, "broke": True} for i in range(3)]
    check("three swims breaking down near 800 m: says so", "800 m" in insights.swim_length_trend(rows)["read"])
    rows = [{"date": f"2026-09-{20 + i}", "total_m": 1500 + 100 * i, "held_m": 1500 + 100 * i, "broke": False} for i in range(3)]
    check("three swims holding to the end: room to swim longer", "room to swim longer" in insights.swim_length_trend(rows)["read"])

    # pauses
    recs = [{"t": T0 + i, "w": 120, "rpm": 80, "hr": 120} for i in range(1800)]
    for a, b in ((300, 400), (700, 760), (1000, 1090)):
        for i in range(a, b):
            recs[i] = {"t": T0 + i, "w": 0, "rpm": 0, "hr": 110}
    bike = {"id": "b", "source": "watch", "sport": "bike", "start": T0, "minutes": 30, "records": recs, "events": []}
    p = insights.pauses(bike)
    check(f"three stops mid-ride: counted and timed, and it asks ({p['count']}, {p['seconds']} s, many={p['many']})",
          p["count"] == 3 and 245 <= p["seconds"] <= 255 and p["many"])
    recs2 = [{"t": T0 + i, "w": 120, "rpm": 80 if not 500 <= i < 515 else 0, "hr": 120} for i in range(1800)]
    p2 = insights.pauses(bike | {"records": recs2})
    check("a 15-second coast is not a pause", p2["count"] == 0 and not p2["many"])
    ev = [{"event": 0, "event_type": 0, "timestamp": T0}, {"event": 0, "event_type": 4, "timestamp": T0 + 600},
          {"event": 0, "event_type": 0, "timestamp": T0 + 601}, {"event": 0, "event_type": 4, "timestamp": T0 + 900},
          {"event": 0, "event_type": 0, "timestamp": T0 + 1020}]
    p3 = insights.pauses({"sport": "swim", "start": T0, "minutes": 30, "records": [], "events": ev})
    check(f"the watch's own timer stops count; a 1-second blip doesn't ({p3['count']}, {p3['seconds']} s)",
          p3["count"] == 1 and p3["seconds"] == 120)

    # ride: efforts and recovery, work
    recs, hr = [], 110.0
    for i in range(1800):
        w = 200 if 600 <= i < 720 or 1200 <= i < 1320 else 110
        hr += ((150 if w == 200 else 110) - hr) * 0.03
        recs.append({"t": T0 + i, "w": w, "rpm": 85, "hr": round(hr)})
    r = insights.ride({"id": "r", "sport": "bike", "start": T0, "minutes": 30, "records": recs, "session": {}})
    check(f"two hard efforts found, heart-rate recovery measured ({r['efforts']})",
          len(r["efforts"]) == 2 and all(15 <= e["drop_60"] <= 40 for e in r["efforts"]) and r["recovery_60"])
    check(f"work is the sum of the watts ({r['work_kj']} kJ)", abs(r["work_kj"] - (110 * 1560 + 200 * 240) / 1000) <= 1)
    check(f"opening minutes: {r['start_hr']} bpm at {r['start_watts']} W", r["start_hr"] == 110 and r["start_watts"] == 110)

    # run: form drift judged only at a matched pace
    def run_act(late_vr, late_v):
        recs = [{"t": T0 + i, "v": 2.5 if i < 1200 else late_v, "rpm": 80, "hr": 140, "w": 220,
                 "vo": 85, "vr": 9.0 if i < 1200 else late_vr, "step": 900} for i in range(1800)]
        return {"id": "n", "sport": "run", "start": T0, "minutes": 30, "records": recs, "laps": [],
                "session": {"total_cycles": 2400, "avg_power": 220}}
    n = insights.run(run_act(10.0, 2.5))
    check(f"same pace, more bounce late: flagged ({n['drift']['form_changed']}); steps = 2 x strides ({n['steps']})",
          n["drift"]["pace_matched"] and n["drift"]["form_changed"] == ["more bounce per step"] and n["steps"] == 4800)
    n2 = insights.run(run_act(10.0, 2.0))
    check("slower late: form not judged", not n2["drift"]["pace_matched"] and n2["drift"]["form_changed"] == [])
    check(f"five-minute splits ({len(n['five_min'])})", len(n["five_min"]) == 6 and n["five_min"][0]["steps_min"] == 160)

    # across the hub
    day = lambda k: (dt.date(2026, 9, 1) + dt.timedelta(days=k)).isoformat()
    w = insights.work_vs_legs({day(2 * k): 100 + 60 * k for k in range(6)}, {day(4)},
                              {day(2 * k + 1): {"legs": 2 + k} for k in range(6)})
    check(f"ride work against next-morning legs: run days left out, line fitted ({w['read']})",
          len(w["pairs"]) == 5 and w["legs_per_100kj"] > 1 and w["r"] > 0.95)
    check("too few days: says so instead of fitting", "not enough" in insights.work_vs_legs({day(0): 100}, set(), {day(1): {"legs": 3}})["read"])
    today = dt.date.fromtimestamp(T0)
    out = insights.summary([swim_act([steady, snap]), bike], today=today)
    kinds = sorted(f["kind"] for f in out["flags"])
    check(f"the summary raises flags that ask, not grade ({kinds})",
          kinds == ["pauses", "stroke_sudden"] and all(f["ask"].endswith("?") for f in out["flags"]))
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
