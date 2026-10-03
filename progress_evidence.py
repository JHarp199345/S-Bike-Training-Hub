"""Evidence for progress, shared by the UI and external coaching assistants.
Training load is exposure, not a measured fitness outcome. No clearance decisions.
"""
def report(state):
    indicators=[]
    def add(name,direction,reading,basis,confidence='limited'):
        indicators.append(dict(name=name,direction=direction,reading=reading,basis=basis,confidence=confidence))
    aerobic=state.get('aerobic') or {}
    rides=aerobic.get('rides') or []
    trend=(aerobic.get('trend') or {}).get('hr_at_band')
    if trend and trend.get('rides',0)>=3:
        delta=round(trend['latest']-trend['first'],1)
        add('Cycling efficiency','improving signal' if delta<0 else 'declining signal' if delta>0 else 'stable',f"{delta:+g} bpm at 100–120 W; latest {trend['latest']} bpm",f"{trend['rides']} rides, {rides[0]['date']}–{rides[-1]['date']}; temperature, cadence and fatigue can affect comparison")
    else:
        add('Cycling efficiency','not established','Need at least three rides with heart rate in the same power band','Comparable effort data; workload averages are not performance tests','insufficient')
    days=[d for d in state.get('days',[]) if (d.get('engine') or {}).get('fitness') is not None]
    if len(days)>=8:
        first,last=days[-8],days[-1];delta=round(last['engine']['fitness']-first['engine']['fitness'],2)
        add('Modeled cardio conditioning','model rising' if delta>0 else 'model falling' if delta<0 else 'model stable',f"{delta:+g} load points",f"{first['date']}–{last['date']}; training-exposure model, not a measured performance gain",'model estimate')
    recovery=((state.get('insights') or {}).get('ride') or {}).get('recovery') or {}
    if recovery.get('latest') is not None and recovery.get('usual') is not None:
        delta=round(recovery['latest']-recovery['usual'],1)
        add('Heart-rate recovery','improving signal' if delta>0 else 'declining signal' if delta<0 else 'stable',f"{delta:+g} bpm vs usual one-minute drop",'Post-effort recovery; compare similar efforts and recovery conditions')
    else:add('Recovery capacity','not established','More comparable post-workout observations needed','Feeling refreshed is useful context; it does not alone establish increased capacity','insufficient')
    add('Running progress','readiness remains governed by load and check-ins','No improvement inferred from absence of running','Mechanical recovery model and return-to-running gates remain authoritative','not rated')
    add('Swim and strength performance','comparison needed','Review matched swim sets and repeated lifts before labeling gains','Stroke, pace, equipment, lift technique, repetitions and effort must be comparable','insufficient')
    return {'indicators':indicators,'interpretation':'Falling load can reflect recovery or reduced exposure. Rising load can reflect more work. Neither alone proves fitness gains. Coaching adjustments must also respect the phase, event timing and regional load limits.','version':1}
