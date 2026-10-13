/* ride-world.js - the Ride menu's Ride World tiles, Watch, the in-place workout builder and Find more modules
   (2026-10-12).
   Tiles: the hub's own views (free) and installed modules (bought on itch.io), from the view list the page and the
   installer keep (#scenery). Choosing one shows it. "Find more modules" reads the public catalogue on GitHub only when
   pressed; each entry links to its itch.io page, and a download goes in through the drop box. */
(() => {
  const CATALOG = 'https://raw.githubusercontent.com/JHarp199345/S-Bike-Training-Hub/main/docs/games/catalog.json';
  const FREE = ['map', 'game', 'pixel', 'haunted'];
  const HIDDEN = ['watch', 'pack:connection-test'];            // Watch has its own section; the connection test is for development
  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? '').replace(/[&<>"]/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const show = (view) => window.dispatchEvent(new CustomEvent('hub-show-view', {detail: view}));

  function tiles() {
    const box = $('rw-tiles'), select = $('scenery');
    if (!box || !select) return;
    box.innerHTML = [...select.options].filter((o) => !HIDDEN.includes(o.value)).map((o) => {
      const pack = o.value.startsWith('pack:');
      const badge = pack ? '<span class="rw-badge rw-itch">itch.io</span>' : FREE.includes(o.value) ? '<span class="rw-badge rw-free">Free</span>' : '';
      return `<button type="button" role="listitem" class="rw-tile" data-view="${esc(o.value)}" aria-pressed="${o.value === select.value}"`
        + `${o.disabled ? ' disabled title="' + esc(o.title) + '"' : ''}><b>${esc(o.textContent.replace(' · unavailable', ''))}</b>${badge}`
        + `${o.disabled ? '<small>unavailable</small>' : ''}</button>`;
    }).join('');
  }

  async function more() {
    const box = $('rw-catalog'); box.hidden = false; box.textContent = 'Looking…';
    try {
      const games = (await (await fetch(CATALOG, {cache: 'no-store'})).json()).games || [];
      box.innerHTML = games.map((g) => `<div class="rw-game"><span><b>${esc(g.name)}</b><small>${esc(g.pitch)}</small>`
        + (g.trains ? `<small class="rw-trains">Trains: ${esc(g.trains)}</small>` : '') + '</span>'
        + (/^https:\/\/[a-z0-9-]+\.itch\.io\//i.test(g.itch || '') ? `<a class="rw-play" href="${esc(g.itch)}" target="_blank" rel="noopener">Get it on itch.io</a>` : '<small>coming soon</small>')
        + '</div>').join('') || '<p class="rw-note">No modules listed yet.</p>';
    } catch (e) { box.innerHTML = '<p class="rw-note">The modules list could not be reached.</p>'; }
  }

  // Build a workout without leaving the ride: the coach's own builder, opened here; what you add goes into today's
  // plan, and the ride chooser opens so you can start it.
  function builder() {
    const dialog = $('ride-builder'), frame = $('ride-builder-frame');
    $('ride-setup')?.open && $('ride-setup').close();
    $('ride-workouts')?.open && $('ride-workouts').close();
    frame.src = '/coach?embed=ride#write-ride';
    dialog.showModal();
  }
  addEventListener('message', (e) => {
    if (e.origin !== location.origin || e.source !== $('ride-builder-frame')?.contentWindow) return;
    if (e.data?.type === 'hub-builder-closed') { $('ride-builder').close(); $('ride-builder-frame').src = 'about:blank'; }
    if (e.data?.type === 'hub-workout-added') {
      $('ride-builder').close(); $('ride-builder-frame').src = 'about:blank';
      $('ride-workout-open')?.click();                       // today's plan now has it: pick it and ride
    }
  });

  document.addEventListener('DOMContentLoaded', () => {
    tiles();
    new MutationObserver(tiles).observe($('scenery'), {childList: true, subtree: true, attributes: true});
    $('rw-tiles').addEventListener('click', (e) => {
      const t = e.target.closest('[data-view]'); if (!t || t.disabled) return;
      show(t.dataset.view); tiles();
    });
    $('ride-menu-open')?.addEventListener('click', tiles);
    $('watch-open') && ($('watch-open').onclick = () => { show('watch'); $('ride-setup').close(); });
    $('rw-more') && ($('rw-more').onclick = more);
    $('ride-build-open') && ($('ride-build-open').onclick = builder);
    $('ride-build-link') && ($('ride-build-link').onclick = (e) => { e.preventDefault(); builder(); });
  });
})();
