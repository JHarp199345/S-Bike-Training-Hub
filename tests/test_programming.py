"""Swim, bike and run programming: phase, load state, tiers, the stroke mix, templates (programming.py)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import datetime as dt
import coach, programming as P

T = dt.date(2026, 10, 1)


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    ev = lambda days, **det: {"events": [{"id": "e", "date": (T + dt.timedelta(days=days)).isoformat(), "name": "Race", "kind": "race",
                                          "sport": det.pop("sport", "swim"), "detail": det}]}
    phases = [P.phase(ev(n), T)["phase"] for n in (120, 70, 30, 10)]
    check(f"phase counted back from the race: >12 weeks base, 12-6 build, 6-2 peak, last 2 weeks taper ({phases})", phases == ["base", "build", "peak", "taper"])
    check("the week after a race is recovery", P.phase(ev(-3), T)["phase"] == "recovery")
    check("no race: base", P.phase({}, T)["phase"] == "base")
    st = lambda sport, rd, mech: P.load_state(sport, rd, {"mechanical": mech})[0]
    check("running: rest verdict -> not ready; easy -> heavy; go with blocks carried -> moderate; clear -> fresh",
          st("run", {"running": {"verdict": "rest"}}, {}) == "not_ready" and st("run", {"running": {"verdict": "easy"}}, {}) == "heavy"
          and st("run", {"running": {"verdict": "go"}}, {"remodeling_ratio": 0.6}) == "moderate" and st("run", {"running": {"verdict": "go"}}, {}) == "fresh")
    check("the load caps the tier; heavy suggests easy; the phase suggests the key session",
          P.tier_for("fresh", "peak") == ("very_hard", "very_hard") and P.tier_for("moderate", "peak") == ("hard", "hard")
          and P.tier_for("heavy", "build") == ("moderate", "easy") and P.tier_for("not_ready", "base") == (None, None))
    tri, _ = P.event_mix(None, "base")
    check(f"triathlon (or no race): ~90% freestyle ({tri})", tri["free"] == 90 and sum(tri.values()) == 100)
    fly, why = P.event_mix(ev(50, type="swim_meet", strokes=[{"stroke": "fly", "m": 100}])["events"][0], "build")
    check(f"a butterfly meet in build: butterfly leads at 50%, the others maintained ({fly})", fly["fly"] == 50 and sum(fly.values()) == 100 and min(fly.values()) > 0)
    im, _ = P.event_mix(ev(50, type="swim_meet", strokes=[{"stroke": "im", "m": 200}])["events"][0], "build")
    check("an IM meet: all four evenly", im == {"free": 25, "back": 25, "breast": 25, "fly": 25})
    d = {}
    P.set_swim(d, {"free": 40, "back": 20, "breast": 20, "fly": 20}, 18, False)
    s = P.swim_settings(d, {"experience": {"swim": "new"}}, P.phase({}, T))
    check("the rider's dials override the race when set to", s["mix"]["free"] == 40 and s["source"] == "your dials" and s["drill_share"] == 18)
    check("drill share defaults from level (new 30%, regular 15%) and stays within 15-30",
          P.swim_settings({}, {"experience": {"swim": "new"}}, P.phase({}, T))["drill_share"] == 30
          and P.set_swim({}, drill_share=50)["drill_share"] == 30)
    out = P.programming(ev(50, type="swim_meet", strokes=[{"stroke": "fly", "m": 100}]), {"experience": {"swim": "regular"}}, "swim", T,
                        {"swimming": {"verdict": "go"}}, {"mechanical": {}}, {"swim_css": 117})
    t = out["templates"][0]
    check(f"fresh in build: a hard butterfly template, paced slower than freestyle CSS ({t['name']}; {t['lines'][2]})",
          t["tier"] == "hard" and t["focus_stroke"] == "butterfly" and "2:05/100" in " ".join(t["lines"]))
    d5 = {}; P.set_swim(d5, {"free": 50, "back": 15, "breast": 15, "fly": 20}, 20, False)
    o5 = P.programming(d5, {"experience": {"swim": "regular"}}, "swim", T, {"swimming": {"verdict": "go"}}, {"mechanical": {}}, {"swim_css": 117})
    sm = o5["templates"][0]["stroke_mix"]
    check(f"any mix works with the same templates: a 50/15/15/20 session lands within ~10% per stroke ({sm})",
          all(abs(sm[k] - v) <= 10 for k, v in {"free": 50, "back": 15, "breast": 15, "fly": 20}.items()))
    check("every template says what it trains, what it doesn't, and its sources", all(x["purpose"] and x["not_for"] and x["sources"] for x in out["templates"]))
    nr = P.programming({}, {}, "run", T, {"running": {"verdict": "rest", "why": ["accumulated mechanical load 13.2 blocks"]}}, {})
    check(f"not ready to run: says why and offers mobility ({nr['message']})", nr["not_ready"] and "13.2 blocks" in nr["message"] and nr["instead"]["lines"])
    b = P.programming({}, {"experience": {"bike": "returning"}}, "bike", T, {"verdict": "go"}, {"mechanical": {}}, {"ftp": 200})
    check(f"bike templates in watts from FTP ({b['templates'][0]['lines'][1]})", " W" in b["templates"][0]["lines"][1])
    r = P.programming({}, {"experience": {"run": "regular"}, "run_5k_s": 1500}, "run", T, {"running": {"verdict": "go"}}, {"mechanical": {}})
    check(f"run templates in paces from a recent 5K ({r['templates'][0]['lines'][1]})", "/km" in " ".join(r["templates"][0]["lines"]))
    check(f"the library has {len(P.SWIM)} swim, {len(P.RUN)} run and {len(P.BIKE)} bike templates across all four tiers",
          len(P.SWIM) >= 24 and all(any(x["tier"] == tr for x in lib) for lib in (P.SWIM, P.RUN, P.BIKE) for tr in P.TIERS))
    dd = {"events": []}
    e = coach.add_event(dd, "2026-12-01", "Winter meet", "race", "swim", "", {"type": "swim_meet", "strokes": [{"stroke": "fly", "m": 100}, {"stroke": "xx", "m": 5}]})
    check("a race can say what it is (a swim meet and its events)", e["detail"] == {"type": "swim_meet", "strokes": [{"stroke": "fly", "m": 100}]})
    ready={"swimming":{"verdict":"go"}}
    base=P.programming({}, {}, "swim", T, ready, {"mechanical":{}}, {"swim_css":117})
    check("eight profiles expose purpose, normalized stroke and work ratios, and eligibility", len(base["swim_profiles"])==8 and all(
        p["purpose"] and sum(p["mix"].values())==100 and sum(p["work_mix"].values())==100 and "reasons" in p for p in base["swim_profiles"]))
    for pid in P.SWIM_PROFILE_IDS:
        days=30 if pid=="speed-skills" else 50 if pid=="race-pace" else 120
        data=ev(days,type="swim_meet",strokes=[{"stroke":"fly","m":100}])
        o=P.programming(data,{},"swim",T,ready,{"mechanical":{}},{"swim_css":117},swim_profile=pid)
        check(f"{pid}: eligible module builds its own structured workouts", o["swim_profile"]["selected"]==pid and o["templates"] and all(
            t["swim_profile"]==pid and sum(t["work_mix"].values())>=99.8 and all(g["metres"]%25==0 for g in t["segments"]) for t in o["templates"]))
    heavy=P.programming(ev(50),{},"swim",T,{"swimming":{"verdict":"easy"}},{"mechanical":{"swim_ratio":.8}},swim_profile="race-pace")
    check("heavy load refuses race pace and selects easy recovery", heavy["swim_profile"]["fallback"] and heavy["swim_profile"]["selected"]=="recovery" and all(t["tier"]=="easy" for t in heavy["templates"]))
    stopped=P.programming({}, {}, "swim",T,{"swimming":{"verdict":"rest"}},{})
    check("a rest gate blocks every profile including kick and recovery", stopped["not_ready"] and not any(p["eligible"] for p in stopped["swim_profiles"]) and "templates" not in stopped)
    kick=P.programming({}, {}, "swim",T,ready,{"mechanical":{}},swim_profile="kick-emphasis")
    check("kick emphasis changes actual main-set work and avoids a freestyle CSS kick target", kick["templates"][0]["work_mix"]["kick"]>=60 and any("arms at sides" in line and "/100" not in line for line in kick["templates"][0]["lines"] if line.startswith("Kick:")))
    blocked=P.programming({}, {}, "swim",T,ready,{"mechanical":{"remodeling_ratio":8}},swim_profile="kick-emphasis")
    check("running mechanical load blocks kick emphasis without blocking all swimming", blocked["swim_profile"]["fallback"] and not next(p for p in blocked["swim_profiles"] if p["id"]=="kick-emphasis")["eligible"] and blocked["templates"])
    taper=P.programming(ev(10),{},"swim",T,ready,{"mechanical":{}},swim_profile="event-technique")
    normal=P.programming(ev(120),{},"swim",T,ready,{"mechanical":{}},swim_profile="event-technique")
    check("taper reduces actual generated volume", taper["templates"][0]["metres"] < normal["templates"][0]["metres"])
    dseq=ev(50);dseq["plans"]={(T-dt.timedelta(days=1)).isoformat():{"sessions":[{"sport":"swim","minutes":30,"swim_profile":"race-pace"}]}}
    after=P.programming(dseq,{},"swim",T,ready,{"mechanical":{}})
    check("recent demanding profile changes ordering to recovery", after["swim_profile"]["selected"]=="recovery" and after["swim_profile"]["context"]["recent_demanding"])
    dw=ev(50);dw["weekly"]={(T-dt.timedelta(days=3)).isoformat():{"progress":{"swim":"worse"}}}
    review=P.programming(dw,{},"swim",T,ready,{"mechanical":{}})
    check("Sunday worsening report rules out demanding profiles", review["swim_profile"]["context"]["weekly_worsening"] and review["swim_profile"]["selected"]=="recovery")
    same_day=P.programming(ev(50),{},"swim",T,ready,{"mechanical":{}},activities=[{"sport":"swim","date":T.isoformat(),"engine":70}])
    check("same-day completed demanding swim informs another session", same_day["swim_profile"]["selected"]=="recovery")
    ds={"plans":{}};P.set_swim(ds,profile_id="kick-emphasis")
    check("saved preference survives while per-session previews do not change it", P.programming(ds,{},"swim",T,ready,{"mechanical":{}},swim_profile="balanced")["swim_profile"]["selected"]=="balanced" and ds["programming"]["swim"]["profile_id"]=="kick-emphasis")
    coach.set_sessions(ds,T.isoformat(),[{"sport":"swim","minutes":30,"swim_profile":"event-technique"}])
    check("planned sessions retain profile tags for weekly ordering", ds["plans"][T.isoformat()]["sessions"][0]["swim_profile"]=="event-technique")
    try: P.set_swim(ds,profile_id="bogus");check("unknown profile rejected",False)
    except ValueError:check("unknown profile rejected",True)
    multi=ev(50,type="swim_meet",strokes=[{"stroke":"fly","m":100}])
    multi["events"].append({"date":(T+dt.timedelta(days=10)).isoformat(),"name":"5K","kind":"race","sport":"run"})
    specific=P.programming(multi,{},"swim",T,ready,{"mechanical":{}},swim_profile="race-pace")
    check("an earlier run race does not override the swim event or its phase", specific["phase"]["phase"]=="build" and specific["swim"]["mix"]["fly"]==50)
    maint=P.programming(ev(50,type="swim_meet",strokes=[{"stroke":"fly","m":100}]),{},"swim",T,ready,{"mechanical":{}},swim_profile="maintenance")
    check("maintenance actually reduces the event stroke in the generated sets", maint["templates"][0]["stroke_mix"]["fly"]<20)
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
