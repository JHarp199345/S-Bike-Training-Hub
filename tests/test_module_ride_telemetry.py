"""The race gets live readings and a bounded clock, never a workout/history dump."""
import unittest,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import module_sandbox as sandbox
class RideTelemetryTest(unittest.TestCase):
    def setUp(self):
        self.raw={'power':135,'heart_rate':142,'bike':True,'workout':{'name':'PRIVATE','steps':[[60,150]],'elapsed':75.5,'total':1800,'paused':True,'auto_paused':False,'history':'PRIVATE'},'reports':'PRIVATE'}
        self.bridge=SimpleNamespace(status=lambda:self.raw)
    def test_minimal_explicit_clock_and_hr(self):
        got=sandbox.telemetry(self.bridge,['heart_rate','workout'])
        self.assertEqual(got,{'heart_rate':142,'workout':{'elapsed':75.5,'total':1800,'paused':True,'auto_paused':False},'bike':True,'no_bike':False})
        self.assertIn('name',self.raw['workout'])
    def test_undeclared_fields_and_history_stay_private(self):
        got=sandbox.telemetry(self.bridge,['power'])
        self.assertEqual(got,{'power':135,'bike':True,'no_bike':False})
    def test_bad_clock_and_heart_rate_are_not_forwarded(self):
        for value in [True,float('nan'),float('inf'),'142']:
            self.raw['heart_rate']=value
            self.assertNotIn('heart_rate',sandbox.telemetry(self.bridge,['heart_rate']))
        for value in [True,-1,float('nan'),'75']:
            self.raw['workout']['elapsed']=value
            self.assertNotIn('workout',sandbox.telemetry(self.bridge,['workout']))
    def test_workout_permission_is_accepted_but_unknown_scope_is_not(self):
        self.assertEqual(sandbox.permissions({'permissions':{'telemetry':['heart_rate','workout'],'controls':['lean']}})['fields'],['heart_rate','workout'])
        with self.assertRaises(ValueError):sandbox.permissions({'permissions':{'telemetry':['history'],'controls':[]}})
if __name__=='__main__':unittest.main()
