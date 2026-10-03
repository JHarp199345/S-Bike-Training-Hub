// shots.js - photograph the Coach at one point in the demo journey.
//   node shots.js <hub url> <YYYY-MM-DD> <folder>
// The browser's clock is set to that day (the hub's own clock is set by journey.py), so "today" matches.
const { chromium } = require('playwright');
const [,, url, day, out] = process.argv;
const VIEWS = [['desktop', { width: 1280, height: 900 }], ['phone', { width: 390, height: 844 }]];

(async () => {
  const browser = await chromium.launch();
  for (const [name, viewport] of VIEWS) {
    const ctx = await browser.newContext({ viewport, deviceScaleFactor: 2, colorScheme: 'dark' });
    const page = await ctx.newPage();
    await page.clock.install({ time: new Date(day + 'T19:30:00') });
    page.on('pageerror', e => console.log('PAGEERROR', e.message));
    const settle = async (ms = 1200) => { await page.waitForLoadState('networkidle').catch(() => {}); await page.waitForTimeout(ms); };
    const shot = async (file, opts = {}) => { await page.screenshot({ path: `${out}/${name}-${file}.png`, ...opts }); };
    await page.goto(url + '/coach#today'); await settle(2500);
    await shot('today');
    await shot('today-full', { fullPage: true });
    // the Plan tab: program timeline, this week, and the week strip
    await page.click('[data-tab="plan"]').catch(() => {}); await settle(2000);
    await shot('plan');
    await shot('plan-full', { fullPage: true });
    const strip = page.locator('#weekstrip');
    if (await strip.count() && await strip.isVisible()) { await strip.scrollIntoViewIfNeeded(); await strip.screenshot({ path: `${out}/${name}-weekstrip.png` }); }
    // the full program calendar (View more)
    const more = page.locator('#viewblock');
    if (await more.count() && await more.isVisible()) {
      await more.click(); await settle(1500);
      const dlg = page.locator('#programcalendardialog');
      if (await dlg.isVisible()) { await dlg.screenshot({ path: `${out}/${name}-program-calendar.png` });
        // detailed weeks: the training calendar with sessions, done and missed
        const loadsBtn = page.locator('#programcalendarloads');
        if (await loadsBtn.isVisible()) { await loadsBtn.click(); await settle(2500);
          const cal = page.locator('#blockdialog');
          if (await cal.isVisible()) { await cal.screenshot({ path: `${out}/${name}-training-calendar.png` }); }
          await page.keyboard.press('Escape'); await settle(500);
        }
        await page.keyboard.press('Escape'); await settle(500);
      }
    }
    // Fitness Dashboard
    await page.goto(url + '/coach#fitness'); await settle(3500);
    await shot('fitness');
    await shot('fitness-full', { fullPage: true });
    await ctx.close();
  }
  await browser.close();
})();
