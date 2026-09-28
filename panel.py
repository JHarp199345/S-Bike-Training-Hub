"""panel.py - the bridge's control panel: a page at http://127.0.0.1:8729.

Served by the bridge itself. This Mac can always use it; with the phone
remote on (the default), a phone on the same Wi-Fi can too, once it has
paired with the PIN shown here (see remote.py). The page polls /status once a
second; its Stop button posts /stop, which ends the bridge cleanly.
"""
import asyncio
import json

import mapserver
import remote

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>S-Bike Hub</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 :root{color-scheme:dark}
 [hidden]{display:none!important}
 body{margin:0;background:#0b0f14;color:#eef1f5;font:16px/1.4 -apple-system,"Helvetica Neue",sans-serif;
      padding:28px 24px;max-width:720px}
 h1{font-size:30px;margin:0 0 4px}
 .sub{color:#8b98a8;margin-bottom:22px}
 .dots{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:18px}
 .dot{background:#151b23;border-radius:14px;padding:14px}
 .dot b{display:block;font-size:13px;letter-spacing:1.5px;color:#8b98a8}
 .dot span{font-size:18px;font-weight:700}
 .on{color:#4ade80}.off{color:#f87171}
 .nums{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:18px}
 .num{background:#151b23;border-radius:14px;padding:14px;text-align:center}
 .num span{display:block;font-size:34px;font-weight:800}
 .num b{font-size:13px;color:#8b98a8;letter-spacing:1.5px}
 button{width:100%;padding:16px;border:0;border-radius:14px;font-size:18px;font-weight:700;
        background:#ef4444;color:#fff;cursor:pointer}
 button:disabled{background:#374151;cursor:default}
 .res{display:grid;grid-template-columns:70px 1fr 70px;gap:10px;margin-bottom:14px;align-items:center}
 .res div{background:#151b23;border-radius:14px;padding:10px;text-align:center}
 .res span{display:block;font-size:30px;font-weight:800}.res b{font-size:13px;color:#8b98a8;letter-spacing:1.5px}
 .res small{display:block;color:#8b98a8;font-size:13px;margin-top:2px}
 .erg{background:#151b23;border-radius:14px;padding:12px;margin-bottom:12px}
 .erg .row{display:flex;gap:8px;margin-bottom:8px}
 .erg input,.erg select{flex:1;background:#0b0f14;color:#eef1f5;border:1px solid #2a3441;border-radius:10px;padding:10px;font-size:16px}
 .erg button{width:auto;flex:none;padding:10px 14px;font-size:15px;background:#9333ea}
 .erg button.grey{background:#374151}
 button.auto{background:#16a34a;margin-bottom:8px}
 button.auto.off{background:#374151}
 button.adj{background:#2563eb;font-size:30px;padding:10px 0}
 ul{list-style:none;padding:0;margin:20px 0 0;color:#b7c1cd;font-size:14px}
 li{padding:5px 0;border-bottom:1px solid #1f2733}
 .graph{background:#151b23;border-radius:14px;padding:10px 10px 6px;margin-bottom:18px}
 .graph canvas{width:100%;height:230px;display:block}
 .graph .top{display:flex;justify-content:space-between;align-items:baseline;margin:0 4px 6px;color:#8b98a8;font-size:13px}
 .graph .top b{color:#eef1f5;font-size:15px}
 .graph label{margin-left:10px;cursor:pointer;user-select:none}.graph input{vertical-align:middle}
 .pbs{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:18px}
 .pb{background:#151b23;border-radius:14px;padding:12px;text-align:center}
 .pb b{font-size:12px;letter-spacing:1.5px;color:#8b98a8}.pb .rec{display:block;font-size:26px;font-weight:800;margin:2px 0}
 .pb small{display:block;color:#8b98a8;font-size:12px}
 .pb .bar{height:6px;background:#0b0f14;border-radius:3px;margin-top:8px;overflow:hidden}
 .pb .bar i{display:block;height:100%;background:#2563eb;width:0;transition:width .5s}
 .pb.live{outline:2px solid #eab308}.pb.live .bar i{background:#eab308}
 #pbflash{background:#422006;color:#fde68a;border:1px solid #eab308;border-radius:14px;padding:14px;font-size:20px;font-weight:800;text-align:center;margin-bottom:14px}
 @media (max-width:520px){.pbs{grid-template-columns:repeat(2,1fr)}}
 .phone{background:#151b23;border-radius:14px;padding:12px 14px;margin:14px 0}
 .phone b{font-size:13px;letter-spacing:1.5px;color:#8b98a8}.phone .pin{font-size:30px;font-weight:800;letter-spacing:6px}
 .phone button{width:auto;padding:8px 12px;font-size:14px;background:#374151;margin-top:6px}
 .qrrow{display:flex;gap:16px;align-items:center;margin:8px 0}.qr{flex:none;width:180px;height:180px;background:#fff;border-radius:10px;overflow:hidden}
 .qr svg{width:100%;height:100%;display:block}
 @media (max-width:520px){.qrrow{flex-direction:column;align-items:flex-start}}
</style></head><body>
<h1>S-Bike Hub</h1><div class="sub" style="margin-bottom:6px"><a href="/ride" style="color:#60a5fa">🗺 Ride view</a> · <a href="/plan" style="color:#60a5fa">Plan a ride</a> · <a href="/fitness" style="color:#60a5fa">📈 Fitness</a> · <a href="/workouts" style="color:#60a5fa">🛠 Workouts</a> · <a href="/posts" style="color:#60a5fa">📣 Posts</a> · <a href="/milestones" style="color:#60a5fa">🎖 Streaks</a> · <a href="/coach" style="color:#60a5fa">🧭 Coach</a></div><div class="sub" id="sub">Starting…</div>
<div class="dots">
 <div class="dot"><b>BIKE</b><span id="bike">–</span></div>
 <div class="dot"><b>WATCH</b><span id="watch">–</span></div>
 <div class="dot"><b>KINOMAP</b><span id="kino">–</span></div>
</div>
<div class="nums">
 <div class="num"><span id="w">0</span><b>WATTS</b></div>
 <div class="num"><span id="rpm">0</span><b>RPM</b></div>
 <div class="num"><span id="kmh">0</span><b>KM/H</b></div>
</div>
<div class="res"><button class="adj" id="dn" title="Easier gear">&minus;</button><div><span id="gear">0</span><b>GEAR</b><small id="lvl"></small></div><button class="adj" id="up" title="Harder gear">+</button></div>
<div class="nums">
 <div class="num"><span id="grade">0.0%</span><b>HILL</b></div>
 <div class="num"><span id="km">0.00</span><b>KM</b></div>
 <div class="num"><span id="elapsed">0:00</span><b>TIME</b></div>
</div>
<div class="nums">
 <div class="num"><span id="kcal">0</span><b>KCAL</b></div>
 <div class="num"><span id="kcalmin">0</span><b>KCAL / MIN</b></div>
 <div class="num"><span id="kj">0</span><b>KJ OF WORK</b></div>
</div>
<div id="pbflash" hidden></div>
<div class="sub" style="margin:0 0 6px;font-weight:700;color:#b7c1cd">PERSONAL BESTS <span style="font-weight:400">· best average power held</span></div>
<div class="pbs" id="pbs"></div>
<div class="graph"><div class="top"><span><b>Last 10 minutes</b> · avg <span id="gavg">–</span> W · <span id="grpm">–</span> rpm</span>
 <span><label><input type="checkbox" data-s="cadence" checked> rpm</label><label><input type="checkbox" data-s="speed"> speed</label><label><input type="checkbox" data-s="grade" checked> hill</label><label><input type="checkbox" data-s="gear" checked> shifts</label></span></div>
 <canvas id="graph"></canvas></div>
<div class="erg">
 <div class="row"><div class="sub" style="flex:1;margin:0" id="ftp">FTP</div>
  <button id="ftptest">Start FTP test</button></div>
 <div class="sub" id="teststate"></div>
 <div class="row"><input id="watts" type="number" min="30" max="400" step="5" value="110">
  <button id="ergon">Hold watts</button><button id="ergoff" class="grey">ERG off</button></div>
 <div class="row"><select id="wsel"></select><button id="wstart">Start workout</button></div>
 <div class="sub" id="ergstate"></div>
</div>
<button id="auto" class="auto">Auto-shift: on</button>
<button id="climb" class="auto off">Climbing mode: off</button>
<div class="sub" id="autolast"></div>
<button id="stop">Stop bridge</button>
<p class="sub"><a href="/report" target="_blank" style="color:#60a5fa">Last ride report</a></p>
<div class="phone" id="phone" hidden><b>PHONE REMOTE</b>
 <div class="qrrow"><div class="qr" id="qr"></div><div>
  <div class="sub" style="margin:4px 0">Point the phone's camera at the code (same Wi-Fi) - it opens the ride view and pairs.
   <span id="qrleft"></span></div>
  <div class="sub" style="margin:10px 0 2px">Or open <span id="addr"></span> and type this PIN:</div>
  <div class="pin" id="pin"></div></div></div>
 <button id="forget">Forget paired phones &amp; new PIN</button></div>
<ul id="log"></ul>
<script>
const $=id=>document.getElementById(id);
function flag(el,on,yes,no){el.textContent=on?yes:no;el.className=on?'on':'off'}
async function tick(){
 try{
  const s=await (await fetch('/status')).json();
  $('sub').textContent='Broadcasting as “'+s.name+'” · running '+s.elapsed;
  flag($('bike'),s.bike,'Connected','Pedal to wake');
  flag($('watch'),s.watch>0,'Connected','Not yet');
  flag($('kino'),s.kinomap>0,'Connected','Not yet');
  $('w').textContent=s.power; $('rpm').textContent=s.cadence; $('kmh').textContent=s.speed;
  $('ftp').textContent='FTP '+s.ftp+' W · '+s.ftp_source;
  const T=s.test;
  $('ftptest').textContent = T && (T.phase==='warm-up'||T.phase==='ramp') ? "I'm done - stop the ramp" : 'Start FTP test';
  if(T){ const mm=x=>Math.floor(x/60)+':'+String(x%60).padStart(2,'0');
    $('teststate').textContent = T.phase==='warm-up' ? 'Warm-up at '+T.target+' W · '+mm(T.left)+' left, then the ramp'
      : T.phase==='ramp' ? 'RAMP: hold '+T.target+' W · next step in '+T.step_left+' s · best minute '+T.best_1min+' W'
      : T.phase==='cool-down' ? (T.result ? 'Done! FTP '+T.result+' W (best minute '+T.best_1min+' W). ' : 'Ended early: '+T.reason+'. ')+'Cool-down '+mm(T.left)
      : ''; }
  else $('teststate').textContent='';
  const ws=$('wsel'), names=s.workouts.join('|'); if(ws.dataset.names!==names){ ws.dataset.names=names; ws.innerHTML=s.workouts.map((n,i)=>'<option value="'+i+'">'+n+'</option>').join(''); }
  if(s.workout){ $('ergstate').textContent='Workout: '+s.workout.name+' · step '+s.workout.step+'/'+s.workout.steps+' at '+s.workout.watts+' W · '
      +Math.floor(s.workout.step_left/60)+':'+String(s.workout.step_left%60).padStart(2,'0')+' left in step, '+Math.floor(s.workout.left/60)+' min left'; }
  else $('ergstate').textContent = s.erg ? ('ERG holding '+s.erg+' W ('+s.erg_source+') · hills and auto-shift paused') : 'ERG off · riding hills';
  $('climb').textContent='Climbing mode: '+(s.climbing?'on (30-45 rpm)':'off');
  $('climb').className='auto'+(s.climbing?'':' off');
  $('auto').textContent='Auto-shift: '+(s.auto?'on':'off'); $('auto').className='auto'+(s.auto?'':' off');
  $('autolast').textContent=s.auto_last?('Last auto-shift: '+s.auto_last):'';
  $('gear').textContent=(s.gear>0?'+':'')+s.gear;
  $('lvl').textContent='resistance level '+s.level;
  $('grade').textContent=(s.grade>0?'+':'')+s.grade.toFixed(1)+'%';
  $('km').textContent=s.distance.toFixed(2); $('elapsed').textContent=s.elapsed;
  $('pbs').innerHTML=s.bests.map(b=>{ const pct=b.now&&b.best?Math.min(100,b.now/b.best*100):0;
    return `<div class="pb${b.live?' live':''}"><b>${b.label.toUpperCase()}</b><span class="rec">${b.best||'–'}${b.best?' W':''}</span>`+
      `<small>this ride ${b.ride??'–'}${b.ride?' W':''}</small><small>${b.now!=null?'now '+b.now+' W':'&nbsp;'}</small><div class="bar"><i style="width:${pct}%"></i></div></div>`; }).join('');
  $('pbflash').hidden=!s.pb; if(s.pb) $('pbflash').textContent=s.pb.text;
  $('kcal').textContent=s.kcal; $('kcalmin').textContent=s.kcal_min.toFixed(1); $('kj').textContent=Math.round(s.kj);
  $('log').innerHTML=s.events.map(e=>'<li>'+e+'</li>').join('');
 }catch(e){
  $('sub').textContent='Bridge is off. Start it from the 🚲 menu icon, or double-click “S-Bike Hub” on your Desktop.';
  $('stop').disabled=true; $('stop').textContent='Stopped';
  ['bike','watch','kino'].forEach(i=>flag($(i),false,'','Off'));
 }
}
async function adj(d){ await fetch('/gear/'+d,{method:'POST'}); tick(); }
$('auto').onclick=async()=>{ const on=!$('auto').textContent.endsWith('on');
 await fetch('/auto/'+(on?'on':'off'),{method:'POST'}); tick(); };
$('ftptest').onclick=async()=>{ await fetch($('ftptest').textContent.startsWith('Start')?'/ftp/start':'/ftp/stop',{method:'POST'}); tick(); };
$('ergon').onclick=async()=>{ await fetch('/erg/'+Math.round($('watts').value),{method:'POST'}); tick(); };
$('ergoff').onclick=async()=>{ await fetch('/erg/off',{method:'POST'}); tick(); };
$('wstart').onclick=async()=>{ await fetch('/workout/'+$('wsel').value,{method:'POST'}); tick(); };
$('climb').onclick=async()=>{ await fetch('/climb/'+($('climb').textContent.includes('on (')?'off':'on'),{method:'POST'}); tick(); };
$('dn').onclick=()=>adj(-1); $('up').onclick=()=>adj(1);
$('stop').onclick=async()=>{ $('stop').disabled=true; $('stop').textContent='Stopping…';
 try{await fetch('/stop',{method:'POST'})}catch(e){} setTimeout(tick,800) };
async function phone(){ try{ const r=await fetch('/remote/info'); if(!r.ok) return; const j=await r.json();
  $('phone').hidden=false; $('pin').textContent=j.pin;
  $('addr').innerHTML=j.addresses.map(a=>'<b style="color:#eef1f5;letter-spacing:0">http://'+a+':'+location.port+'</b>').join(' or '); }catch(e){} }
let qrUrl=null;
async function qr(){ try{ const r=await fetch('/remote/qr'); if(!r.ok) return; const j=await r.json(); if(j.error) return;
  if(j.url!==qrUrl){ qrUrl=j.url; $('qr').innerHTML=j.svg; }
  $('qrleft').textContent='Works once, for '+Math.max(1,Math.round(j.expires_in/60))+' more min.'; }catch(e){} }
$('forget').onclick=async()=>{ if(!confirm('Unpair every phone and pick a new PIN?')) return;
  await fetch('/remote/forget',{method:'POST'}); phone(); };
tick(); setInterval(tick,1000); phone(); qr(); setInterval(qr,5000);
</script>
<script type="module">
import {LiveGraph} from '/web/livegraph.js';
const g=new LiveGraph(document.getElementById('graph'),{window:600}).start();
document.querySelectorAll('[data-s]').forEach(cb=>cb.onchange=()=>{ g.show[cb.dataset.s]=cb.checked; g.draw(); });
setInterval(()=>{ const m=g.summary(); document.getElementById('gavg').textContent=m.watts; document.getElementById('grpm').textContent=m.rpm||'–'; },1000);
</script></body></html>"""


async def serve(bridge, port=8729, lan=True):
    async def handle(reader, writer):
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except Exception:
            writer.close()
            return
        method, path = head.split(b" ")[0:2]
        headers = {}
        for line in head.split(b"\r\n")[1:]:
            k, _, v = line.partition(b":")
            headers[k.strip().lower()] = v.strip()
        body = b""
        n = int(headers.get(b"content-length", b"0") or 0)
        if 0 < n <= 20_000_000:                       # up to 20 MB: GPX uploads, planning requests
            try:
                body = await reader.readexactly(n)
            except Exception:
                writer.close()
                return
        peer = writer.get_extra_info("peername")
        try:
            res = remote.handle(peer, method, path, headers, body) if lan else None
            if res is None:
                res = await mapserver.handle(bridge, method, path.decode(errors="replace"), body,
                                             headers.get(b"host", b"127.0.0.1:8729").decode())
        except Exception as e:
            res = 500, "application/json", json.dumps({"error": str(e)}).encode(), {}
        if res is not None:
            code, ctype, payload, extra = res
            reason = {200: b"OK", 204: b"No Content", 302: b"Found", 400: b"Bad Request", 401: b"Unauthorized",
                      403: b"Forbidden", 404: b"Not Found", 422: b"Unprocessable", 500: b"Error"}.get(code, b"OK")
            hdrs = b"".join(k.encode() + b": " + v.encode() + b"\r\n" for k, v in extra.items())
            if "Cache-Control" not in extra:
                hdrs += b"Cache-Control: no-store\r\n"
            writer.write(b"HTTP/1.1 " + str(code).encode() + b" " + reason + b"\r\nContent-Type: " + ctype.encode()
                         + b"\r\n" + hdrs + b"Content-Length: " + str(len(payload)).encode()
                         + b"\r\nConnection: close\r\n\r\n" + payload)
            await writer.drain()
            writer.close()
            return
        if path == b"/status":
            body, ctype = json.dumps(bridge.status()).encode(), "application/json"
        elif path.startswith(b"/history"):
            # The live graph: points after ?since=<epoch seconds> (all ten minutes without it).
            from urllib.parse import parse_qs, urlsplit
            try:
                since = float(parse_qs(urlsplit(path.decode()).query).get("since", ["0"])[0])
            except ValueError:
                since = 0.0
            import time as _t
            body = json.dumps({"now": _t.time(), "ftp": bridge.profile["ftp"],
                               "band": [bridge.auto.low, bridge.auto.high],
                               "points": bridge.live.since(since)}).encode()
            ctype = "application/json"
        elif path.startswith(b"/climb/") and method == b"POST":
            bridge.climbing(path.endswith(b"/on"))
            body, ctype = b'{"ok":true}', "application/json"
        elif path.startswith(b"/auto/") and method == b"POST":
            bridge.auto.enabled = path.endswith(b"/on")
            bridge.event(f"Auto-shift turned {'on' if bridge.auto.enabled else 'off'}")
            body, ctype = b'{"ok":true}', "application/json"
        elif path == b"/report":
            import report
            p = report.latest()
            rep = p.with_name(p.stem + "_report.html") if p else None
            if p and (not rep.exists() or rep.stat().st_mtime < p.stat().st_mtime):
                rep = report.build(p)       # the ride in progress, up to now
            if not (rep and rep.exists()):
                # The newest ride has no riding in it yet: show the last finished one.
                done = sorted(report.RIDES.glob("ride_*_report.html"), key=lambda q: q.stat().st_mtime)
                rep = done[-1] if done else None
            body = rep.read_bytes() if rep and rep.exists() else b"No ride report yet."
            ctype = "text/html; charset=utf-8"
        elif path in (b"/ftp/start", b"/ftp/stop") and method == b"POST":
            bridge.ftp_test_start() if path.endswith(b"start") else bridge.ftp_test_stop()
            body, ctype = b'{"ok":true}', "application/json"
        elif path.startswith(b"/erg/") and method == b"POST":
            arg = path.split(b"/")[2]
            try:
                bridge.erg_set(None if arg == b"off" else int(arg))
                body = b'{"ok":true}'
            except ValueError:
                body = b'{"ok":false}'
            ctype = "application/json"
        elif path.startswith(b"/workout/") and method == b"POST":
            try:
                bridge.workout_start(int(path.split(b"/")[2]))
                body = b'{"ok":true}'
            except ValueError:
                body = b'{"ok":false}'
            ctype = "application/json"
        elif path.startswith(b"/gear/") and method == b"POST":
            try:
                bridge.shift(int(path.split(b"/")[2]))
                body = b'{"ok":true}'
            except ValueError:
                body = b'{"ok":false}'
            ctype = "application/json"
        elif path.startswith(b"/level/") and method == b"POST":
            try:
                bridge.manual_level(int(path.split(b"/")[2]))
                body = b'{"ok":true}'
            except ValueError:
                body = b'{"ok":false}'
            ctype = "application/json"
        elif path == b"/stop" and method == b"POST":
            body, ctype = b'{"ok":true}', "application/json"
            asyncio.get_running_loop().call_later(0.3, bridge.stop.set)
        else:
            body, ctype = PAGE.encode(), "text/html; charset=utf-8"
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: " + ctype.encode()
                     + b"\r\nCache-Control: no-store\r\nContent-Length: " + str(len(body)).encode()
                     + b"\r\nConnection: close\r\n\r\n" + body)
        await writer.drain()
        writer.close()

    # With the phone remote on, listen on the Wi-Fi too; remote.py turns away
    # anything that isn't this Mac or a paired phone.
    return await asyncio.start_server(handle, "0.0.0.0" if lan else "127.0.0.1", port)
