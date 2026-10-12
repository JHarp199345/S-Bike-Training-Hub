/* ride-lean.js - lean for ride modes (2026-10-12). The hub owns this; games read window.sbike.lean, -1 (left) .. 1 (right).

   Two sources, both optional; whichever is leaning more wins:
   - tilt: the device's gravity sensor (a tablet held like a wheel, or a phone on a bike that leans on a rocker plate).
   - camera: where the rider's head and shoulders are. Only three points are read (nose, left shoulder, right shoulder)
     and everything else the pose model finds is dropped on the spot. The video is never shown, recorded, saved or
     sent anywhere: frames go from the camera to the model in this browser and nowhere else. Off until the rider says.
   Browsers share sensors and cameras only with secure pages (this Mac, or the hub's https port), and iPhone/iPad ask
   for a tap before the tilt sensor. */
const S = window.sbike = window.sbike || {lean: 0, leanSource: ''};
const FLIP = /[?&]flip/.test(location.search) ? -1 : 1;
const parts = {tilt: 0, camera: 0}, live = {tilt: false, camera: false};
const clamp = (v) => Math.max(-1, Math.min(1, v));
const avg = (a) => a.reduce((p, c) => p + c, 0) / a.length;

function publish() {
  const t = live.tilt ? parts.tilt : 0, c = live.camera ? parts.camera : 0;
  S.lean = Math.abs(c) > Math.abs(t) ? c : t;
  S.leanSource = [live.camera && 'camera', live.tilt && 'tilt'].filter(Boolean).join('+');
}

/* --- tilt ---------------------------------------------------------------------------------------------------------- */
const TILT_FULL = 25;                        // degrees of tilt for a full lean
let tiltZero = null, tiltSamples = [];
const screenAngle = () => ((screen.orientation && screen.orientation.angle) || window.orientation || 0) * Math.PI / 180;
function motion(e) {
  const g = e.accelerationIncludingGravity; if (!g || g.x == null) return;
  const a = screenAngle(), sx = g.x * Math.cos(a) + g.y * Math.sin(a), sy = -g.x * Math.sin(a) + g.y * Math.cos(a);
  const roll = Math.atan2(sx, sy) * 180 / Math.PI;
  if (tiltZero === null) { tiltSamples.push(roll); if (tiltSamples.length >= 15) tiltZero = avg(tiltSamples); return; }
  const d = ((roll - tiltZero + 540) % 360) - 180;
  parts.tilt = clamp(FLIP * d / TILT_FULL);
  live.tilt = true;
  publish();
}

/* --- camera: head and shoulders -------------------------------------------------------------------------------------- */
const CAM_FULL = 0.6, CAM_DEAD = 0.12;      // a full lean = the shoulders' middle moving 0.6 shoulder-widths sideways
const KEY = 'sbike.cameraLean';
let stream = null, video = null, landmarker = null, timer = null, camZero = null, camSamples = [];

function step() {
  if (!video || video.readyState < 2) return;
  const found = landmarker.detectForVideo(video, performance.now());
  const p = found.landmarks && found.landmarks[0];
  // The only points read: 0 nose, 11 left shoulder, 12 right shoulder. Nothing else is kept.
  const nose = p && p[0], ls = p && p[11], rs = p && p[12];
  if (!nose || !ls || !rs || (ls.visibility ?? 1) < 0.5 || (rs.visibility ?? 1) < 0.5) { parts.camera = 0; publish(); return; }
  const width = Math.max(0.05, Math.abs(ls.x - rs.x));          // in shoulder-widths, so distance from the camera doesn't matter
  const x = 0.7 * (ls.x + rs.x) / 2 + 0.3 * nose.x;              // mostly the shoulders: a turned head or a sneeze isn't a lean
  if (camZero === null) { camSamples.push(x); if (camSamples.length >= 15) camZero = avg(camSamples); return; }
  let d = (camZero - x) / width / CAM_FULL;                      // the camera faces you: your right is its left
  d = Math.abs(d) < CAM_DEAD ? 0 : d;
  parts.camera = clamp(FLIP * d);
  publish();
}

async function cameraOn() {
  const {FilesetResolver, PoseLandmarker} = await import('/vision/vision_bundle.mjs');
  const files = await FilesetResolver.forVisionTasks('/vision');
  const make = (delegate) => PoseLandmarker.createFromOptions(files, {
    baseOptions: {modelAssetPath: '/vision/pose_landmarker_lite.task', delegate}, runningMode: 'VIDEO', numPoses: 1});
  landmarker = await make('GPU').catch(() => make('CPU'));
  stream = await navigator.mediaDevices.getUserMedia({audio: false, video: {facingMode: 'user', width: 320, height: 240, frameRate: 15}});
  video = document.createElement('video');                       // never added to the page: nothing is shown
  video.muted = true; video.playsInline = true; video.srcObject = stream;
  await video.play();
  camZero = null; camSamples = [];
  live.camera = true;
  timer = setInterval(step, 66);                                 // about 15 looks a second
}

function cameraOff() {
  clearInterval(timer); timer = null;
  if (stream) stream.getTracks().forEach((t) => t.stop());
  if (landmarker) landmarker.close();
  stream = video = landmarker = null;
  live.camera = false; parts.camera = 0;
  publish();
}

S.recenter = () => { tiltZero = null; tiltSamples = []; camZero = null; camSamples = []; };

/* --- the small panel: ask once, show when it's on, off any time ------------------------------------------------------- */
function ui() {
  const $ = (id) => document.getElementById(id);
  const card = $('lean-card'), on = $('lean-live'), later = $('lean-later'), canvas = $('canvas');
  const show = (el) => { for (const x of [card, on, later]) if (x) x.hidden = x !== el; };
  const back = () => canvas && canvas.focus();
  const remember = (v) => { try { localStorage.setItem(KEY, v); } catch (e) {} };
  const said = (() => { try { return localStorage.getItem(KEY); } catch (e) { return null; } })();
  const start = () => cameraOn().then(() => { remember('on'); show(on); },
    (e) => { remember('no'); show(later); $('lean-why').textContent = 'The camera could not start: ' + (e && e.message || e); });

  // tilt: Android just shares; iPhone/iPad need a tap
  if (typeof DeviceMotionEvent !== 'undefined') {
    if (DeviceMotionEvent.requestPermission) {
      const ask = $('tilt-ask');
      if (ask && isSecureContext) { ask.hidden = false; ask.onclick = () => DeviceMotionEvent.requestPermission().then((r) => { if (r === 'granted') addEventListener('devicemotion', motion); ask.remove(); back(); }); }
    } else addEventListener('devicemotion', motion);
  }
  addEventListener('orientationchange', S.recenter);

  if (!isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;   // no camera here
  $('lean-yes').onclick = () => { start(); back(); };
  $('lean-no').onclick = () => { remember('no'); show(later); back(); };
  $('lean-off').onclick = () => { cameraOff(); remember('no'); show(later); back(); };
  later.onclick = () => { show(card); };
  if (said === 'on') start(); else if (said === 'no') show(later); else show(card);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ui); else ui();
