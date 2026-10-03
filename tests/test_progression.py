"""Contextual decisions and real forecast integration; no athlete data writes."""
import copy,datetime as dt,pathlib,sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
import progression as P,training_block as B,coach


def seed():
    d={'plans':{},'checkins':{'2026-10-07':{'legs':2,'shoulders':2,'breathing':2}},'events':[],
       'training_block':{'start':'2026-10-05','weeks':4,'status':'active','reviews':{}}}
    for date in ['2026-10-06','2026-10-09','2026-10-16']:
        coach.set_sessions(d,date,[{'sport':'swim','name':'Easy aerobic swim','minutes':40,'steps':['5 min easy warm-up','30 min comfortable aerobic swimming','5 min easy cool-down']}])
    P.enable(d)
    e=P.report(d,'2026-10-06',0,{'effort':'too_easy'},{'2026-10-06':[{'sport':'swim','minutes':40}]},'2026-10-07')
    return d,e


def forecast(d,today,dates,*args):
    total=sum(s['minutes'] for p in d['plans'].values() for s in B.sessions(p) if s['sport']=='swim')
    return {day:{'metrics':[{'key':k,'after':v,'name':k,'limit':1.5 if k in ('swim_recovery','strength') else None} for k,v in
        [('cardio_fatigue',20+total/100),('cardio_conditioning',15),('muscle_fatigue',1+total/1000),('run_mechanical',12.0),('run_recent',0),('swim_recovery',total/1000),('strength',.1)]],
        'regional_overlap':{'regions':{},'unavailable_sources':[]}} for day in dates}


class Decisions(unittest.TestCase):
    def setUp(self):
        self.d,self.e=seed();self.load={'systems':{k:{'fitness':2,'fatigue':5,'form':0,'acwr':None,'usual_week':30,'last7':20,'prev7':20} for k in ('engine','impact','muscle')},'history_days':3,'days':[],'headline':{'mechanical':{'remodeling_blocks':12.0,'block_limit':1.5}}}

    def compare(self,d=None,e=None):
        with patch.object(B,'projected_loads',side_effect=forecast):
            return P.compare(d or self.d,'2026-10-07','2026-10-09',0,self.load,{},trigger=e or self.e)

    def test_lifting_regressions_preserve_unaffected_work(self):
        session={'sport':'gym','name':'Strength','minutes':25,'lifts':[
            {'name':'Calf raise','kind':'bodyweight','sets':2,'reps':10,'regions':{'calves':1}},
            {'name':'Row','kind':'machine','sets':2,'reps':10,'regions':{'lats':1}}]}
        x=P._lifting_regression(session,[{'regions':['calves']}])
        self.assertEqual([l['name'] for l in x['lifts']],['Row'])
        self.assertEqual(session['lifts'][0]['sets'],2)
        x=P._lifting_regression(session,[])
        self.assertEqual([l['sets'] for l in x['lifts']],[1,1])
        session['lifts'][0]['regions']={}
        self.assertIsNone(P._lifting_regression(session,[]))

    def test_context(self):
        self.assertEqual(P.feedback(self.d,self.e)['decision'],'progression_candidate')
        self.d['events']=[{'kind':'race','date':'2026-10-11','name':'Race','sport':'run'}]
        e={**self.e,'context':P.context(self.d,'2026-10-06','swim')}
        self.assertEqual(P.feedback(self.d,e)['decision'],'purpose_met')
        x=self.compare();self.assertNotEqual(x['selected'],'extend')
        self.d['events']=[];self.d['training_block']['progression']['sport_phases']['swim']='recovery'
        self.assertNotEqual(self.compare()['selected'],'extend')

    def test_delayed_response_bound_manual_edits_and_idempotence(self):
        # Small synthetic week needs an explicit larger bound for this test; production uses 5%.
        self.d['training_block']['progression']['max_weekly_fraction']=.2
        x=self.compare();self.assertEqual(x['selected'],'extend');x['trigger']=self.e
        before=copy.deepcopy(self.d['plans'])
        with patch.object(B,'projected_loads',side_effect=forecast):
            P.apply(self.d,x,'2026-10-07',self.load,{})
        self.assertEqual(self.d['plans']['2026-10-09']['sessions'][0]['minutes'],45)
        self.assertEqual(self.d['plans']['2026-10-09']['sessions'][0]['steps'][1],'35 min comfortable aerobic swimming')
        self.assertEqual(self.d['plans']['2026-10-16'],before['2026-10-16'])
        with patch.object(B,'projected_loads',side_effect=forecast):
            self.assertRaises(ValueError,P.apply,self.d,x,'2026-10-07',self.load,{})
        d,e=seed();d['checkins'].clear();self.assertNotEqual(self.compare(d,e)['selected'],'extend')

    def test_pain_overrides_easy_without_changing_running_curve(self):
        self.d['training_feedback']['2026-10-06:0']['symptoms']=[{'location':'achilles','side':'left','severity':2,'regions':['calves']}]
        before=copy.deepcopy(self.load)
        x=self.compare();self.assertEqual(x['selected'],'unload');self.assertEqual(self.load,before)
        self.assertFalse(next(c for c in x['candidates'] if c['action']=='keep')['eligible'])
        self.d.setdefault('progression_symptom_reviews',{})['2026-10-06:0']={'date':'2026-10-07'}
        self.assertEqual(P.active_symptoms(self.d,'2026-10-07'),[])

    def test_future_overlap_and_unknowns_block_increase(self):
        self.d['training_block']['progression']['max_weekly_fraction']=.2
        def overlap(*args):
            out=forecast(*args)
            for f in out.values():f['regional_overlap']['regions']={'shoulders':{'name':'shoulders','shared':True,'overlap_index':1.2,'active_sources':['swim','lifting']}}
            return out
        with patch.object(B,'projected_loads',side_effect=overlap):
            x=P.compare(self.d,'2026-10-07','2026-10-09',0,self.load,{},trigger=self.e)
        self.assertNotEqual(x['selected'],'extend')
        def unknown(*args):
            out=forecast(*args)
            for f in out.values():
                for m in f['metrics']:
                    if m['key']=='muscle_fatigue':m['after']=None
            return out
        with patch.object(B,'projected_loads',side_effect=unknown):
            x=P.compare(self.d,'2026-10-07','2026-10-09',0,self.load,{},trigger=self.e)
        self.assertNotEqual(x['selected'],'extend')

    def test_running_gate_and_no_added_frequency(self):
        coach.set_sessions(self.d,'2026-10-09',[{'sport':'run','minutes':10,'name':'Easy run'}])
        before=set(self.d['plans']);x=self.compare()
        self.assertEqual(x['selected'],'unload');self.assertEqual(set(self.d['plans']),before)
        self.assertNotIn('extend',[c['action'] for c in x['candidates']])

    def test_hr_baseline_regression_and_validation(self):
        self.d['checkins'].update({f'2026-10-0{i}':{'hr90':110} for i in (3,4,5)})
        self.d['checkins']['2026-10-07']['hr90']=125
        self.assertEqual(self.compare()['selected'],'shorter')
        self.assertRaises(ValueError,P.report,self.d,'2026-10-16',0,{'effort':'too_easy'},{},'2026-10-07')
        self.assertRaises(ValueError,P.report,self.d,'2026-10-06',0,{'effort':'too_easy','symptoms':[{'location':'calf_belly','side':'left','severity':-1}]},{'2026-10-06':[{'sport':'swim','minutes':40}]},'2026-10-07')

    def test_real_forecast_detects_unprescribed_strength(self):
        self.d['training_block']['progression']['max_weekly_fraction']=.2
        coach.set_sessions(self.d,'2026-10-08',[{'sport':'gym','minutes':25,'name':'Unknown lifts'}])
        load={'systems':{k:{'fitness':2,'fatigue':3,'form':0,'acwr':None,'usual_week':30,'last7':20,'prev7':20} for k in ('engine','impact','muscle')},
              'activities':[{'date':'2026-10-06','sport':'swim','minutes':40,'engine':20,'impact':0,'muscle':2,'swim_exposure':{'units':200,'by_stroke':{'freestyle':200}}}],
              'swim_recovery':{'score':.2,'threshold_blocks':1.5,'recent':.1,'history_component':.1,'reference_units':1000},'profile':{'ftp':180},'history_days':3,'days':[]}
        x=P.compare(self.d,'2026-10-07','2026-10-09',0,load,{},trigger=self.e)
        c=next(c for c in x['candidates'] if c['action']=='extend')
        self.assertFalse(c['eligible']);self.assertTrue(any('Unknown dose' in r for r in c['reasons']))

if __name__=='__main__':unittest.main()
