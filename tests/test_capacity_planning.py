"""Capacity evidence stays separate from predictions and recovery clearance."""
import copy
import pathlib
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import capacity_planning as C
import program_builder as B
import mcp_server


class CapacityTests(unittest.TestCase):
    def test_running_units_and_missing_mass(self):
        goal = C.goals([{'sport': 'run', 'distance_m': 5000, 'duration_min': 25}])[0]
        result = C.demand(goal, {'weight_kg': 264 * .45359237})
        self.assertEqual(result['pace_seconds_per_km'], 300)
        self.assertEqual(result['oxygen_cost_ml_kg_min'], 43.5)
        self.assertAlmostEqual(result['energy']['gross_kcal'], 651.1, delta=.2)
        self.assertEqual(result['mechanical']['estimated_steps'], 3750)
        self.assertIsNone(C.demand(goal, {})['energy'])
        # A label such as experienced does not grant energy savings.
        self.assertEqual(result['energy'], C.demand(goal, {'weight_kg': 264 * .45359237, 'experience': {'run': 'experienced'}})['energy'])

    def test_power_work_and_strength_not_calories(self):
        ride = C.demand(C.goals([{'sport': 'ride', 'duration_min': 60, 'power_w': 100}])[0], {})
        self.assertEqual(ride['energy']['mechanical_kj'], 360)
        gym = C.demand(C.goals([{'sport': 'gym', 'weight_kg': 50, 'reps': 10, 'sets': 3}])[0], {})
        self.assertEqual(gym['mechanical']['external_volume_kg'], 1500)
        self.assertIsNone(gym['energy'])

    def test_not_splicing_short_speed_and_long_distance(self):
        d = {'program_goal': {'capacity_demands': [{'sport':'run','distance_m':5000,'duration_min':25}]}}
        load = {'profile': {'weight_kg': 80}, 'activities': [
            {'sport':'run','date':'2026-10-01','minutes':5,'distance_m':1200},
            {'sport':'run','date':'2026-10-02','minutes':35,'distance_m':5000},
            {'sport':'run','date':'2026-10-10','minutes':20,'distance_m':5000}]}
        before = copy.deepcopy((d, load))
        result = C.review(d, load, '2026-10-05')['demands'][0]
        self.assertEqual(result['matching_efforts'], [])
        self.assertEqual(result['observed']['sessions'], 2)
        self.assertEqual(result['exposure_gaps']['distance_m'], 0)
        self.assertEqual((d, load), before)
        load['activities'].append({'sport':'run','date':'2026-10-04','minutes':24,'distance_m':5000})
        result = C.review(d, load, '2026-10-05')['demands'][0]
        self.assertEqual(len(result['matching_efforts']), 1)
        self.assertIn('Unconfirmed', result['tolerance'])

    def test_unknown_is_not_zero_and_validation(self):
        out = C.review({}, {}, '2026-10-05', [{'sport':'swim','distance_m':50,'duration_min':.5}])['demands'][0]
        self.assertIsNone(out['exposure_gaps']['distance_m'])
        for bad in (True, float('nan'), -2, float('inf')):
            with self.assertRaises(ValueError): C.goals([{'sport':'run','duration_min':bad}])
        with self.assertRaises(ValueError):C.goals([{'sport':'run','duration_min':25,'power_w':300}])
        with self.assertRaises(ValueError):C.goals([{'sport':'run','duration_min':25,'grade':-.02}])

    def test_energy_trend_requires_explicit_delayed_reports(self):
        d={'training_feedback':{},'capacity_followups':{}}
        acts=[]
        for date,kcal in [('2026-08-28',500),('2026-08-30',500),('2026-09-02',500),('2026-09-22',700),('2026-09-24',700),('2026-09-26',700)]:
            acts.append({'sport':'bike','date':date,'minutes':60,'calories_kcal':kcal,'calories_basis':'same-device-total','source':'watch'})
            d['training_feedback'][date+':0']={'date':date,'sport':'ride','session_index':0,'rpe':6,'effort':'as_intended','symptoms':[]}
        load={'activities':acts}
        view=lambda:C.tolerance_trends(d,load,'2026-10-05')[1]
        self.assertEqual(view()['signal'],'insufficient evidence')
        for a in acts:d['capacity_followups'][a['date']+':0']={'recovery':'good'}
        self.assertEqual(view()['signal'],'improving tolerance signal')
        d['capacity_followups']['2026-09-26:0']['recovery']='difficult'
        self.assertEqual(view()['signal'],'recovery concern')
        d['capacity_followups']['2026-09-26:0']['recovery']='good'
        acts[-1]['calories_basis']='different-device'
        self.assertEqual(view()['signal'],'insufficient evidence')
        for a in acts:a['calories_basis']='same-device-total'
        for a in acts[-3:]:a['calories_kcal']=300
        self.assertEqual(view()['signal'],'no clear change')

    def test_preview_carries_goal_without_clearing_hold(self):
        d = {'plans': {}, 'phase_profiles': []}
        f = {'start':'2026-10-05','horizon_days':42,'sport':'run','hours':4,
             'capacity_demands':[{'sport':'run','distance_m':5000,'duration_min':25}]}
        before = copy.deepcopy(d)
        proposal = B.propose(d, f, '2026-10-05', {'status':'hold'})
        self.assertEqual(d, before)
        self.assertTrue(proposal['running_hold'])
        self.assertFalse(any(s['sport']=='run' for w in proposal['weeks'] for s in w['slots']))
        B.accept(d, proposal)
        self.assertEqual(d['program_goal']['capacity_demands'][0]['distance_m'], 5000)
        tools = {t['name']:t for t in mcp_server.handle({'id':1,'method':'tools/list'})['tools']}
        self.assertTrue(tools['get_capacity_review']['annotations']['readOnlyHint'])


if __name__ == '__main__': unittest.main()
