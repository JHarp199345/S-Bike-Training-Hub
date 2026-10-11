import unittest,copy
import exercise_tracking as tracking
class TrackingTest(unittest.TestCase):
 def test_saved_names_do_not_change_workouts(self):
  d={'plans':{'2026-10-11':{'sessions':[{'name':'Swim'}]}},'checkins':{'x':1}};before=copy.deepcopy(d)
  result=tracking.save(d,['hip thruster','hip thrust','lat pull down','chest press','bench press','dumbbell bench press'])
  self.assertEqual([x['key'] for x in result],['hip thrust','lat pulldown','machine chest press','barbell bench press','dumbbell bench press'])
  self.assertEqual(d['plans'],before['plans']);self.assertEqual(d['checkins'],before['checkins'])
 def test_invalid_and_empty(self):
  for value in (None,{},[''],['a'*81],['x']*51):
   with self.assertRaises(ValueError):tracking.save({},value)
  self.assertEqual(tracking.save({},[]),[])
if __name__=='__main__':unittest.main()
