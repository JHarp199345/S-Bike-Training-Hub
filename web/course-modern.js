/* course-modern.js - the course's "Modern" look: soft layered silhouettes, a sky that moves from dawn to dusk
   over the course, a vector rider whose legs turn the cranks at your cadence, and the forms as animated
   silhouettes. Everything is drawn in code - no image files. Uses the page's canvas (g, W, H) and state
   (course, game, st, shownD, ele, onRoadNow, FORMS). */
const MODERN = (() => {
  const TAU = Math.PI * 2;
  const lerp = (a, b, f) => a + (b - a) * f;
  const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const mix = (a, b, f) => { const x = hex(a), y = hex(b); return `rgb(${x.map((v, i) => Math.round(lerp(v, y[i], f))).join(',')})`; };
  const mixHex = (a, b, f) => '#' + hex(a).map((v, i) => Math.round(lerp(v, hex(b)[i], f)).toString(16).padStart(2, '0')).join('');
  const mixA = (a, b, f, al) => { const x = hex(a), y = hex(b); return `rgba(${x.map((v, i) => Math.round(lerp(v, y[i], f))).join(',')},${al})`; };
  // the sky over the course: dawn -> day -> golden hour -> dusk
  const SKY = [[0, '#23284f', '#f49d6e', '#ffd9a8'], [0.35, '#4f86c6', '#bfe0f2', '#fff4d6'],
               [0.72, '#3b3f86', '#f7a35c', '#ffe0a0'], [1, '#161a3a', '#c85a6a', '#ffb07a']];
  function sky(p) {
    let i = 0; while (i < SKY.length - 2 && p > SKY[i + 1][0]) i++;
    const a = SKY[i], b = SKY[i + 1], f = Math.max(0, Math.min(1, (p - a[0]) / (b[0] - a[0])));
    return { top: mix(a[1], b[1], f), low: mix(a[2], b[2], f), sun: mix(a[3], b[3], f), topH: [a[1], b[1], f], lowH: [a[2], b[2], f] };
  }
  const INK = '#12162a';
  const noise = (x, s) => Math.sin(x * 0.9 + s) * 0.5 + Math.sin(x * 2.1 + s * 1.7) * 0.28 + Math.sin(x * 4.7 + s * 2.3) * 0.14 + Math.sin(x * 9.3 + s) * 0.08;
  const hash = n => { const x = Math.sin(n * 127.1) * 43758.5453; return x - Math.floor(x); };
  let sparks = [], lastForm = null, burst = 0, flies = null;

  function ridge(off, base, amp, freq, seed, col) {
    g.fillStyle = col; g.beginPath(); g.moveTo(0, H);
    for (let x = 0; x <= W + 8; x += 8) g.lineTo(x, base - amp * noise((x + off) / W * freq, seed));
    g.lineTo(W, H); g.closePath(); g.fill();
  }
  function pine(x, y, h, col) {
    g.fillStyle = col; g.beginPath(); g.moveTo(x, y - h);
    for (const [dx, dy] of [[0.28, 0.35], [0.12, 0.35], [0.36, 0.7], [0.14, 0.7], [0.42, 1]]) g.lineTo(x + dx * h * 0.6, y - h + dy * h);
    for (const [dx, dy] of [[-0.42, 1], [-0.14, 0.7], [-0.36, 0.7], [-0.12, 0.35], [-0.28, 0.35]]) g.lineTo(x + dx * h * 0.6, y - h + dy * h);
    g.closePath(); g.fill(); g.fillRect(x - h * 0.03, y - h * 0.05, h * 0.06, h * 0.1);
  }
  // two-bone leg: hip -> knee -> foot, knee bending `dir` (+1 forward)
  function leg(hx, hy, fx, fy, l1, l2, dir, w) {
    let dx = fx - hx, dy = fy - hy, d = Math.hypot(dx, dy); const m = l1 + l2 - 0.01;
    if (d > m) { fx = hx + dx / d * m; fy = hy + dy / d * m; dx = fx - hx; dy = fy - hy; d = m; }
    const a = (l1 * l1 - l2 * l2 + d * d) / (2 * d), h = Math.sqrt(Math.max(0, l1 * l1 - a * a));
    const px = hx + a * dx / d, py = hy + a * dy / d, kx = px - dir * h * dy / d, ky = py + dir * h * dx / d;
    g.lineWidth = w; g.lineCap = 'round'; g.lineJoin = 'round';
    g.beginPath(); g.moveTo(hx, hy); g.lineTo(kx, ky); g.lineTo(fx, fy); g.stroke();
  }

  // ── the rider: wheels, frame, and legs on the cranks at your cadence ──
  function cyclist(k, crank, scarf, t) {
    const R = 3.3 * k, wy = -R, rear = -5 * k, front = 5 * k, bb = [-0.6 * k, wy + 0.4 * k];
    const seat = [-2.3 * k, wy - 5 * k], bar = [3.6 * k, wy - 5.6 * k];
    g.strokeStyle = INK; g.fillStyle = INK;
    g.lineWidth = 0.35 * k; for (const cx of [rear, front]) { g.beginPath(); g.arc(cx, wy, R, 0, TAU); g.stroke();
      g.lineWidth = 0.08 * k; for (let i = 0; i < 8; i++) { const a = crank * 2.2 + i * TAU / 8; g.beginPath(); g.moveTo(cx, wy); g.lineTo(cx + Math.cos(a) * R, wy + Math.sin(a) * R); g.stroke(); } g.lineWidth = 0.35 * k; }
    g.lineWidth = 0.42 * k; g.lineCap = 'round'; g.beginPath();
    g.moveTo(rear, wy); g.lineTo(bb[0], bb[1]); g.lineTo(seat[0] + 0.3 * k, seat[1] + 0.6 * k); g.lineTo(rear, wy);
    g.moveTo(bb[0], bb[1]); g.lineTo(bar[0] - 0.6 * k, bar[1] + 1.2 * k); g.lineTo(front, wy);
    g.moveTo(seat[0] + 0.3 * k, seat[1] + 0.6 * k); g.lineTo(bar[0] - 0.6 * k, bar[1] + 1.2 * k); g.lineTo(bar[0], bar[1]); g.stroke();
    const hip = [seat[0], seat[1] - 0.3 * k], sh = [1.5 * k, wy - 8.3 * k], cr = 1.5 * k;
    for (const side of [Math.PI, 0]) {                                           // far leg first, then near
      const a = crank + side, f = [bb[0] + Math.cos(a) * cr, bb[1] + Math.sin(a) * cr];
      g.strokeStyle = side ? mixA('#12162a', '#ffffff', 0.12, 1) : INK; leg(hip[0], hip[1], f[0], f[1], 3.5 * k, 3.4 * k, -1, 0.9 * k);   // knees forward
    }
    g.strokeStyle = INK; g.lineWidth = 1.5 * k; g.beginPath(); g.moveTo(hip[0], hip[1]); g.lineTo(sh[0], sh[1]); g.stroke();
    g.lineWidth = 0.7 * k; leg(sh[0], sh[1], bar[0], bar[1], 2.4 * k, 2.3 * k, 1, 0.7 * k);     // elbows down
    g.beginPath(); g.arc(sh[0] + 1.3 * k, sh[1] - 1.5 * k, 1.1 * k, 0, TAU); g.fill();
    g.fillStyle = scarf; g.beginPath(); g.moveTo(sh[0] + 0.6 * k, sh[1] - 0.6 * k);   // the scarf, streaming back
    for (let i = 1; i <= 6; i++) g.lineTo(sh[0] + 0.6 * k - i * 1.1 * k, sh[1] - 0.6 * k + Math.sin(t / 140 + i) * 0.35 * k * i / 3 + i * 0.15 * k);
    for (let i = 6; i >= 1; i--) g.lineTo(sh[0] + 0.6 * k - i * 1.1 * k, sh[1] + 0.1 * k + Math.sin(t / 140 + i) * 0.35 * k * i / 3 + i * 0.15 * k);
    g.closePath(); g.fill();
  }

  // ── the forms: four-legged gaits drawn as silhouettes ──
  function legs4(k, ph, hips, len, w, gallop, col, dirs = [-1, -1, 1, 1]) {
    g.strokeStyle = col;
    hips.forEach(([x, y, off], i) => {
      const a = Math.sin(ph + off) * (gallop ? 0.55 : 0.35), lift = Math.max(0, Math.cos(ph + off)) * (gallop ? 1.1 : 0.6) * k;
      leg(x, y, x + Math.sin(a) * len * 0.9, -lift, len * 0.52, len * 0.52, dirs[i], w);
    });
  }
  const FORM = {
    unicorn(k, ph, t) {
      legs4(k, ph, [[-3.2 * k, -5.6 * k, 0], [-2.4 * k, -5.6 * k, 0.6], [2.4 * k, -5.8 * k, Math.PI], [3.1 * k, -5.8 * k, Math.PI + 0.6]], 5.6 * k, 0.75 * k, true, INK, [1, 1, -1, -1]);
      g.fillStyle = INK; g.beginPath(); g.ellipse(0, -6.8 * k, 4.3 * k, 2 * k, -0.05, 0, TAU); g.fill();
      g.beginPath(); g.moveTo(2.6 * k, -7.8 * k); g.lineTo(5.1 * k, -11.2 * k); g.lineTo(6.3 * k, -10.6 * k); g.lineTo(4.4 * k, -6.4 * k); g.fill();
      g.beginPath(); g.ellipse(6.4 * k, -11 * k, 1.8 * k, 0.9 * k, 0.45, 0, TAU); g.fill();
      g.strokeStyle = '#ffd86b'; g.lineWidth = 0.35 * k; g.beginPath(); g.moveTo(6.2 * k, -12 * k); g.lineTo(7.6 * k, -14.6 * k); g.stroke();
      const mane = g.createLinearGradient(2 * k, -12 * k, 0, -5 * k);
      ['#ff6b9d', '#ffb86b', '#fff06b', '#6bffb8', '#6bb8ff', '#b86bff'].forEach((c, i) => mane.addColorStop(i / 5, c));
      g.fillStyle = mane; g.beginPath(); g.moveTo(5.4 * k, -12 * k);           // a full mane streaming off the neck
      for (let i = 0; i <= 7; i++) g.lineTo(5.2 * k - i * 0.8 * k - 0.8 * k, -11.6 * k + i * 0.72 * k + Math.sin(t / 110 + i) * 0.6 * k);
      for (let i = 7; i >= 0; i--) g.lineTo(5.2 * k - i * 0.62 * k, -11.2 * k + i * 0.62 * k);
      g.closePath(); g.fill();
      g.beginPath(); g.moveTo(-4 * k, -7.8 * k);                                   // and a tail to match
      for (let i = 1; i <= 7; i++) g.lineTo(-4 * k - i * 0.95 * k, -7.8 * k + i * 0.55 * k + Math.sin(t / 120 + i) * 0.7 * k);
      for (let i = 7; i >= 1; i--) g.lineTo(-4 * k - i * 0.9 * k, -6.2 * k + i * 0.7 * k + Math.sin(t / 120 + i) * 0.7 * k);
      g.closePath(); g.fill();
    },
    gorilla(k, ph) {
      g.fillStyle = INK; g.strokeStyle = INK;
      legs4(k, ph * 0.8, [[-3 * k, -5 * k, 0], [-2.2 * k, -5 * k, Math.PI]], 4.8 * k, 1.3 * k, false, INK);
      g.beginPath(); g.ellipse(-2.4 * k, -5.8 * k, 2.6 * k, 2.2 * k, 0, 0, TAU); g.fill();
      g.beginPath(); g.ellipse(0.9 * k, -8.2 * k, 4.2 * k, 3.3 * k, -0.25, 0, TAU); g.fill();
      g.beginPath(); g.arc(4.3 * k, -9.4 * k, 1.7 * k, 0, TAU); g.fill();
      g.fillRect(3.4 * k, -11.2 * k, 2.6 * k, 0.8 * k);                         // the brow
      for (const [off, x] of [[Math.PI, 2 * k], [0, 3 * k]]) {                   // knuckle-walking arms
        const a = Math.sin(ph * 0.8 + off) * 0.4, lift = Math.max(0, Math.cos(ph * 0.8 + off)) * 0.7 * k;
        leg(x, -8.6 * k, x + 1.5 * k + Math.sin(a) * 4 * k, -lift - 0.3 * k, 4.1 * k, 4.3 * k, -1, 1.5 * k);
      }
    },
    panda(k, ph) {
      const bob = Math.abs(Math.sin(ph)) * 0.3 * k;
      legs4(k, ph * 0.7, [[-2.8 * k, -3.6 * k, 0], [-2 * k, -3.6 * k, Math.PI], [2 * k, -3.8 * k, Math.PI], [2.8 * k, -3.8 * k, 0]], 3.6 * k, 1.5 * k, false, INK);
      g.fillStyle = '#f4f1ea'; g.beginPath(); g.ellipse(0, -5 * k - bob, 4.3 * k, 3 * k, 0, 0, TAU); g.fill();
      g.fillStyle = INK; g.beginPath(); g.ellipse(1.8 * k, -5.3 * k - bob, 1.6 * k, 3.1 * k, 0.3, 0, TAU); g.fill();
      g.fillStyle = '#f4f1ea'; g.beginPath(); g.arc(4.5 * k, -7 * k - bob, 2.2 * k, 0, TAU); g.fill();
      g.fillStyle = INK; for (const [x, y, r] of [[3.4 * k, -8.9 * k, 0.8 * k], [5.4 * k, -9 * k, 0.8 * k], [6.5 * k, -6.6 * k, 0.4 * k]]) { g.beginPath(); g.arc(x, y - bob, r, 0, TAU); g.fill(); }
      g.beginPath(); g.ellipse(5.1 * k, -7.3 * k - bob, 0.6 * k, 0.9 * k, 0.5, 0, TAU); g.fill();
      g.beginPath(); g.ellipse(3.9 * k, -7.3 * k - bob, 0.55 * k, 0.85 * k, -0.4, 0, TAU); g.fill();
    },
    dragon(k, ph, t, on) {
      const flap = Math.sin(t / 180) * 0.9;
      g.fillStyle = mix('#12162a', '#1d3b3a', 0.6); g.beginPath();                // far wing
      g.moveTo(0.5 * k, -7.6 * k); g.lineTo(-2 * k, -13 * k - flap * 3 * k); g.lineTo(-5.5 * k, -9.5 * k - flap * 2 * k); g.lineTo(-2.5 * k, -7 * k); g.fill();
      legs4(k, ph, [[-2.8 * k, -5.4 * k, 0], [-2 * k, -5.4 * k, 0.6], [2.2 * k, -5.6 * k, Math.PI], [2.9 * k, -5.6 * k, Math.PI + 0.6]], 5 * k, 0.8 * k, true, INK, [1, 1, -1, -1]);
      g.fillStyle = INK; g.beginPath(); g.ellipse(0, -6.5 * k, 4.6 * k, 1.9 * k, 0, 0, TAU); g.fill();
      g.beginPath(); g.moveTo(-4 * k, -7.2 * k);                                   // the tail
      for (let i = 1; i <= 8; i++) g.lineTo(-4 * k - i * 0.9 * k, -7 * k + i * 0.45 * k + Math.sin(t / 200 + i * 0.6) * 0.5 * k);
      for (let i = 8; i >= 1; i--) g.lineTo(-4 * k - i * 0.9 * k, -6 * k + i * 0.45 * k * 0.9 + Math.sin(t / 200 + i * 0.6) * 0.5 * k);
      g.fill();
      g.beginPath(); g.moveTo(3 * k, -7.4 * k); g.quadraticCurveTo(5.5 * k, -9 * k, 5.6 * k, -11.4 * k);
      g.lineTo(6.9 * k, -11.2 * k); g.quadraticCurveTo(6.4 * k, -8 * k, 4.2 * k, -5.8 * k); g.fill();
      g.beginPath(); g.moveTo(5.2 * k, -12.2 * k); g.lineTo(8.6 * k, -11.3 * k); g.lineTo(8.4 * k, -10.5 * k); g.lineTo(5.4 * k, -10.4 * k); g.fill();
      g.strokeStyle = INK; g.lineWidth = 0.3 * k; g.beginPath(); g.moveTo(5.6 * k, -12 * k); g.lineTo(4.8 * k, -13.6 * k); g.moveTo(6.3 * k, -12 * k); g.lineTo(5.8 * k, -13.8 * k); g.stroke();
      g.fillStyle = INK; g.beginPath();                                            // near wing, edged in embers
      g.moveTo(1 * k, -7.6 * k); g.lineTo(-1 * k, -14.5 * k - flap * 3.4 * k); g.lineTo(-4.8 * k, -11 * k - flap * 2.2 * k); g.lineTo(-2 * k, -7 * k); g.fill();
      g.strokeStyle = 'rgba(255,120,60,.7)'; g.lineWidth = 0.18 * k; g.stroke();
      if (on) for (let i = 0; i < 3; i++) sparks.push({ x: 8.6 * k, y: -10.9 * k, vx: 0.5 * k + Math.random() * 0.4 * k, vy: (Math.random() - 0.6) * 0.25 * k, life: 1, fire: 1, local: true });
    },
  };
  const SCARF = { bike: '#ff6b6b', unicorn: '#ff9ad1', gorilla: '#ffb347', panda: '#7fd4ff', dragon: '#ff7a3c' };

  function draw(t) {
    const L = course ? (course.length_m || 1) : 1, p = course ? Math.max(0, Math.min(1, shownD / L)) : 0.05, s = sky(p);
    const gr = g.createLinearGradient(0, 0, 0, H); gr.addColorStop(0, s.top); gr.addColorStop(0.62, s.low); gr.addColorStop(1, s.low);
    g.fillStyle = gr; g.fillRect(0, 0, W, H);
    const night = Math.max(0, (p - 0.8) / 0.2) + Math.max(0, (0.12 - p) / 0.12) * 0.6;
    if (night > 0) { g.fillStyle = `rgba(255,255,255,${0.7 * night})`; for (let i = 0; i < 60; i++) g.fillRect(hash(i) * W, hash(i + 99) * H * 0.45, 1.5, 1.5); }
    const sunX = W * lerp(0.2, 0.85, p), sunY = H * (0.5 - Math.sin(Math.PI * Math.min(1, p * 1.1)) * 0.28);
    const glow = g.createRadialGradient(sunX, sunY, 0, sunX, sunY, H * 0.35);
    glow.addColorStop(0, mixA(s.lowH[0], '#ffffff', 0.5, 0.55)); glow.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = glow; g.fillRect(0, 0, W, H);
    g.fillStyle = s.sun; g.beginPath(); g.arc(sunX, sunY, Math.min(W, H) * 0.045, 0, TAU); g.fill();
    const far = s.lowH, farHex = mixHex(far[0], far[1], far[2]), ink = f => mix(farHex, INK, f);   // atmospheric depth: far ridges fade into the sky
    ridge(shownD * 0.02, H * 0.56, H * 0.12, 1.6, 1.1, ink(0.25));
    ridge(shownD * 0.05, H * 0.62, H * 0.1, 2.4, 3.7, ink(0.45));
    const hz = g.createLinearGradient(0, H * 0.55, 0, H * 0.72); hz.addColorStop(0, 'rgba(255,255,255,0)'); hz.addColorStop(1, mixA(farHex, '#ffffff', 0.2, 0.25)); g.fillStyle = hz; g.fillRect(0, H * 0.55, W, H * 0.2);
    ridge(shownD * 0.11, H * 0.7, H * 0.07, 3.3, 6.2, ink(0.65));
    if (!course) return;
    const k = Math.min(W, H) * 0.015, mpp = 420 / W, rx = W * 0.3, baseY = H * 0.74, VX = 7 / mpp;   // hills drawn 7x steeper
    const e0 = ele(shownD), yAt = x => baseY - (ele(shownD + (x - rx) * mpp) - e0) * VX, on = onRoadNow();
    const tstep = 42 / mpp, first = Math.floor((shownD - rx * mpp) / 42);                            // pines along the hills
    for (let i = first; i < first + W / tstep + 2; i++) { if (hash(i) < 0.45) continue; const x = rx + (i * 42 - shownD) / mpp + hash(i + 7) * tstep * 0.6;
      pine(x, yAt(x) + k * 0.6, k * (6 + hash(i + 3) * 7), ink(0.82)); }
    const tg = g.createLinearGradient(0, baseY - H * 0.1, 0, H); tg.addColorStop(0, INK); tg.addColorStop(1, '#070912');
    g.fillStyle = tg; g.beginPath(); g.moveTo(0, H); for (let x = 0; x <= W + 6; x += 6) g.lineTo(x, yAt(x)); g.lineTo(W, H); g.closePath(); g.fill();
    g.lineWidth = Math.max(2, k * 0.35); g.lineCap = 'round';                   // the road: faint behind, lit ahead while you're in range
    g.strokeStyle = 'rgba(255,255,255,.14)'; g.beginPath(); for (let x = 0; x <= rx; x += 6) g.lineTo(x, yAt(x) - 1); g.stroke();
    if (on) { const rg = g.createLinearGradient(rx, 0, W, 0); rg.addColorStop(0, '#9ff4ff'); rg.addColorStop(1, 'rgba(255,214,120,.9)');
      g.save(); g.lineWidth = k * 1.3; g.strokeStyle = 'rgba(127,232,255,.18)';      // the glow: a wide soft stroke, not a blur
      g.beginPath(); for (let x = rx; x <= W + 6; x += 6) g.lineTo(x, yAt(x) - 1); g.stroke(); g.restore(); g.strokeStyle = rg; }
    else g.strokeStyle = 'rgba(255,255,255,.22)';
    g.beginPath(); for (let x = rx; x <= W + 6; x += 6) g.lineTo(x, yAt(x) - 1); g.stroke();
    g.font = `600 ${Math.round(k * 0.95)}px system-ui,-apple-system,sans-serif`; g.textAlign = 'left';
    for (const pt of course.parts) { const x = rx + (pt.start_m - shownD) / mpp; if (x < -W * 0.2 || x > W) continue; const y = yAt(x);
      g.fillStyle = 'rgba(255,255,255,.35)'; g.fillRect(x, y - k * 5, Math.max(1, k * 0.12), k * 5);
      g.fillStyle = 'rgba(255,255,255,.75)'; g.fillText(pt.label.toUpperCase(), x + k * 0.5, y - k * 4); }
    for (const gt of course.gates || []) { const x = rx + (gt.at_m - shownD) / mpp; if (x < -k * 8 || x > W + k * 8) continue;
      const y = yAt(x), st8 = game.gates[gt.kind + gt.at_m], col = st8?.state === 'cleared' ? '#8dffb0' : st8?.state === 'missed' ? 'rgba(255,255,255,.3)' : gt.kind === 'spin' ? '#7fe8ff' : '#ffc27a';
      g.strokeStyle = col; g.lineWidth = k * 0.3;
      g.beginPath(); g.arc(x, y - k * 5, k * 3.2, Math.PI, 0); g.lineTo(x + k * 3.2, y); g.moveTo(x - k * 3.2, y - k * 5); g.lineTo(x - k * 3.2, y); g.stroke();
      g.fillStyle = col; g.textAlign = 'center'; g.fillText(gt.kind === 'spin' ? 'SPIN' : 'PUSH', x, y - k * 9);
      if (st8?.state === 'open') { g.strokeStyle = '#fff'; g.lineWidth = k * 0.35; g.beginPath(); g.arc(x, y - k * 5, k * 2.4, -Math.PI / 2, -Math.PI / 2 + TAU * Math.min(1, st8.held / gt.secs)); g.stroke(); }
      g.textAlign = 'left'; }
    // the rider (or the form), tilted to the slope
    const gy = yAt(rx), ang = Math.atan2(yAt(rx + 12) - yAt(rx - 12), 24), rpm = st?.cadence || 0, form = FORMS[game.form];
    const crank = (t / 1000) * (rpm / 60) * TAU, ph = (t / 1000) * Math.max(0.6, (st?.speed || 0) / 12) * TAU;
    if (lastForm !== null && lastForm !== form) burst = 1; lastForm = form;
    const aura = Math.min(1, game.streak / 180);
    g.save(); g.translate(rx, gy); g.rotate(ang);
    if (aura > 0.05 || burst > 0) { const ag = g.createRadialGradient(0, -7 * k, 0, 0, -7 * k, k * (9 + aura * 5 + burst * 14));
      ag.addColorStop(0, `rgba(255,220,140,${0.28 * aura + 0.5 * burst})`); ag.addColorStop(1, 'rgba(255,220,140,0)'); g.fillStyle = ag; g.fillRect(-k * 30, -k * 30, k * 60, k * 40); }
    if (form === 'bike') cyclist(k, crank, SCARF.bike, t);
    else { g.imageSmoothingEnabled = true;                                   // the animal's filmed strip; code-drawn only as a fallback
      if (!drawAnimal(g, form, 0, k * 0.4, k * 11, t, shownD) && FORM[form]) FORM[form](k, ph, t, on);
      if (form === 'dragon' && on) for (let i = 0; i < 2; i++) sparks.push({ x: 7.5 * k, y: -11 * k, vx: 0.5 * k + Math.random() * 0.4 * k, vy: (Math.random() - 0.6) * 0.25 * k, life: 1, fire: 1, local: true }); }
    for (const sp of sparks.filter(q => q.local)) { sp.x += sp.vx; sp.y += sp.vy; sp.life -= 0.04;
      g.fillStyle = sp.fire ? `rgba(255,${Math.round(120 + 100 * sp.life)},60,${sp.life})` : `rgba(180,245,255,${sp.life})`; g.beginPath(); g.arc(sp.x, sp.y, k * 0.35 * (0.5 + sp.life), 0, TAU); g.fill(); }
    g.restore();
    if (on && Math.random() < 0.5) sparks.push({ x: rx - k * 4, y: gy - k * 0.5, vx: -k * (0.3 + Math.random() * 0.4), vy: -Math.random() * k * 0.15, life: 1 });
    for (const sp of sparks.filter(q => !q.local)) { sp.x += sp.vx; sp.y += sp.vy; sp.life -= 0.025; g.fillStyle = `rgba(180,245,255,${sp.life * 0.8})`; g.fillRect(sp.x, sp.y, k * 0.3, k * 0.3); }
    sparks = sparks.filter(q => q.life > 0).slice(-160);
    if (burst > 0) { g.strokeStyle = `rgba(255,236,180,${burst})`; g.lineWidth = k * 0.4; g.beginPath(); g.arc(rx, gy - 7 * k, k * (4 + (1 - burst) * 26), 0, TAU); g.stroke(); burst = Math.max(0, burst - 0.02); }
    if (!flies) flies = Array.from({ length: 18 }, (_, i) => ({ x: hash(i) * W, y: H * (0.55 + hash(i + 40) * 0.3), s: hash(i + 80) }));
    if (p > 0.7) for (const f of flies) { f.x = (f.x - (st?.speed || 0) * 0.05 + W) % W; const a = (0.4 + 0.6 * Math.sin(t / 400 + f.s * 9)) * (p - 0.7) / 0.3;
      g.fillStyle = `rgba(255,236,150,${a})`; g.beginPath(); g.arc(f.x, f.y + Math.sin(t / 700 + f.s * 7) * k, k * 0.25, 0, TAU); g.fill(); }
    const vg = g.createRadialGradient(W / 2, H * 0.45, Math.min(W, H) * 0.3, W / 2, H * 0.5, Math.max(W, H) * 0.75);
    vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, 'rgba(0,0,0,.35)'); g.fillStyle = vg; g.fillRect(0, 0, W, H);
  }
  return { draw };
})();
