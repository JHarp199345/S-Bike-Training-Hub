"""Reviewed swim prescriptions; never confuse send-off intervals with fixed rest."""
import copy, math, re
UNIT=r'(?:yds?|yards?|meters?|metres?|m)'
HEAD=re.compile(r'^(warm[ -]?up|pre[ -]?set(?:\s*/\s*drill)?|drills?|main (?:set|work(?:out)?)(?:\s+[A-Z0-9]+)?|cool[ -]?down)\b',re.I)
NAMES={'warmup':'Warm-up','main':'Main work','cooldown':'Cool-down'}
def unit(v):
 if str(v).lower() in ('yd','yds','yard','yards'):return 'yd'
 if str(v).lower() in ('m','meter','meters','metre','metres'):return 'm'
 raise ValueError('Choose yards or meters')
def seconds(v):
 p=v.split(':')
 if len(p) not in (2,3) or any(not x.isdigit() for x in p) or any(int(x)>=60 for x in p[1:]):raise ValueError('Use an interval time such as 1:10')
 return sum(int(x)*60**i for i,x in enumerate(reversed(p)))
def split_sections(text):
 fields={k:[] for k in NAMES};section='main'
 for line in str(text).splitlines():
  line=line.strip(' \t•●');h=HEAD.match(line)
  if h:section='warmup' if h[1].lower().startswith('warm') else 'cooldown' if h[1].lower().startswith('cool') else 'main'
  fields[section].append(line)
 return {k:'\n'.join(v).strip() for k,v in fields.items()}
def parse(fields,repeats=1,distance_unit='yd',pool_length=None):
 distance_unit=unit(distance_unit)
 if isinstance(repeats,bool) or not isinstance(repeats,int) or not 1<=repeats<=10:raise ValueError('Repeat count must be 1–10')
 if pool_length not in (None,''):
  pool_length=float(pool_length)
  if not math.isfinite(pool_length) or not 10<=pool_length<=100:raise ValueError('Pool length must be 10–100 in the selected unit')
 else:pool_length=None
 if not isinstance(fields,dict) or any(len(str(v))>6000 for v in fields.values()) or sum(len(str(v)) for v in fields.values())>18000:raise ValueError('Maximum 6,000 characters per section and 18,000 per swim')
 sets=[];issues=[];warnings=[];totals=[];groups=[];notes=[]
 for section in NAMES:
  group={'label':NAMES[section],'sets':[]};groups.append(group)
  text=str(fields.get(section) or '').replace('×','x').replace('–','-').replace('—','-')
  for raw in re.split(r'\n|;',text):
   line=raw.strip(' \t•●')
   if not line:continue
   t=re.match(r'^total\s*:?\s*([\d,]+)\s*('+UNIT+r')?\b',line,re.I)
   if t:totals.append((int(t[1].replace(',','')),unit(t[2] or distance_unit)));continue
   h=HEAD.match(line)
   if h:
    group={'label':h[1].strip(),'sets':[]};groups.append(group);line=line[h.end():].strip(' :-')
    if not line:continue
   d=re.fullmatch(r'([\d,]+)\s*('+UNIT+r')',line,re.I)
   if d and not group['sets']:group['declared']=(int(d[1].replace(',','')),unit(d[2]));continue
   chunks=re.split(r'\s*/\s*(?=\d+(?:\s*x\s*\d+)?\s*(?:'+UNIT+r'\b|[A-Za-z]))',line,flags=re.I)
   for chunk in chunks:
    m=re.match(r'^(?:(\d+)\s*x\s*)?(\d+(?:\.\d+)?)\s*('+UNIT+r')?\b\s*(.*)$',chunk,re.I)
    if not m:
     if re.match(r'^\d',chunk):issues.append('Could not read this set: '+chunk)
     elif group['sets']:group['sets'][-1]['notes'].append(chunk[:300])
     else:notes.append(chunk[:300])
     continue
    count=int(m[1] or 1);distance=float(m[2]);u=unit(m[3] or distance_unit);description=m[4].strip()
    if not 1<=count<=100 or not 1<=distance<=10000:issues.append('Set repetitions or distance out of range: '+chunk);continue
    if not description:issues.append('Add a stroke or activity for '+chunk);continue
    sendoff=None;rest_seconds=None
    try:
     intervals=re.findall(r'(?:@|\bon\s+)\s*(\d+:\d{2}(?::\d{2})?)',description,re.I)
     if len(intervals)>1:raise ValueError('Choose one send-off per set')
     if not intervals and ('@' in description or re.search(r'\b(?:on|at)\s*\d+:',description,re.I)):raise ValueError('Clarify the send-off; use @ 1:10')
     if intervals:
      if re.search(r'\d+:\d{2}\s*/\s*\d+',description):raise ValueError('Clarify pace versus send-off')
      sendoff=seconds(intervals[0])
      if not 5<=sendoff<=3600:raise ValueError('Send-off must be 5–3600 seconds')
     rest=re.search(r'\brest\s*(?:(\d+:\d{2})|(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?))',description,re.I)
     if rest:rest_seconds=seconds(rest[1]) if rest[1] else float(rest[2])*(60 if rest[3].lower().startswith('min') else 1)
     if sendoff is not None and rest_seconds is not None:raise ValueError('Choose a send-off or fixed rest, not both')
     if rest_seconds is not None and not 0<=rest_seconds<=600:raise ValueError('Rest must be 0–600 seconds')
    except ValueError as e:issues.append(str(e)+': '+chunk);continue
    stroke=next((v for pattern,v in ((r'\b(?:free(?:style)?|front crawl|fs)\b','free'),(r'\b(?:back(?:stroke)?|bs)\b','back'),(r'\bbreast(?:stroke)?\b','breast'),(r'\b(?:fly|butterfly)\b','fly'),(r'\b(?:IM|medley)\b','medley')) if re.search(pattern,description,re.I)),'choice')
    work='kick' if re.search(r'\bkick\b',description,re.I) else 'pull' if re.search(r'\bpull\b',description,re.I) else 'drill' if re.search(r'\bdrill\b',description,re.I) or 'drill' in group['label'].lower() else 'swim'
    item={'section':section,'group':group['label'],'repetitions':count,'distance':distance,'unit':u,'distance_m':round(count*distance*(.9144 if u=='yd' else 1),4),'stroke':stroke,'work':work,'equipment':[name for name in ('board','buoy','paddles','fins','snorkel') if re.search(r'\b'+name+r'\b',description,re.I)],'sendoff_seconds':sendoff,'rest_seconds':rest_seconds,'description':description[:400],'notes':[]}
    if pool_length and u==distance_unit and abs(distance/pool_length-round(distance/pool_length))>.01:warnings.append('A set is not a whole number of pool lengths: '+chunk)
    group['sets'].append(item);sets.append(item)
 for g in groups:
  if g.get('declared'):
   expected,u=g['declared'];actual=sum(s['distance_m'] for s in g['sets'])/(.9144 if u=='yd' else 1)
   if abs(expected-actual)>.05:issues.append(f"{g['label']}: stated {expected:g} {u}, but sets total {actual:g} {u}")
 original=sets;sets=[]
 for section in NAMES:
  for r in range(repeats if section=='main' else 1):sets.extend({**copy.deepcopy(s),'group':s['group']+(f' · round {r+1}' if section=='main' and repeats>1 else '')} for s in original if s['section']==section)
 total_m=round(sum(s['distance_m'] for s in sets),4);distance=round(total_m/(.9144 if distance_unit=='yd' else 1),2)
 for expected,u in totals:
  actual=total_m/(.9144 if u=='yd' else 1)
  if abs(expected-actual)>.05:issues.append(f'Total says {expected:g} {u}, but sets add up to {actual:g} {u}')
 if not sets:issues.append('Add a swim set with distance and a stroke or activity')
 if len(sets)>100 or total_m>30000:issues.append('Split workouts exceeding 100 sets or 30,000 meters')
 timed=sum(s['repetitions']*s['sendoff_seconds'] for s in sets if s['sendoff_seconds'] is not None)
 warnings.append('Send-offs are start-to-start intervals. Rest depends on when you finish each repetition. The final send-off slot is included in scheduled timing.')
 if any(s['sendoff_seconds'] is None for s in sets):warnings.append('Some sets have no timed interval. Enter the full session duration; distance alone cannot determine swimming time.')
 if any(s['stroke'] in ('choice','medley') for s in sets):warnings.append('Choice or medley strokes stay unspecified, not silently converted to freestyle.')
 return {'sets':sets,'total_distance':distance,'unit':distance_unit,'total_distance_m':total_m,'pool_length':pool_length,'sendoff_minutes':round(timed/60,2),'all_sendoffs':bool(sets) and all(s['sendoff_seconds'] is not None for s in sets),'issues':issues,'warnings':list(dict.fromkeys(warnings)),'notes':notes,'valid':not issues}
def validate_recipe(recipe):
 if not isinstance(recipe,dict):raise ValueError('Swim recipe must be an object')
 parsed=parse(recipe.get('fields') or {},recipe.get('repeats',1),recipe.get('unit','yd'),recipe.get('pool_length'))
 if not parsed['valid']:raise ValueError('; '.join(parsed['issues']))
 return {**parsed,'fields':{k:str(recipe.get('fields',{}).get(k) or '')[:6000] for k in NAMES},'repeats':recipe.get('repeats',1)}
def snapshot(recipe):
 work={k:0 for k in ('swim','kick','pull','drill_swim')};stroke={k:0 for k in ('free','back','breast','fly')};unknown=False
 for s in recipe['sets']:
  work['drill_swim' if s['work']=='drill' else s['work']]+=s['distance_m']
  if s['stroke'] in stroke:stroke[s['stroke']]+=s['distance_m']
  elif s['work']!='kick':unknown=True
 out={'purpose':'Reviewed manual or imported swim prescription.','work_mix':{k:v/recipe['total_distance_m']*100 for k,v in work.items()},'why':'Distance and work types come from the prescription. Choice strokes remain unresolved; forecasts use the existing duration-based model. Send-off time includes rest.'}
 n=sum(stroke.values())
 if n and not unknown:out['stroke_mix']={k:v/n*100 for k,v in stroke.items()}
 return out
def add(d,date,req):
 import coach,training_block
 recipe=validate_recipe(req.get('swim_recipe'));minutes=float(req.get('minutes') or 0)
 if not math.isfinite(minutes) or not 1<=minutes<=600:raise ValueError('Enter a full session duration of 1–600 minutes')
 if minutes+.02<recipe['sendoff_minutes']:raise ValueError(f"Timed sets already use {recipe['sendoff_minutes']:g} minutes; review the session duration")
 candidate=copy.deepcopy(d);sessions=copy.deepcopy(training_block.sessions(candidate.get('plans',{}).get(date) or {}));index=req.get('index')
 if index is not None and (isinstance(index,bool) or not isinstance(index,int) or not 0<=index<len(sessions) or sessions[index].get('sport')!='swim'):raise ValueError('Choose the existing swim to edit')
 entry={'sport':'swim','name':str(req.get('name') or 'Swim workout')[:80],'minutes':minutes,'steps':[],'note':str(req.get('note') or '')[:300],'swim_recipe':recipe,'swim_plan':snapshot(recipe),'typed_workout':{**recipe['fields'],'repeats':recipe['repeats']}}
 if req.get('workout_import_id'):entry['workout_import_id']=str(req['workout_import_id'])
 if index is None:sessions.append(entry)
 else:sessions[index]=entry
 coach.set_sessions(candidate,date,sessions)
 return candidate


def recording_draft(activity):
 """FIT-detected strokes form a draft, never a statement of actual drills or kick."""
 pool=activity.get('pool_length_m');measured=activity.get('distance_m') or 0
 if not pool:return {'text':'','unit':'yd','warnings':['Pool length was not recorded; enter distance and sets.'],'groups':[]}
 yards=pool/.9144
 u='yd' if abs(yards-round(yards))<.01 else 'm';size=yards if u=='yd' else pool
 labels={0:'free',1:'back',2:'breast',3:'fly',4:'drill (identify the drill or kick)',5:'choice (verify strokes)',6:'IM'}
 groups=[]
 for x in activity.get('swim_lengths',[]):
  if x.get('length_type')!=1:continue
  stroke=x.get('swim_stroke');label=labels.get(stroke,'choice (stroke not recorded)')
  if not groups or groups[-1]['stroke']!=stroke:groups.append({'stroke':stroke,'label':label,'lengths':0,'distance':0,'seconds':0})
  g=groups[-1];g['lengths']+=1;g['distance']+=size;g['seconds']+=x.get('total_timer_time') or 0
 text='\n'.join(f"{g['distance']:g} {g['label']}" for g in groups)
 detected=sum(g['distance'] for g in groups)*(.9144 if u=='yd' else 1)
 warnings=['Detected strokes can be wrong. Identify drill and kick sections; verify every distance before approving.']
 if abs(detected-measured)>max(1,pool/2):warnings.append(f'Detected lengths total {detected/(.9144 if u=="yd" else 1):g} {u}; watch session total is {measured/(.9144 if u=="yd" else 1):g} {u}. Correct the missing or miscounted lengths.')
 return {'text':text,'unit':u,'pool_length':size,'groups':groups,'warnings':warnings,'detected_distance_m':detected,'recorded_distance_m':measured,'source':'watch-detected draft; unapproved'}
