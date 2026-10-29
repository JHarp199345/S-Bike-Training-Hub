/* Starts a pack on the shared engine, inside the game frame (packs.runtime_page). A file of its own, not inline, so the
   frame's rules can name every script it may run: the Hub page requires those rules of anything loaded in the game
   frame (module-host.js), so an outside page that a game navigates to can't run any script at all. */
(() => {
const {gameName, config} = JSON.parse(document.getElementById('module-start').textContent);
const status = document.getElementById('status');
const say = (t) => { if (status) status.textContent = t; };
// Draw at one pixel per CSS pixel (?dpr= to change): on a 2x screen a game renders four times the pixels, and its water,
// outlines and anti-aliasing all cost per pixel (Absolute Adrenaline ran at 8 fps at 2x, 60+ at 1x, 2026-10-26).
const wantDpr = Number(new URLSearchParams(location.search).get('dpr')) || 1, realDpr = window.devicePixelRatio || 1;
Object.defineProperty(window, 'devicePixelRatio', {get: () => Math.min(realDpr, wantDpr)});
// Lost graphics: the browser can drop the game's WebGL context (many reloads, memory pressure) - the picture goes black
// while the game runs on. Say so, with a one-tap reload, instead of a black screen. The ride itself is unaffected.
document.getElementById('canvas').addEventListener('webglcontextlost', (e) => {
  e.preventDefault();
  const d = document.createElement('div');
  d.style.cssText = 'position:fixed;inset:0;z-index:100;display:grid;place-items:center;text-align:center;background:#0b141dee';
  d.innerHTML = '<div><div style="font-size:24px;margin-bottom:8px">Graphics reset</div><div style="opacity:.75;margin-bottom:18px">The browser dropped the graphics for this game. Your ride is not affected.</div><button style="padding:12px 22px;font-size:17px">Tap to reload</button></div>';
  d.querySelector('button').onclick = () => location.reload();
  document.body.append(d);
}, false);
window.addEventListener('error', (e) => say('This ride mode hit a problem: ' + (e.message || e.error || 'unknown')));
const missing = Engine.getMissingFeatures({threads: false});
if (missing.length) {
  say('This device or browser is missing what the game needs: ' + missing.join(', ') + '. Try another browser, or the computer running the hub.');
} else {
  // The game's saved settings arrive from the Hub first (module-runtime.js), so they're there when its scenes load.
  const saves = Promise.race([window.SBikeBridge.ready, new Promise((r) => setTimeout(r, 5000))]);
  const engine = new Engine(config);
  saves.then(() => engine.startGame({onProgress: (done, total) => { if (total > 0) say('Loading ' + gameName + '… ' + Math.round(100 * done / total) + '%'); }})
    .then(() => status && status.remove(),
      (e) => say('This ride mode could not start: ' + (e && e.message || e))));
}
})();
