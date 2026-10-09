# App 1.9.0: recorded work, validated check-ins and a plan that watches its load

## Available in this release

- **Energy from the least heart-rate-dependent source.** Rides use power (mechanical kJ ≈ metabolic kcal at ~20–25% cycling efficiency). Runs and walks use body mass × distance × gradient cost: 1 kcal per kg per km on the flat (Margaria et al. 1963), with Minetti et al. (2002) for hills; walking stretches use the walking curve. Swims use the watch. The watch's own number is always shown beside it, and gaps over 30% are flagged. Body weight is kept as a dated history, so past sessions keep the weight you had then.
- **Report snapshots.** Every daily and weekly check-in, workout report and lifting follow-up freezes its 3-day rate, biggest day and 28-day carried load when you save it, so later formula changes never move your evidence. A one-time preview → apply back-fill rebuilds older reports (marked "rebuilt", with a receipt).
- **Validated check-ins.** The Hooper questionnaire (fatigue, sleep, stress, overall soreness, 1–7; Hooper & Mackinnon 1995); pain by site on 0–10, kept apart from soreness (pain-monitoring model, Silbernagel et al. 2007); session effort on the Borg CR-10 scale (Foster et al. 2001); and the weekly OSTRC overuse injury questionnaire (Clarsen et al. 2013). The Hub's own leg, feet and shoulder soreness, hop test, gut call and journal stay as they were.
- **Plan load outlook** (Plan tab). Recorded and projected 3-day rate, biggest day and 28-day load through your plan, against the phase's target: recovery about 50–60% of your usual rate, taper 40–60% (Bosquet et al. 2007), build steps of 3–10% gated by your reports. Sessions that went well in the last 90 days are listed for reuse. New athletes start from activity guidelines and their wearable's VO2max until 14 days of history replace it. Read-only.
- **Bad-report protocol.** Pain of 5+, pain worse than the last report, or soreness well above your usual holds running and schedules a short re-check that evening and the next morning. The outcome is to resume, stay reduced, step back, or, for red flags, stop and see a professional. Nothing is cancelled silently, and the Hub never diagnoses.
- **Fitness dashboard.** One page: recorded training (with the biggest day in the last 3 against your typical training day), lifting records, body workload (an Overall ring of every region, group views with magnifying graphs, bars stacked by source, 28-day carried totals), calibration and watch measurements.
- **Also:** completed-workout reports (swim SWOLF, distance per stroke and more), actual strength logging (per-set weights, tempo, skipped sets, sled metadata), swim correction against the watch, a more responsive ride screen, and partial-ride credit on the calendar.
- **Assistant tools (MCP 1.9.0, 107 tools)**, including the load outlook, report-snapshot back-fill, re-checks, body weight and wearable starting estimates.

## In progress

- Forecasting your reports from recent rate and carried load, with an accuracy scoreboard.
- Recovery-curve learning is **paused for a research review**. Its preview and apply are off unless `HUB_RECOVERY_LEARNING=1` is set; the curve keeps its starting values.

## Installation and updates

Download this release's source archive, extract it, and follow the README. If you installed with Git, update your checkout. Your local athlete data and settings are preserved; this release contains no athlete records, personal workouts or music.

Use **MCP 1.9.0** (attached to the `mcp-v1.9.0` release) with this app: the assistant tools changed. What's new and optional update notices announce the update; they never install it.

## Verification scope

The Python suites and browser checks run on macOS, Ubuntu and Windows in GitHub Actions, including no-bike HTTP startup and simulated trainer behavior. Software tests do not certify Bluetooth or watch compatibility, real media accounts or physiological accuracy. Energy, load and response readings are estimates for the athlete and coach to judge, not measurements or medical advice.
