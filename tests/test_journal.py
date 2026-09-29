"""The journal flags: the words never score - they raise a flag when they disagree with the sliders (or name
something serious), and only a flag the rider confirms counts, the way moving its slider would."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import tempfile
import coach, journal, loads


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)

    f = journal.find
    check("sharp pain and a tender spot: bone", f("sharp pain in my shin, point tender")["bone"] == ["sharp pain", "point tender"])
    check("pain tied to hopping, a few words apart: bone",
          f("Stopped hopping at 2, pain in the calf when hopping.").get("bone") == ["pain when hopping or walking"])
    check("negated: 'not swollen, no sharp pain' raises nothing", f("not swollen, no sharp pain") == {})
    check("'not painful' isn't pain", f("legs tired but not painful") == {})
    check("fever and chills: illness", f("woke up with a fever and chills")["illness"] == ["fever", "chills"])
    check("'sick of resting' isn't illness", "illness" not in f("sick of resting"))
    check("'constraint' isn't a strain", "muscle" not in f("the constraint is annoying"))
    check("a pulled hamstring: muscle", "muscle" in f("think I pulled my hamstring"))

    fl = journal.flags({"journal": "sharp pain in my shin", "feet": 3})
    check(f"words vs a low slider: a flag ({fl[0]['message']})", fl and fl[0]["kind"] == "bone" and "3/10" in fl[0]["message"])
    check("words that match a high slider: no flag - the slider already says it",
          journal.flags({"journal": "sharp pain in my shin", "feet": 7}) == [])
    sev = journal.flags({"journal": "my foot is swollen", "feet": 7})
    check("something serious flags whatever the slider", sev and sev[0]["severe"])
    better = journal.flags({"journal": "no pain at all, feel great", "feet": 7, "legs": 3})
    check(f"the other direction: 'feel great' with feet 7/10 ({better[0]['message'][:60]}...)", better and better[0]["kind"] == "better")
    check("...and not when the sliders agree", journal.flags({"journal": "feel great", "feet": 2, "legs": 2}) == [])

    # the lifecycle, through the real check-in
    d = coach.load(pathlib.Path(tempfile.mkdtemp()) / "coach.json")
    c = coach.record(d, "2026-10-01", {"legs": 3, "feet": 3, "journal": "sharp pain in my shin when I walk"})
    check(f"saving a check-in raises its flags ({[x['kind'] + ':' + x['status'] for x in c['flags']]})",
          [x["kind"] for x in c["flags"]] == ["bone"] and c["flags"][0]["status"] == "open")
    check("an open flag changes nothing", journal.effective(c)["feet"] == 3 and c["verdict"] == "go")
    journal.settle(c, "bone", "confirm", "t")
    check("confirmed: feet & bones read as 6/10", journal.effective(c)["feet"] == 6 and c["feet"] == 3)
    c = coach.record(d, "2026-10-01", {"sleep": 7})
    check("editing another field keeps it confirmed", c["flags"][0]["status"] == "confirmed")
    c = coach.record(d, "2026-10-01", {"journal": "sharp pain in my shin when I walk, and it's swollen now"})
    check("new words of that kind ask again", c["flags"][0]["status"] == "open")
    journal.settle(c, "bone", "dismiss", "t")
    check("dismissed: counts for nothing", journal.effective(c)["feet"] == 3)
    c = coach.record(d, "2026-10-01", {"journal": "all good today"})
    check("the words gone: the flag goes", "flags" not in c)
    try:
        journal.settle(c, "bone", "confirm"); check("settling a flag that isn't there is refused", False)
    except ValueError:
        check("settling a flag that isn't there is refused", True)

    c = coach.record(d, "2026-10-02", {"legs": 2, "gut": "go", "journal": "bit of a sore throat and a fever"})
    journal.settle(c, "illness", "confirm", "t")
    check(f"confirmed illness: the day goes easy ({coach.verdict(d, '2026-10-02')})", coach.verdict(d, "2026-10-02")[0] == "easy")
    st = {"systems": {x: {"acwr": 0.9, "tuned": True, "form": 0, "last7": 1, "prev7": 1} for x in ("engine", "impact", "muscle")},
          "days": [], "history_days": 30}
    st["systems"]["impact"]["tissue"] = None
    r = loads.readiness(st, c)
    check(f"...and heart & lungs easy in readiness ({r['systems']['engine']['why']})", r["systems"]["engine"]["level"] == "easy")
    c3 = coach.record(d, "2026-10-03", {"legs": 3, "feet": 2, "journal": "limping a bit after the stairs"})
    journal.settle(c3, "bone", "confirm", "t")
    r3 = loads.readiness(st, c3)
    check(f"confirmed bone flag: feet & bones read as 6/10 ({r3['systems']['impact']['level']}, {r3['systems']['impact']['why']})", r3["systems"]["impact"]["level"] == "easy")
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
