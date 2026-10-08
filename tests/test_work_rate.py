import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import copy
import unittest
import work_rate as wr


class WorkRateTests(unittest.TestCase):
    def test_duration_weighting_rest_and_missing_are_distinct(self):
        activities = [dict(id='a',date='2026-10-05',sport='run',source='fit',minutes=10,calories_kcal=100,engine=10,impact=20,muscle=5),
                      dict(id='b',date='2026-10-06',sport='swim',source='fit',minutes=30,calories_kcal=200,engine=15,muscle=3),
                      dict(id='opening',date='2026-10-05',sport='bike',source='tcx',minutes=7,calories_kcal=None,muscle=4)]
        result = wr.build({'activities':activities},today='2026-10-07')
        c = result['windows']['3']['cardio']
        self.assertEqual(c['j_per_min'],300*4184/40)
        self.assertEqual(c['j_per_day'],100*4184)
        self.assertFalse(c['complete'])
        self.assertEqual(c['missing_ids'],['opening'])
        self.assertEqual(result['daily'][-1]['cardio']['recorded_sessions'],0)
        self.assertEqual(result['windows']['28']['cardio']['j_per_day'],300*4184/28)
        self.assertIsNone(result['response_band'])

    def test_lifting_variable_sets_units_sides_and_exclusions(self):
        log={'date':'2026-10-06','minutes':23,'session':'Gym','lifts':[
            dict(name='Pulldown',weight=100,unit='lb',sets=3,reps=10,hold=6,tempo='3-0-3'),
            dict(name='Row',weight=10,unit='kg',per_side=True,set_details=[{'reps':4},{'reps':5,'weight':20},{'done':False,'reps':50}]),
            dict(name='Hold',weight=20,unit='lb',sets=2,seconds=40),
            dict(name='Magnetic sled',weight=None,sets=3,seconds=90)]}
        original=copy.deepcopy(log);result=wr.lift_work(log)
        self.assertAlmostEqual(result['volume_kg'],3000*wr.KG_PER_LB+280)
        self.assertEqual(len(result['sets']),5)
        self.assertEqual(len(result['excluded']),5)
        log['lifts'][0].update(hold=50,tempo='9-9-9')
        self.assertEqual(wr.lift_work(log)['work_j'],result['work_j'])
        self.assertEqual(original['lifts'][0]['hold'],6)

    def test_linked_timer_and_report_context_no_fatigue(self):
        load={'activities':[dict(id='gym',date='2026-10-06',sport='gym',source='fit',minutes=23.2,duration_seconds=1393,calories_kcal=242,muscle=10)]}
        log={'date':'2026-10-06','minutes':23,'session':'Gym','source_activity_id':'gym','regions':{'lats':20},'lifts':[dict(name='Lat',weight=100,unit='lb',reps=10,sets=3)]}
        before=copy.deepcopy((load,log))
        result=wr.build(load,[log],{'2026-10-07':{'legs':4}},today='2026-10-07')
        self.assertAlmostEqual(result['lifts'][0]['minutes'],1393/60)
        self.assertEqual(result['windows']['3']['cardio']['known_j'],242*4184)
        self.assertEqual(result['reports'][0]['readings'],{'legs':4})
        self.assertEqual(result['daily'][-2]['regions']['lats']['sources']['lift'],20)
        self.assertNotIn('fatigue',result)
        self.assertEqual((load,log),before)


if __name__ == '__main__':unittest.main()
