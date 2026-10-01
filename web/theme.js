/* theme.js - applies the shared theme (kept on the bridge, so the Mac and the phone match), lets the
   charts use the theme's colour roles, and draws the picker where a page has a [data-theme-picker]
   slot (or a ride drawer / planner side panel). Loaded in <head> without defer, so there's no flash
   of the wrong colours and every chart drawn afterwards resolves its colours. */
(function () {
  const root = document.documentElement, KEY = 'hubTheme';
  const THEMES = {
    classic: ['Classic', 'the original'],
    honeybee: ['Honeybee', 'Gruvbox Dark Hard'],
    rattlesnake: ['Rattlesnake', 'Atelier Dune'],
    peacock: ['Peacock', 'Deep Oceanic Next'],
    harpy_eagle: ['Harpy eagle', 'Grayscale Light'],
    cherry_blossom: ['Cherry blossom', 'Rose Pine'],
  };
  let cache = {};
  function apply(name, save) {
    if (name === 'diamondback') name = 'rattlesnake';
    if (!THEMES[name]) name = 'classic';
    root.dataset.theme = name;
    cache = {};
    try { localStorage.setItem(KEY, name); } catch (e) {}
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = getComputedStyle(root).getPropertyValue('--bg').trim() || '#0b0f14';
    document.querySelectorAll('[data-pick]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.pick === name)));
    window.dispatchEvent(new Event('resize'));             // every chart redraws on resize: now in the new colours
    if (save) fetch('/api/theme', {method: 'POST', body: JSON.stringify({theme: name})}).catch(() => {});
  }
  let first = 'classic';
  try { first = localStorage.getItem(KEY) || 'classic'; } catch (e) {}
  apply(first);
  fetch('/api/theme').then(r => r.json()).then(d => { if (d.theme && d.theme !== root.dataset.theme) apply(d.theme); }).catch(() => {});

  // Canvas can't read CSS variables: resolve "var(--role)" (and "var(--role)66", a colour plus alpha) for it.
  function resolve(v) {
    if (typeof v !== 'string' || v.indexOf('var(') < 0) return v;
    return v.replace(/var\(--([\w-]+)\)/g, (m, k) => {
      if (!(k in cache)) cache[k] = getComputedStyle(root).getPropertyValue('--' + k).trim() || '#888888';
      return cache[k];
    });
  }
  const C2D = window.CanvasRenderingContext2D && CanvasRenderingContext2D.prototype;
  if (C2D) {
    ['fillStyle', 'strokeStyle', 'shadowColor'].forEach(prop => {
      const d = Object.getOwnPropertyDescriptor(C2D, prop);
      if (d && d.set) Object.defineProperty(C2D, prop, {configurable: true, get: d.get,
        set(v) { d.set.call(this, resolve(v)); }});
    });
    const stop = window.CanvasGradient && CanvasGradient.prototype.addColorStop;
    if (stop) CanvasGradient.prototype.addColorStop = function (o, c) { return stop.call(this, o, resolve(c)); };
  }
  window.themeColor = k => resolve(`var(--${k})`);

  function picker() {
    const box = document.createElement('div');
    box.className = 'theme-picker';
    box.innerHTML = '<div class="tp-label">APPEARANCE · the same on every screen</div><div class="tp-row">' +
      Object.entries(THEMES).map(([k, [n, src]]) =>
        `<button type="button" data-pick="${k}" title="${n} - from ${src}" aria-pressed="${k === root.dataset.theme}">` +
        `<span class="sw sw-${k}"></span>${n}</button>`).join('') + '</div>';
    box.querySelectorAll('[data-pick]').forEach(b => b.onclick = () => apply(b.dataset.pick, true));
    return box;
  }
  // One small Appearance button: in the corner of the page, or inside the menu on the map pages (ride, planner),
  // where the corners belong to the controls. It opens the themes in a little panel.
  document.addEventListener('DOMContentLoaded', () => {
    const menu = document.querySelector('#drawer') || document.querySelector('#side');
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'appearance-btn' + (menu ? ' in-menu' : '');
    btn.setAttribute('aria-label', 'Appearance'); btn.setAttribute('aria-expanded', 'false');
    btn.innerHTML = '<span class="ap-dot"></span>' + (menu ? 'Appearance' : '');
    const pop = picker(); pop.classList.add('appearance-pop'); pop.hidden = true;
    const toggle = open => { pop.hidden = !open; btn.setAttribute('aria-expanded', String(open)); };
    btn.onclick = e => { e.stopPropagation(); toggle(pop.hidden); };
    pop.onclick = e => e.stopPropagation();
    document.addEventListener('click', () => toggle(false));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') toggle(false); });
    if (menu) { menu.append(btn, pop); pop.classList.add('in-menu'); }
    else document.body.append(btn, pop);
  });
})();
