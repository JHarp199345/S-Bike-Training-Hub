"""One workout builder: typed rides carry cadence, watts/cadence/time goals are checked, the old page is gone,
and its starter rides live in the workout library."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import asyncio, json, shutil, subprocess
import mapserver, workouts, workout_library as wl

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    ok = True
    def check(n, c):
        nonlocal ok; c = bool(c); ok &= c; print(("PASS " if c else "FAIL ") + n)
    blocks = [{'type': 'steady', 'minutes': 5, 'watts': 100, 'section': 'warmup'},
              {'type': 'steady', 'minutes': 9, 'watts': 150, 'watts_low': 140, 'watts_high': 160, 'rpm_low': 85, 'rpm_high': 95, 'section': 'main'},
              {'type': 'steady', 'minutes': 3, 'watts': 100, 'rpm_low': 80, 'rpm_high': 80, 'section': 'main'}]
    steps = workouts.flatten(blocks)
    check("a typed stage's rpm range survives into the ride steps", steps[1]['rpm'] == 90 and (steps[1]['rpm_low'], steps[1]['rpm_high']) == (85, 95))
    try:
        workouts.flatten([{'type': 'steady', 'minutes': 5, 'watts': 100, 'rpm_low': 95, 'rpm_high': 85}]); check("reversed rpm refused", False)
    except workouts.BadWorkout:
        check("reversed rpm refused", True)
    session = {'sport': 'ride', 'ride_blocks': blocks}
    g = wl.clean_goals('ride', {'minutes': 17, 'power_low': 130, 'power_high': 145, 'cadence_low': 85, 'cadence_high': 92})
    r = wl.compare('ride', g, session)
    c = {x['metric']: x for x in r['checks']}
    check(f"average cadence of the main work is checked ({c['average_cadence']['calculated']} rpm in 85-92)", c['average_cadence']['matches'] is True)
    check(f"average watts checked alongside ({c['average_watts']['calculated']} W)", c['average_watts']['matches'] is True)
    r = wl.compare('ride', wl.clean_goals('ride', {'cadence_low': 85, 'cadence_high': 95}),
                   {'sport': 'ride', 'ride_blocks': [blocks[0], blocks[1], {'type': 'steady', 'minutes': 3, 'watts': 100, 'section': 'main'}]})
    check(f"recoveries without rpm don't block the check ({r['checks'][0]['calculated']} rpm; {r['checks'][0].get('note')})",
          r['checks'][0]['calculated'] == 90 and r['checks'][0]['matches'] is True)
    plain = {'sport': 'ride', 'ride_blocks': [{'type': 'steady', 'minutes': 20, 'watts': 150, 'section': 'main'}]}
    r = wl.compare('ride', wl.clean_goals('ride', {'cadence_low': 85, 'cadence_high': 95}), plain)
    check("no rpm written: the range is kept as the ride's cadence target, without forcing a review",
          r['checks'][0].get('note') and not r['requires_review'])
    for bad in ({'cadence_low': 85}, {'cadence_low': 95, 'cadence_high': 85}):
        try:
            wl.clean_goals('ride', bad); check(f"refuses {bad}", False)
        except ValueError:
            check(f"refuses {bad}", True)
    d = {'plans': {}}
    check("the 7 starter rides join the library once", wl.add_starter_rides(d, 200) == 7 and wl.add_starter_rides(d, 200) == 0
          and all(i['origin'] == 'starter' for i in d['workout_library'].values()))
    z2 = next(i['session'] for i in d['workout_library'].values() if i['session']['name'].startswith('Zone 2'))
    check(f"starters are written in watts at the athlete's FTP ({z2['typed_workout']['main']})", z2['typed_workout']['main'] == '40 minutes at 124 watts')
    code, _, _, extra = asyncio.run(mapserver.handle(None, b"GET", "/workouts", b"", "127.0.0.1"))
    check("the old builder page is gone: /workouts opens Write your workout", code == 302 and extra["Location"] == "/coach#write-ride")
    check("ride screens link to the one builder", '/coach#write-ride' in (ROOT / 'web/ride-hub.html').read_text() and '/coach#write-ride' in (ROOT / 'web/ride.html').read_text()
          and not (ROOT / 'web/workouts.html').exists())
    if shutil.which('node'):
        js = ("const P=require('./web/ride-parser.js');const r=P.parse({main:'3 x 9 minutes at 140-160 watts, 85-95 rpm with 3 minutes at 90-110 watts between intervals'},1);"
              "console.log(JSON.stringify([r.valid,r.blocks[0].rpm_low,r.blocks[0].rpm_high,r.blocks[1].rpm_low??null]))")
        out = json.loads(subprocess.run(['node', '-e', js], cwd=ROOT, capture_output=True, text=True).stdout)
        check(f"the form's parser reads '85-95 rpm' on the work, none on the recovery ({out})", out == [True, 85, 95, None])
    print("ALL PASS" if ok else "SOME FAILED"); return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
