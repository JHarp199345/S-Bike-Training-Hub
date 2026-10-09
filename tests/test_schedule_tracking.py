"""Preserve missed work; distinguish cancellation from target movement without athlete data."""
import copy, datetime as dt, json, sys, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import coach, schedule_tracking as T, training_block
DATE='2026-01-05'; NEXT='2026-01-06'
original={'sport':'ride','minutes':40,'name':'Endurance','steps':['40 min easy']}
d={'plans':{DATE:{'sessions':[original.copy()]}},'checkins':{}}
with patch.object(coach,'today',return_value=DATE):
 before=copy.deepcopy(d);T.capture(d,before)
 coach.session_action(d,DATE,0,'skip');T.capture(d,before)
 assert T.prescriptions(d,d['plans'][DATE])==T.prescriptions(before,before['plans'][DATE])
 assert not d['schedule_tracking']['revisions']
 assert coach.day(d,DATE)['plan']['sessions'][0]['sport']=='ride'
 assert coach.day(d,DATE)['plan']['sessions'][0]['minutes']==40
 assert d['plans'][DATE]['sessions'][0]['sport']=='rest' and d['plans'][DATE]['sessions'][0]['minutes']==0
 # Saving a presentation view cannot accidentally restore a cancelled workout's dose.
 coach.set_sessions(d,DATE,coach.day(d,DATE)['plan']['sessions']);assert d['plans'][DATE]['sessions'][0]['minutes']==0
with patch.object(coach,'today',return_value=NEXT):
 summary=T.summary(d,DATE,NEXT,{})
 assert summary['counts']['cancelled']==1 and summary['counts']['missed']==0
 assert summary['prescribed_minutes']==40 and summary['completion_share']==0
 assert summary['target_change_minutes']==0
 wk=coach.week(d,DATE,{})[0]
 assert wk['recovery_day'] and wk['sessions'][0]['sport']=='ride' and wk['sessions'][0]['skipped_id']
 assert not wk['sessions'][0].get('missed')
 # A different ride on a cancelled day remains additional actual work, not a completion of the skip.
 wk=coach.week(d,DATE,{DATE:[{'sport':'bike','minutes':45}]})[0]
 assert not wk['recovery_day'] and not wk['sessions'][0].get('completion')
 week=training_block._week(d,dt.date.fromisoformat(DATE),{})
 assert week['total_minutes']==40 and week['exposure_minutes']==0 and week['cancelled']==1
 assert week['days'][0]['workouts'][0]['sport']=='ride'
 assert not T.summary(d,DATE,NEXT,{},DATE)['sessions']  # today's workout never auto-missed
with patch.object(coach,'today',return_value=DATE):
 coach.session_action(d,DATE,0,'restore')
 before=copy.deepcopy(d);coach.set_sessions(d,DATE,[{**original,'minutes':30,'steps':['30 min easy']}]);T.capture(d,before)
 summary=T.summary(d,DATE,NEXT,{DATE:[{'sport':'bike','minutes':20}]},NEXT)
 assert summary['plan_revision_count']==1 and summary['target_change_minutes']==-10
 assert summary['counts']['partial']==1 and summary['matched_recorded_minutes']==20
 assert summary['initial_minutes']==40 and summary['prescribed_minutes']==30
 # The ordinary save boundary captures a change, including changes made outside set_sessions.
 with tempfile.TemporaryDirectory() as tmp:
  p=Path(tmp)/'coach.json';p.write_text(json.dumps(d));d['_path']=str(p)
  d['plans'][DATE]['sessions'][0]['minutes']=25;before_save=copy.deepcopy(d);coach.save(d)
  saved=json.loads(p.read_text());assert len(saved['schedule_tracking']['revisions'])==2
  assert d==before_save  # persistence never changes a reviewed in-memory snapshot
  coach.save(d);assert len(json.loads(p.read_text())['schedule_tracking']['revisions'])==2
  d['plans'][DATE]['sessions'][0]['minutes']=20;coach.save(d)
  assert len(json.loads(p.read_text())['schedule_tracking']['revisions'])==3  # stale caller ledger cannot erase history
# Skipping a second session must be allowed after reporting the first; deleting cannot shift it.
x={'plans':{DATE:{'sessions':[original.copy(),{'sport':'swim','minutes':20,'name':'Swim'}]}},'training_feedback':{DATE+':0':{}},'checkins':{}}
with patch.object(coach,'today',return_value=DATE):
 coach.session_action(x,DATE,1,'skip')
 try:coach.session_action(x,DATE,1,'delete');raise AssertionError('shifted recorded indices')
 except ValueError:pass
print('PASS cancellation and revisions stay separate, original icons/targets, no phantom dose/completion, recovery record, partials, immutable baseline and normal save audit')


def test_untrainable_sessions_do_not_look_like_plan_changes():
    """A session that doesn't count toward adherence (e.g. 'other' or rest) must not appear as a target change."""
    import coach, schedule_tracking
    other = next(s for s in ('other', 'mobility', 'walk') if s not in coach.TRAINABLE) if any(s not in coach.TRAINABLE for s in ('other', 'mobility', 'walk')) else None
    if other is None:
        return
    d = {'plans': {'2026-10-01': {'sessions': [{'sport': 'ride', 'minutes': 30, 'name': 'Ride'},
                                               {'sport': other, 'minutes': 25, 'name': 'Extra'}]}}}
    s = schedule_tracking.summary(d, '2026-10-01', '2026-10-02', {}, as_of='2026-10-03')
    assert s['initial_minutes'] == s['prescribed_minutes'] == 30 and s['target_change_minutes'] == 0, s


if __name__ == '__main__':
    test_untrainable_sessions_do_not_look_like_plan_changes()
    print('PASS untrainable sessions are not counted as a plan change')
