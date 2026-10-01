/* overlays.js - the ride's information, one overlay at a time, the same in the map view and the game view.

   Like Kinomap's pages: the overlays cycle every few seconds (swipe or tap to move on), the lock holds the one
   you're on, and something happening jumps to the overlay it concerns for a few seconds (a gate -> Focus, a climb
   -> Route, a new workout block -> Workout, a new form -> Form). A small watts + cadence readout stays up always:
   they're what you steer by. Only the overlays that have something to show are in the cycle.

   Overlays.mount(parent)                 build it (once)
   Overlays.update(st, extra)             every status poll: st = /status, extra = {profile, name, total_m, form}
   Overlays.jump(name, seconds)           show `name` now, for `seconds`, then go back
*/
const Overlays = (() => {
  const ORDER = ['ride', 'focus', 'graph', 'route', 'workout', 'form'];
  const TITLE = { ride: 'RIDE', focus: 'FOCUS', graph: 'GRAPH', route: 'ROUTE', workout: 'WORKOUT', form: 'FORM' };
  let graph = null, graphLoading = false;          // the live graph (livegraph.js): polls only while its card is showing
  const CYCLE_MS = 8000;
  let root, cards = {}, dots, lockBtn, strip, cur = 'ride', locked = false, lastSwitch = Date.now(), jumpUntil = 0, jumpBack = null;
  let avail = new Set(['ride', 'focus']), last = {}, touchX = null;
  try { locked = localStorage.getItem('ovLock') === '1'; cur = localStorage.getItem('ovCur') || 'ride'; } catch (e) {}
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const mmss = s => s == null ? '–' : `${Math.floor(s / 60)}:${String(Math.max(0, Math.floor(s % 60))).padStart(2, '0')}`;
  const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function mount(parent) {
    root = el('div', 'ov');
    strip = el('div', 'ov-strip');
    const box = el('div', 'ov-box');
    for (const k of ORDER) { cards[k] = el('div', 'ov-card'); cards[k].dataset.ov = k; box.appendChild(cards[k]); }
    cards.graph.innerHTML = '<h4>GRAPH · LAST 10 MIN</h4><canvas class="ov-graph"></canvas>';
    cards.graph.querySelector('canvas').addEventListener('click', e => e.stopPropagation());   // touching the graph reads it, not next card
    const bar = el('div', 'ov-bar'); dots = el('div', 'ov-dots'); lockBtn = el('button', 'ov-lock'); lockBtn.type = 'button';
    lockBtn.setAttribute('aria-label', 'Lock this overlay'); bar.append(dots, lockBtn);
    root.append(strip, box, bar); parent.appendChild(root);
    lockBtn.onclick = e => { e.stopPropagation(); locked = !locked; save(); paint(); };
    box.onclick = () => next(1, true);
    box.addEventListener('touchstart', e => { touchX = e.touches[0].clientX; }, { passive: true });
    box.addEventListener('touchend', e => { if (touchX == null) return; const dx = e.changedTouches[0].clientX - touchX; touchX = null;
      if (Math.abs(dx) > 40) { e.preventDefault(); next(dx < 0 ? 1 : -1, true); } });
    setInterval(tick, 500); paint();
  }
  function save() { try { localStorage.setItem('ovLock', locked ? '1' : '0'); localStorage.setItem('ovCur', cur); } catch (e) {} }
  function list() { return ORDER.filter(k => avail.has(k)); }
  function show(k) { cur = k; lastSwitch = Date.now(); save(); paint(); }
  function next(d, byHand) { const l = list(); const i = l.indexOf(cur); show(l[(i + d + l.length) % l.length] || 'ride'); if (byHand) jumpUntil = 0; }
  function jump(k, secs = 5) { if (!avail.has(k) || (cur === k && !jumpUntil)) return; if (!jumpUntil) jumpBack = cur; jumpUntil = Date.now() + secs * 1000; show(k); }
  function tick() {
    if (jumpUntil && Date.now() > jumpUntil) { jumpUntil = 0; if (jumpBack && avail.has(jumpBack)) show(jumpBack); jumpBack = null; return; }
    if (!avail.has(cur)) show(list()[0] || 'ride');
    if (!locked && !jumpUntil && Date.now() - lastSwitch > CYCLE_MS) next(1);
  }
  async function graphOn(on) {
    if (on && !graph && !graphLoading) {
      graphLoading = true;
      try { const { LiveGraph } = await import('/web/livegraph.js');
        graph = new LiveGraph(cards.graph.querySelector('canvas'), { window: 600, compact: true }); } catch (e) {}
      graphLoading = false;
    }
    if (!graph) return;
    if (on && !graph.timer) { graph.start(2000); requestAnimationFrame(() => graph.draw()); }
    if (!on && graph.timer) { graph.stop(); graph.timer = null; }
  }
  function paint() {
    if (!root) return;
    for (const k of ORDER) cards[k].classList.toggle('on', k === cur);
    graphOn(cur === 'graph');
    const l = list();
    dots.innerHTML = l.map(k => `<i class="${k === cur ? 'on' : ''}" title="${TITLE[k]}"></i>`).join('');
    lockBtn.textContent = locked ? '🔒' : '🔓'; lockBtn.classList.toggle('on', locked);
  }
  function bar(v, lo, hi, ok, max) {                                       // a value against its band
    if (lo == null) return '';
    const top = max || hi * 1.35, p = x => Math.max(0, Math.min(100, 100 * x / top));
    return `<div class="ov-band"><u style="left:${p(lo)}%;width:${p(hi) - p(lo)}%"></u><em class="${ok === false ? 'off' : ok ? 'ok' : ''}" style="left:${p(v)}%"></em></div>`;
  }
  // a workout block's watt zones (erg.py): black / red / yellow / GREEN / yellow / red / black around the target
  function zoneBar(v, target, zone, easy) {
    const gh=easy?5/3:1.2,yh=easy?1.8:1.4,rh=easy?2:1.6,top=rh+.2;
    const WZ=[[0,.65,'#111'],[.65,.8,'#e53e3e'],[.8,1,'#ecc94b'],[1,gh,'#48bb78'],[gh,yh,'#ecc94b'],[yh,rh,'#e53e3e'],[rh,top,'#111']];
    const p = x => Math.max(0, Math.min(100, 100 * x / top));
    const grad = WZ.map(([a, b, c]) => `${c} ${p(a)}% ${p(b)}%`).join(',');
    return `<div class="ov-band" style="background:linear-gradient(90deg,${grad});opacity:.95"><em class="${zone === 'green' || zone === 'yellow' ? 'ok' : 'off'}" style="left:${p(v / target)}%"></em></div>`;
  }
  function profileSvg(profile, doneM, totalM) {                            // the route's hills, where you are on them
    if (!profile || profile.length < 2) return '';
    const es = profile.map(p => p[1]), lo = Math.min(...es), hi = Math.max(...es, lo + 20), L = profile[profile.length - 1][0] || totalM || 1;
    const pts = profile.map(p => `${(100 * p[0] / L).toFixed(1)},${(38 - 34 * (p[1] - lo) / (hi - lo)).toFixed(1)}`).join(' ');
    const x = Math.max(0, Math.min(100, 100 * (doneM || 0) / L));
    return `<svg class="ov-prof" viewBox="0 0 100 40" preserveAspectRatio="none"><polygon points="0,40 ${pts} 100,40"/><polyline points="${pts}"/>
      <line x1="${x}" y1="0" x2="${x}" y2="40"/></svg>`;
  }

  function update(st, extra = {}) {
    if (!root || !st) return;
    const f = st.focus || {}, wk = st.workout, rt = st.route;
    // workout blocks: the lit-road watts are the block's target, not the day's focus band
    const wTarget = wk ? wk.watts : null, wLo = wk ? (wk.power_band?.[0]??wTarget) : f.watts?.[0], wHi = wk ? (wk.power_band?.[1]??Math.round(wTarget * 1.4)) : f.watts?.[1];
    const rpm=wk?.cadence_band||f.rpm, rpmOk=extra.effort?extra.effort.rpm_ok:(rpm?st.cadence>=rpm[0]&&st.cadence<=rpm[1]:f.rpm_ok);
    const wOk=extra.effort?extra.effort.watts_ok:wk?(st.power>=wLo):f.watts_ok;
    strip.innerHTML = `<span class="${wOk === false ? 'off' : wOk ? 'ok' : ''}"><b>${st.power ?? '–'}</b> W</span>` +
                      `<span class="${rpmOk === false ? 'off' : rpmOk ? 'ok' : ''}"><b>${st.cadence ?? '–'}</b> rpm</span>`;
    const doneM = rt ? rt.done_m : null, totalM = rt ? rt.total_m : extra.total_m;
    cards.ride.innerHTML = `<h4>RIDE</h4><div class="ov-grid">
      <div><b>${(st.speed ?? 0).toFixed(1)}</b><span>KM/H</span></div><div><b>${st.power ?? '–'}</b><span>WATTS</span></div>
      <div><b>${st.cadence ?? '–'}</b><span>RPM</span></div><div><b>${(rt ? rt.grade : st.grade ?? 0) > 0 ? '+' : ''}${(rt ? rt.grade : st.grade ?? 0).toFixed(1)}%</b><span>GRADE</span></div>
      <div><b>${st.gear > 0 ? '+' : ''}${st.gear ?? 0}</b><span>GEAR</span></div>
      <div><b>${rt ? ((rt.total_m - rt.done_m) / 1000).toFixed(1) : (st.distance ?? 0).toFixed(1)}</b><span>${rt ? 'KM LEFT' : 'KM'}</span></div></div>`;
    const pct = f.in_range?.both;
    cards.focus.innerHTML = `<h4>FOCUS · ${esc(wk ? 'BLOCK ' + wk.step + ' OF ' + wk.steps : (f.name || 'free ride').toUpperCase())}</h4>
      <div class="ov-fr"><span>CADENCE</span><b>${st.cadence ?? '–'}</b><small>${rpm ? rpm[0] + '–' + rpm[1] : ''}</small></div>${bar(st.cadence, rpm?.[0], rpm?.[1], rpmOk, 110)}
      <div class="ov-fr"><span>WATTS</span><b>${st.power ?? '–'}</b><small>${wLo != null ? (wk?wLo+'+ W · animal floor':wLo+'–'+wHi) : 'no target'}</small></div>${wk ? zoneBar(st.power, wTarget, wk.zone,wk.easy_block) : bar(st.power, wLo, wHi, wOk)}
      ${wk && wk.zone && wk.zone !== 'green' ? `<div class="ov-hint"><span>Resistance ${wk.zone.toUpperCase()} · ${wk.zone_for}s · below the segment floor: correction after 15 s or sooner; above the control band: correction after ${({yellow:'2 min',red:'30 s',black:'8 s'})[wk.zone]}</span></div>` : ''}
      <div class="ov-hint">${esc(extra.hint ?? f.hint ?? '')}${pct != null ? `<span>${pct}% in range</span>` : ''}</div>`;
    avail.clear(); avail.add('ride'); avail.add('focus'); avail.add('graph');
    if (rt || extra.profile) {
      avail.add('route');
      const cue = st.session?.cue, g = st.ghost;
      const gap = g && g.seconds != null ? `${Math.abs(g.seconds)} s ${g.seconds < 0 ? 'ahead of' : 'behind'} ${esc(g.vs)}` : '';
      cards.route.innerHTML = `<h4>ROUTE · ${esc((extra.name || rt?.name || '').toUpperCase())}</h4>
        ${profileSvg(extra.profile, doneM ?? extra.done_m, totalM)}
        <div class="ov-row"><span><b>${totalM != null ? (((totalM - (doneM ?? extra.done_m ?? 0))) / 1000).toFixed(1) : '–'}</b> km left</span>
        <span><b>${(rt ? rt.grade : st.grade ?? 0).toFixed(1)}%</b> now</span></div>
        ${cue ? `<div class="ov-hint">🎯 ${esc(cue)}</div>` : ''}${gap ? `<div class="ov-hint">👻 ${gap}</div>` : ''}`;
      if (cue && cue !== last.cue) jump('route', 6); last.cue = cue;
    }
    if (wk) {
      avail.add('workout');
      const blocks = wk.blocks || [], nxt = blocks[wk.step];               // blocks are [seconds, watts]; step is 1-based
      cards.workout.innerHTML = `<h4>WORKOUT · ${esc(wk.name.toUpperCase())}</h4>
        <div class="ov-grid"><div><b>${wTarget}</b><span>TARGET W</span></div><div><b>${mmss(wk.step_left)}</b><span>THIS BLOCK</span></div>
        <div><b>${mmss(wk.left)}</b><span>TOTAL LEFT</span></div></div>
        <div class="ov-blocks">${blocks.map((b, i) => `<i class="${i + 1 === wk.step ? 'now' : i + 1 < wk.step ? 'done' : ''}" style="flex:${b[0]};height:${Math.max(18, Math.min(100, b[1] / (Math.max(...blocks.map(x => x[1])) || 1) * 100))}%"></i>`).join('')}</div>
        <div class="ov-hint">${nxt ? `Next: ${nxt[1]} W for ${mmss(nxt[0])}` : 'Last block'}</div>
        ${wk.adjustment?`<div class="ov-hint">Adapted from ${wk.adjustment.anchor_watts} W sustained · ${wk.adjustment.scope} ×${wk.adjustment.scale}</div>`:''}`;
      if (wk.step !== last.step && last.step != null) jump('workout', 6); last.step = wk.step;
    } else last.step = null;
    if (extra.form) {
      avail.add('form');
      const fm = extra.form;
      cards.form.innerHTML = `<h4>FORM · ${esc(fm.name)}</h4><div class="ov-formbar"><i style="width:${fm.pct}%"></i></div>
        <div class="ov-row"><span>${fm.last ? 'FINAL FORM' : 'NEXT: ' + esc(fm.next)}</span><span><b>${mmss(fm.streak)}</b> streak</span></div>
        <div class="ov-row"><span>Gates <b>${fm.cleared}/${fm.gates}</b></span><span>${fm.onroad ? 'on the lit road' : 'off the road'}</span></div>
        ${extra.effort?.watts?`<div class="ov-hint">Earn animals: ${extra.effort.rpm?.join('–')||'planned'} rpm · ${extra.effort.watts[0]}${extra.effort.watts[1]==null?'+':'–'+extra.effort.watts[1]} W · 5 s average</div>`:''}`;
      if (fm.name !== last.form && last.form != null) jump('form', 5); last.form = fm.name;
    }
    paint();
  }
  return { mount, update, jump };
})();
window.Overlays = Overlays;       // for pages whose own script is a module
