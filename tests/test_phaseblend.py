"""Phase blends, existing session planning and feedback policy; no athlete writes."""
import copy,datetime as dt,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import phaseblend as P,programming,progression,coach

class Blends(unittest.TestCase):
    def setUp(self):self.d={'plans':{},'checkins':{},'events':[]}
    def save(self,**kw):return P.save(self.d,{'start':'2026-10-05','weeks':4,'profile':'ride','kind':'base',**kw},'2026-10-02')
    def test_disabled_until_chosen_and_preserves_plans(self):
        self.assertFalse(P.resolve(self.d,'2026-10-05')['enabled'])
        coach.set_sessions(self.d,'2026-10-06',[{'sport':'swim','minutes':40}]);before=copy.deepcopy(self.d['plans'])
        self.save();self.assertEqual(self.d['plans'],before)
        self.assertFalse(P.resolve(self.d,'2026-10-04')['enabled']);self.assertFalse(P.resolve(self.d,'2026-11-02')['enabled'])
    def test_normal_blends_and_long_term_events(self):
        self.save(modes={'ride':'improve','swim':'improve','gym':'maintain','run':'maintain'})
        r=P.resolve(self.d,'2026-10-06');self.assertEqual(r['sports']['swim']['role'],'improve')
        self.assertAlmostEqual(sum(x['priority_share'] for x in r['sports'].values()),100,places=0)
        self.d['events']=[{'name':'Swim meet','sport':'swim','kind':'race','date':'2027-06-05'}]
        self.d['phase_profiles'][0]['modes']['swim']='maintain'
        r=P.resolve(self.d,'2026-10-06');self.assertEqual(r['sports']['swim']['role'],'prepare');self.assertTrue(r['sports']['swim']['can_progress'])
    def test_recovery_hold_and_pause_override_priorities(self):
        self.save();self.d['events']=[{'name':'Swim meet','sport':'swim','kind':'race','date':'2027-06-05'}]
        r=P.resolve(self.d,'2026-10-06',headline={'mechanical':{'remodeling_blocks':12.0,'block_limit':1.5}})
        self.assertEqual(r['sports']['run']['role'],'hold');self.assertEqual(r['sports']['run']['priority_share'],0)
        self.save(kind='recovery');r=P.resolve(self.d,'2026-10-06');self.assertFalse(any(x['can_progress'] for x in r['sports'].values()))
        self.save(modes={'ride':'improve','swim':'pause','gym':'maintain','run':'pause'})
        r=P.resolve(self.d,'2026-10-06');self.assertEqual(r['sports']['swim']['role'],'pause');self.assertTrue(any('gap' in w for w in r['sports']['swim']['why']))
    def test_rotation_and_validation(self):
        self.save();self.save(start='2026-11-02',profile='swim');self.assertEqual(P.resolve(self.d,'2026-11-03')['profile']['profile'],'swim')
        with self.assertRaises(ValueError):self.save(start='2026-10-15')
        with self.assertRaises(ValueError):self.save(weights={'ride':float('nan')})
        with self.assertRaises(ValueError):self.save(weeks=True)
        with self.assertRaises(ValueError):self.save(modes={'ride':'improve'})
    def test_advanced_priority_separate_from_actual_time(self):
        self.save(modes={'ride':'improve','swim':'improve','gym':'pause','run':'pause'},weights={'ride':60,'swim':40})
        coach.set_sessions(self.d,'2026-10-06',[{'sport':'swim','minutes':60}])
        coach.set_sessions(self.d,'2026-10-07',[{'sport':'ride','minutes':30}])
        r=P.resolve(self.d,'2026-10-06');w=P.week(self.d,'2026-10-06','2026-10-05')
        self.assertEqual(r['sports']['ride']['priority_share'],60);self.assertEqual(w['sports']['ride']['time_share'],33.3)
    def test_session_templates_and_progression_obey_maintenance(self):
        self.save(profile='gym',kind='build')
        r=programming.programming(self.d,{'experience':{'bike':'returning'}},'bike',dt.date(2026,10,6),{'verdict':'go'},capacities={'ftp':180})
        self.assertEqual(r['phase_blend']['sports']['ride']['role'],'maintain');self.assertIn(r['suggested_tier'],('easy','moderate'))
        c=progression.context(self.d,'2026-10-06','ride',{'name':'Aerobic ride'})
        self.assertEqual(c['purpose'],'maintain')
        self.assertEqual(progression.feedback(self.d,{'context':c,'effort':'too_easy'})['decision'],'purpose_met')
        r=programming.programming(self.d,{'experience':{'swim':'returning'}},'swim',dt.date(2026,10,6),{'swimming':{'verdict':'go'}},capacities={'swim_css':120})
        self.assertTrue(r['templates']);self.assertTrue(all(t['tier'] in ('easy','moderate') for t in r['templates']))
    def test_near_event_and_consolidation_protection(self):
        self.save();self.d['events']=[{'name':'Meet','sport':'swim','kind':'race','date':'2026-10-12'}]
        self.assertFalse(P.resolve(self.d,'2026-10-06')['sports']['swim']['can_progress'])
        self.d['events']=[];self.d['training_block']={'start':'2026-10-05','weeks':4,'progression':{'sport_phases':{'ride':'base'}}}
        self.save(kind='build');c=progression.context(self.d,'2026-10-28','ride',{'name':'Aerobic ride'})
        self.assertEqual(c['phase'],'recovery')

if __name__=='__main__':unittest.main()
