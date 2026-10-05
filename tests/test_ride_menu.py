"""Shared ride entry points and load-aware, read-only library choices."""
import asyncio, copy, csv, json, pathlib, sys, tempfile, unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import coach, mapserver, ride_library, workouts

class RideMenuTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name); (self.base / 'rides').mkdir()
        self.bridge = SimpleNamespace(csv_path=self.base/'rides'/'scratch.csv', profile={'ftp':180}, status=lambda:{'bike':True})

    def test_all_renderer_entry_points_use_shared_screen(self):
        for url, target in [('/ride/map','map'),('/ride/game?scene=pixel','pixel'),('/ride/game?scene=haunted','haunted'),('/course','game')]:
            result = asyncio.run(mapserver.handle(self.bridge,b'GET',url,b'', 'localhost'))
            self.assertEqual(result[0],302); self.assertEqual(result[3]['Location'],'/ride?view='+target)
        result=asyncio.run(mapserver.handle(self.bridge,b'GET','/ride/map?embedded=1',b'', 'localhost'))
        self.assertEqual(result[0],200); self.assertIn(b'hub-map-controls',result[2])

    def test_menu_is_read_only_and_matches_load_not_creation_order(self):
        date=coach.today(); data=coach.load(self.base/'coach.json')
        coach.set_sessions(data,date,[{'sport':'ride','minutes':30,'name':'Today ride','workout':'scheduled','bike_plan':{'power_steps':[{'minutes':30,'watts':120}]}}]); coach.save(data)
        before=(self.base/'coach.json').read_bytes()
        stats=lambda minutes,watts:workouts.stats([{'minutes':minutes,'watts':watts}],180)
        saved=[{'id':'hard','name':'Hard','stats':stats(60,220)},{'id':'matched','name':'Matched','stats':stats(30,120)},{'id':'scheduled','name':'Today ride','stats':stats(10,90)}]
        with patch.object(workouts,'list_all',return_value=copy.deepcopy(saved)),patch('routes.list_routes',return_value=[]),patch.object(mapserver,'load_state',return_value={}),patch.object(mapserver,'done_by_day',return_value={}):
            result=ride_library.listing(self.bridge)
        self.assertEqual([w['id'] for w in result['workouts']],['scheduled','matched','hard'])
        self.assertFalse(result['guidance']['review_required']); self.assertIn('Log rides',result['guidance']['warning'])
        self.assertEqual((self.base/'coach.json').read_bytes(),before)
        self.assertEqual(list(self.base.glob('*.json')),[self.base/'coach.json'])

    def test_history_marks_starts_without_inventing_completions(self):
        file=self.base/'rides'/'ride_2026-10-01_events.csv'
        with file.open('w') as f:
            w=csv.DictWriter(f,fieldnames=['time','event']);w.writeheader()
            w.writerows([{'time':'2026-10-01T12:00:00','event':'Workout started: Easy (at FTP 180 W)'},{'time':'2026-10-01T12:01:00','event':'Route started: forest at 0 km'},{'time':'2026-10-01T12:02:00','event':'Unrelated event'}])
        self.assertEqual(ride_library.recent_use(self.base),{('workout','Easy'):'2026-10-01',('route','forest'):'2026-10-01'})

    def test_launch_rechecks_readiness_and_active_ride(self):
        async def call(req):return await mapserver.handle(self.bridge,b'POST','/api/ride/menu/start',json.dumps(req).encode(),'localhost')
        req={'kind':'workout','id':'easy'}
        self.bridge.status=lambda:{'bike':False};self.assertEqual(asyncio.run(call(req))[0],409)
        self.bridge.status=lambda:{'bike':True,'workout':{'name':'Already active'}};self.assertEqual(asyncio.run(call(req))[0],409)
        self.bridge.status=lambda:{'bike':True}
        listing={'guidance':{'not_ready':True},'workouts':[{'id':'easy'}],'routes':[]}
        with patch.object(ride_library,'listing',return_value=listing):self.assertEqual(asyncio.run(call(req))[0],409)
        listing['guidance']={'review_required':True}
        with patch.object(ride_library,'listing',return_value=listing):self.assertEqual(asyncio.run(call(req))[0],409)
        listing['guidance']={}
        with patch.object(ride_library,'listing',return_value=listing):self.assertEqual(asyncio.run(call(dict(req,id='missing')))[0],404)
        with patch.object(ride_library,'listing',return_value=listing),patch.object(self.bridge,'status',side_effect=[{'bike':True},{'bike':True,'route':{'name':'Concurrent ride'}}]):
            self.assertEqual(asyncio.run(call(req))[0],409)

if __name__=='__main__':unittest.main()
