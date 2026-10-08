"""Validated check-in instruments: Hooper (1-7) daily, pain by site (0-10), OSTRC weekly; Hub questions unchanged."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import wellness


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    c = wellness.clean_daily({"hooper_fatigue": 4, "hooper_sleep": 2, "hooper_stress": 3, "hooper_soreness": 5, "pain": {"feet": 3}, "legs": 6})
    check("Hooper items and pain are stored with the instrument version", c["hooper_fatigue"] == 4 and c["pain"] == {"feet": 3} and c["scale_version"] == "checkin-v2")
    check("the Hub's own leg soreness is not touched here", "legs" not in c)
    check("Hooper index = sum of all four (14)", wellness.hooper_index(c) == 14)
    check("no index unless all four are answered", wellness.hooper_index({"hooper_fatigue": 4}) is None)
    for bad in ({"hooper_sleep": 8}, {"hooper_sleep": 0}, {"pain": {"elbow": 3}}, {"pain": {"feet": 11}}, {"hooper_stress": 2.5}):
        try:
            wellness.clean_daily(bad); check(f"refuses {bad}", False)
        except ValueError:
            check(f"refuses {bad}", True)
    o = wellness.clean_ostrc([{"area": "lower_leg", "participation": 1, "volume": 2, "performance": 1, "pain": 1}])[0]
    check(f"OSTRC severity scored (8 + 13 + 6 + 8 = {o['severity']})", o["severity"] == 35)
    check("a moderate volume reduction is a substantial problem", o["substantial"])
    mild = wellness.clean_ostrc([{"area": "knee", "participation": 1, "volume": 1, "performance": 0, "pain": 1}])[0]
    check("mild problems are not substantial", not mild["substantial"] and mild["severity"] == 22)
    check("full score is 100", wellness.clean_ostrc([{"area": "foot", "participation": 3, "volume": 4, "performance": 4, "pain": 3}])[0]["severity"] == 100)

    import coach, weekly
    d = {"checkins": {}, "plans": {}}
    rec = coach.record(d, "2026-10-07", {"legs": 5, "feet": 4, "hooper_fatigue": 3, "hooper_sleep": 3, "hooper_stress": 2, "hooper_soreness": 4, "pain": {"legs": 2}})
    check("a saved check-in keeps leg/feet soreness and adds Hooper index and pain", rec["legs"] == 5 and rec["feet"] == 4 and rec["hooper_index"] == 12 and rec["pain"] == {"legs": 2})
    w = weekly.record(d, "2026-10-04", {"week": 5, "ostrc": [{"area": "lower_leg", "participation": 0, "volume": 0, "performance": 0, "pain": 1}]})
    check("the weekly check-in stores scored OSTRC entries", w["ostrc"][0]["severity"] == 8)
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
