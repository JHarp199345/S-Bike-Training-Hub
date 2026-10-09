"""Damaged optional history must not stop a ride or hide an older valid ghost."""
import pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ghost import Ghost

with tempfile.TemporaryDirectory() as temp:
    base = pathlib.Path(temp)
    (base/'ride_sample.csv').write_text('time,virtual_distance_m,grade_pct\n'+''.join(
        f'2026-10-08T09:00:{i:02d},{i*100},2\n' for i in range(15)))
    (base/'ride_sample_events.csv').write_text(
        'time,event\n2026-10-08T09:00:00,Route started: sample at 0 m - Sample\n'
        '2026-10-08T09:00:01\n'
        'bad date,Route started: sample at 0 m\n'
        '2026-10-08T09:00:02,Route started: sample at broken m\n'
        '2026-10-08T09:00:03,Route started: sample at nan m\n')
    g=Ghost(base);g.use_route('sample')
    assert g.match and g.match.name=='ride_sample' and g.match.length==1400
    g.use_route('other');assert g.match is None
print('PASS blank and malformed history rows do not block route starts; latest valid route ghost remains usable')
