"""Workout builder: blocks flatten into ERG steps, stats are right, files save,
rename-safe ids, bad input refused, old workouts open as blocks."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import json, tempfile
import workouts as W
from erg import load_workouts


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    s = W.flatten([{"type": "steady", "minutes": 10, "pct": 50}])
    check("a steady block is one step", s == [{"minutes": 10, "pct": 50}])
    r = W.flatten([{"type": "ramp", "minutes": 10, "from": 40, "to": 80}])
    check(f"a 10-min ramp is twenty 30-s steps climbing 40->80% ({len(r)} steps, {r[0]['pct']}..{r[-1]['pct']})",
          len(r) == 20 and r[0]["pct"] == 41 and r[-1]["pct"] == 79 and all(a["pct"] < b["pct"] for a, b in zip(r, r[1:])))
    iv = W.flatten([{"type": "intervals", "times": 5, "on": {"minutes": 3, "pct": 112}, "off": {"minutes": 3, "pct": 50}}])
    check(f"5x3 intervals: 5 on, 4 easy between ({len(iv)} steps)", len(iv) == 9 and [x["pct"] for x in iv[:3]] == [112, 50, 112])
    m = W.flatten([{"type": "steady", "minutes": 5, "pct": 60}, {"type": "steady", "minutes": 5, "pct": 60}])
    check("same-intensity neighbours merge into one step", m == [{"minutes": 10, "pct": 60}])
    thirty = W.flatten([{"type": "intervals", "times": 2, "on": {"minutes": 0.5, "pct": 150}, "off": {"minutes": 0.5, "pct": 50}}])
    check("30-second intervals work", thirty[0]["minutes"] == 0.5)
    for bad, why in (([], "empty"), ([{"type": "steady", "minutes": 10, "pct": 900}], "900%"),
                     ([{"type": "steady", "minutes": "x", "pct": 60}], "non-number"), ([{"type": "sprint"}], "unknown kind"),
                     ([{"type": "steady", "minutes": 300, "pct": 60}, {"type": "steady", "minutes": 100, "pct": 50}], "over 6 h")):
        try:
            W.flatten(bad); check(f"refuses {why}", False)
        except W.BadWorkout as e:
            check(f"refuses {why}: \"{e}\"", True)
    st = W.stats([{"minutes": 60, "pct": 100}], 200)
    check(f"an hour at FTP: load 100, IF 1.00 ({st['tss']}, {st['if']})", st["tss"] == 100 and st["if"] == 1.0)
    st = W.stats(W.flatten([{"type": "steady", "minutes": 60, "pct": 62}]), 180)
    check(f"an hour of zone 2 at 62%: load ~38, ~{st['kcal']} kcal", st["tss"] == 38 and 390 < st["kcal"] < 410)

    d = pathlib.Path(tempfile.mkdtemp())
    (d / "old.json").write_text(json.dumps({"name": "Old one", "steps": [{"minutes": 10, "pct": 47}, {"minutes": 25, "pct": 61}]}))
    lst = W.list_all(180, d)
    check("an old steps-only workout opens as steady blocks", lst[0]["blocks"][1] == {"type": "steady", "minutes": 25, "pct": 61})
    wid = W.save({"name": "Sweet spot 3x10", "blocks": [{"type": "steady", "minutes": 10, "pct": 50}]}, d)
    wid2 = W.save({"name": "Sweet spot 3x10", "blocks": [{"type": "steady", "minutes": 10, "pct": 55}]}, d)
    check(f"ids come from the name, and a second with the same name gets its own ({wid}, {wid2})", wid == "sweet-spot-3x10" and wid2 == "sweet-spot-3x10-2")
    W.save({"id": wid, "name": "Renamed", "blocks": [{"type": "steady", "minutes": 12, "pct": 50}]}, d)
    saved = json.loads((d / f"{wid}.json").read_text())
    check("saving an existing one keeps its file (rename-safe)", saved["name"] == "Renamed" and saved["steps"][0]["minutes"] == 12)
    check("the ERG engine can load what the builder wrote", {w["id"] for w in load_workouts(d)} == {"old", wid, wid2})
    for bad in ("../profile", "a/b", ""):
        try:
            W.delete(bad, d); check(f"delete refuses {bad!r}", False)
        except W.BadWorkout:
            check(f"delete refuses {bad!r}", True)
    try:
        W.save({"id": "../../x", "name": "Sneaky", "blocks": [{"type": "steady", "minutes": 1, "pct": 50}]}, d)
        check("a made-up id can't write outside the folder", not (d.parent / "x.json").exists() and (d / "sneaky.json").exists())
    except W.BadWorkout:
        check("a made-up id is refused", True)
    W.delete(wid2, d)
    check("delete removes the file", not (d / f"{wid2}.json").exists())
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
