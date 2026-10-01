// livegraph.js - the last ten minutes of the ride, drawn live.
// Used by the Mac panel and the Pixel ride view:
//   const g = new LiveGraph(canvas, {window: 600});  g.start();  (polls /history once a second)
//
// Watts are bars coloured by power zone (% of FTP) over today's watt range (shaded),
// cadence is a line with the auto-shift band marked, grade is a strip along the bottom, and every shift
// is a tick with its new gear. Hover or touch shows the numbers at that moment.
const ZONES = [ // Coggan power zones, as a fraction of FTP
  [0.55, '#6b7280', 'Z1 recovery'], [0.75, '#3b82f6', 'Z2 endurance'], [0.90, '#22c55e', 'Z3 tempo'],
  [1.05, '#eab308', 'Z4 threshold'], [1.20, '#f97316', 'Z5 VO2max'], [Infinity, '#ef4444', 'Z6+ anaerobic']];

export function zoneOf(watts, ftp) {
  const f = watts / (ftp || 180);
  for (const [top, color, name] of ZONES) if (f < top) return {color, name};
}

export class LiveGraph {
  constructor(canvas, opts = {}) {
    this.c = canvas; this.window = opts.window || 600; this.compact = !!opts.compact;
    this.pts = []; this.last = 0; this.ftp = 180; this.band = [65, 80]; this.watts = null; this.hover = null; this.skew = 0;
    this.show = {cadence: true, grade: true, gear: true, speed: false, ...(opts.show || {})};
    const at = e => { const r = this.c.getBoundingClientRect(); this.hover = (e.touches ? e.touches[0].clientX : e.clientX) - r.left; this.draw(); };
    canvas.addEventListener('mousemove', at); canvas.addEventListener('touchmove', at, {passive: true});
    canvas.addEventListener('touchstart', at, {passive: true});
    const off = () => { this.hover = null; this.draw(); };
    canvas.addEventListener('mouseleave', off); canvas.addEventListener('touchend', () => setTimeout(off, 1500));
    addEventListener('resize', () => this.draw());
  }
  start(every = 1000) { this.poll(); this.timer = setInterval(() => this.poll(), every); return this; }
  stop() { clearInterval(this.timer); }
  async poll() {
    try {
      const j = await (await fetch('/history?since=' + this.last)).json();
      this.ftp = j.ftp || this.ftp; this.band = j.band || this.band; this.watts = j.watts || null;
      this.skew = j.now - Date.now() / 1000;                       // Mac clock vs this device's
      for (const p of j.points) if (!this.pts.length || p[0] > this.pts[this.pts.length - 1][0]) this.pts.push(p);
      if (this.pts.length) this.last = this.pts[this.pts.length - 1][0];
      const cut = j.now - this.window; while (this.pts.length && this.pts[0][0] < cut) this.pts.shift();
      this.now = j.now; this.draw();
    } catch (e) { /* the page shows its own connection state */ }
  }
  summary() { // averages over the window: watts, cadence while pedalling
    const w = this.pts.map(p => p[1]), rpm = this.pts.map(p => p[2]).filter(x => x > 0);
    const avg = a => a.length ? Math.round(a.reduce((x, y) => x + y, 0) / a.length) : 0;
    return {watts: avg(w), rpm: avg(rpm), max: w.length ? Math.max(...w) : 0};
  }
  draw() {
    const c = this.c, dpr = devicePixelRatio || 1, W = c.clientWidth, H = c.clientHeight;
    if (!W || !H) return;
    c.width = W * dpr; c.height = H * dpr; const g = c.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    const padL = this.compact ? 30 : 40, padR = this.compact ? 30 : 38, padT = 8, padB = this.compact ? 16 : 20;
    const gradeH = this.show.grade ? (this.compact ? 12 : 18) : 0;
    const x0 = padL, x1 = W - padR, y0 = padT, y1 = H - padB - gradeH;
    const now = this.now || Date.now() / 1000 + this.skew;
    const X = t => x1 - (now - t) / this.window * (x1 - x0);
    const maxW = Math.max(this.ftp * 1.3, ...this.pts.map(p => p[1]), 100);
    const Yw = w => y1 - w / maxW * (y1 - y0), Yr = r => y1 - Math.min(r, 130) / 130 * (y1 - y0);
    g.font = `${this.compact ? 10 : 11}px -apple-system,Roboto,sans-serif`; g.textBaseline = 'middle';
    // grid: watts on the left, rpm on the right
    const taken = this.watts ? this.watts.map(Yw) : [];      // the focus range's own labels win where they'd collide
    for (const f of [0.5, 0.75, 1.0]) {
      const y = Yw(this.ftp * f);
      if (f !== 1 && taken.some(t => Math.abs(t - y) < 11)) continue;
      g.strokeStyle = f === 1 ? 'rgba(234,179,8,.55)' : 'var(--grid)';
      g.setLineDash(f === 1 ? [4, 4] : []); g.beginPath(); g.moveTo(x0, y); g.lineTo(x1, y); g.stroke(); g.setLineDash([]);
      g.fillStyle = f === 1 ? 'var(--warn)' : 'var(--muted)'; g.textAlign = 'right';
      g.fillText(f === 1 ? 'FTP' : Math.round(this.ftp * f), x0 - 4, y);
    }
    if (this.watts) {                    // today's focus: the watt range, shaded (the cadence range is the dotted lines)
      const [lo, hi] = this.watts; g.fillStyle = 'rgba(74,222,128,.12)'; g.fillRect(x0, Yw(hi), x1 - x0, Yw(lo) - Yw(hi));
      g.fillStyle = 'var(--good)'; g.textAlign = 'right'; g.fillText(hi, x0 - 4, Yw(hi));
      if (Yw(lo) - Yw(hi) >= 11) g.fillText(lo, x0 - 4, Yw(lo));     // a thin range on a small graph: just the top
    }
    if (this.show.cadence) {
      for (const r of this.band) { const y = Yr(r); g.strokeStyle = 'rgba(147,197,253,.25)'; g.setLineDash([2, 4]);
        g.beginPath(); g.moveTo(x0, y); g.lineTo(x1, y); g.stroke(); g.setLineDash([]);
        g.fillStyle = 'var(--info)'; g.textAlign = 'left'; g.fillText(r, x1 + 4, y); }
    }
    // watts: one bar per second, coloured by zone
    const bw = Math.max(1, (x1 - x0) / this.window + 0.4);
    for (const p of this.pts) { const x = X(p[0]); if (x < x0) continue;
      g.fillStyle = zoneOf(p[1], this.ftp).color; g.fillRect(x - bw, Yw(p[1]), bw, y1 - Yw(p[1])); }
    // grade strip: green down, brown up
    if (this.show.grade) for (const p of this.pts) { const x = X(p[0]); if (x < x0) continue;
      const gr = p[4], a = Math.min(1, Math.abs(gr) / 10);
      g.fillStyle = gr >= 0 ? `rgba(180,120,60,${0.15 + a * 0.85})` : `rgba(34,197,94,${0.15 + a * 0.6})`;
      g.fillRect(x - bw, y1 + 2, bw, gradeH - 3); }
    const line = (i, color, Y, width) => { g.strokeStyle = color; g.lineWidth = width; g.beginPath(); let on = false;
      for (const p of this.pts) { const x = X(p[0]); if (x < x0) continue; on ? g.lineTo(x, Y(p[i])) : g.moveTo(x, Y(p[i])); on = true; }
      g.stroke(); g.lineWidth = 1; };
    if (this.show.speed) line(3, 'var(--accent2)', v => y1 - Math.min(v, 60) / 60 * (y1 - y0), 1.5);
    if (this.show.cadence) line(2, '#ffffff', Yr, this.compact ? 1.6 : 2);
    // shifts: a tick with the new gear
    if (this.show.gear) { let prev = null;
      for (const p of this.pts) { if (prev !== null && p[5] !== prev) { const x = X(p[0]); if (x >= x0) {
          const up = p[5] > prev; g.fillStyle = up ? 'var(--info)' : 'var(--good)'; g.textAlign = 'center';
          g.fillRect(x - 1, y0, 2, 7); if (!this.compact || (x1 - x0) > 300) g.fillText((p[5] > 0 ? '+' : '') + p[5], x, y0 + 14); } }
        prev = p[5]; } }
    // time axis
    g.fillStyle = 'var(--muted)'; g.textAlign = 'center';
    const step = this.window >= 600 ? 120 : 60;
    for (let s = 0; s <= this.window; s += step) g.fillText(s ? `-${s / 60}m` : 'now', X(now - s), H - padB / 2);
    if (!this.pts.length) { g.fillStyle = 'var(--muted)'; g.textAlign = 'center'; g.fillText('Start pedalling - the graph fills in as you ride', (x0 + x1) / 2, (y0 + y1) / 2); }
    // hover readout
    if (this.hover !== null && this.pts.length) {
      const t = now - (x1 - this.hover) / (x1 - x0) * this.window;
      let best = this.pts[0]; for (const p of this.pts) if (Math.abs(p[0] - t) < Math.abs(best[0] - t)) best = p;
      const x = X(best[0]); g.strokeStyle = 'var(--grid2)'; g.beginPath(); g.moveTo(x, y0); g.lineTo(x, y1); g.stroke();
      const z = zoneOf(best[1], this.ftp), ago = Math.round(now - best[0]);
      const txt = [`${best[1]} W · ${z.name}`, `${best[2]} rpm · ${best[3]} km/h`, `grade ${best[4] > 0 ? '+' : ''}${best[4]}% · gear ${best[5] > 0 ? '+' : ''}${best[5]}`, ago > 1 ? `${Math.floor(ago / 60)}:${String(ago % 60).padStart(2, '0')} ago` : 'now'];
      g.font = `${this.compact ? 11 : 12}px -apple-system,Roboto,sans-serif`;
      const bwid = Math.max(...txt.map(s => g.measureText(s).width)) + 16, bh = txt.length * 16 + 10;
      const bx = x + 10 + bwid > x1 ? x - 10 - bwid : x + 10;
      g.fillStyle = 'var(--glass)'; g.fillRect(bx, y0 + 4, bwid, bh);
      g.fillStyle = 'var(--text)'; g.textAlign = 'left'; txt.forEach((s, i) => g.fillText(s, bx + 8, y0 + 17 + i * 16));
    }
  }
}
