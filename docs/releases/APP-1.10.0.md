# App 1.10.0 — clearer workout records and swim timing

Released 2026-10-09. Pair with MCP 1.10.0 (114 tools).

- Calories / joules display settings, rates and discreet equivalents; energy sources and mechanical/metabolic distinctions preserved.
- Manual watch import and explicit scheduled/new association, bike/watch combination, clock-alignment preview, duplicate-safe storage and single counting.
- Shared workout cards, session reports and daily Hooper access across six recorded sport categories; saves collapse across views.
- Strength text parsing and corrections, separate planned/reported effort, output assumptions, reusable routine histories, stacked record navigation and red library hearts.
- Swim completion goal/expected ranges, distance/order watch alignment, combined drill blocks, optional athlete split recall and reviewed history timing drafts.
- Swim distance-proportion donut, existing credited front/back heat map with a five-color key, separate watch/described stroke histories with 5/10/20/30/40/60/90-day windows and session/day grouping, duration/volume/HR response panels and unknown data coverage.
- Fitness Dashboard swim history: full-size stroke-distance bars, custom dates and 1–12-month presets, month/quarter/saved-phase/custom-group donuts, six periods initially, up to twelve, three per page or all together. Compact 90-day history stays in Plan only.
- Plan View/Hide workout details stay in Plan for all sports, including today’s swims.
- Cancelled sport icons and red crosses remain beside separately checked recovery days; adherence and plan changes stay separate.
- Private-folder audio/video library, phone ride display, clearer outlook flags and robust optional ghost lookup.

## Verification

107 Python suites and 15 JavaScript suites passed; the paused recovery calibration test was skipped. Browser/JavaScript checks cover shared cards, units, parser rendering, watch import, Plan detail toggles and normal ride controls. The exact MCP release archive was exercised under the stock Python runtime against an isolated Hub, including tool discovery, read/preview/apply, reports and library contracts. Browser screenshots and interaction checks use synthetic data; no real athlete files or bike resistance were changed.

Physical-device verification on other operating systems is not newly claimed by this release. Watch timing alignment requires usable length/lap distance data; ambiguous/missing segments are reviewed, not given invented split grades. History suggestions need at least three comparable recorded performances.

## Distribution and privacy

The unfinished Halloween planet, game routes, scene builder, downloaded scene assets, private workout files, watch activities, ride logs, profiles and credentials are excluded. Existing finished ride views remain available. README screenshots contain synthetic sessions. Restart the Hub when no workout is active, refresh the Coach page, and update the MCP extension to load the new actions.
