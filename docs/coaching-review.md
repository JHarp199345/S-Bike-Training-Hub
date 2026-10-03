# Forecast review and capacity recalibration

The assistant has two separate levers: change the future program within current constraints, or review a capacity estimate when outcomes repeatedly disagree with expectations. This is an assistant-driven workflow; the Hub supplies calculations and enforces reviewed writes, not autonomous optimization or biological clearance.

## Tools and sequence

1. `get_coaching_review` returns 1–14 days of running/lifting forecasts, each day's readings across sports, current running restrictions, unresolved symptoms and capacity candidates. It is also included in `get_recent_weeks` and the MCP Today response. Read the whole sequence, including openers after a peak week.
2. `preview_coaching_change` with `kind: calendar` takes replacements for all sessions on 1–14 uncompleted dates within the next two weeks. Use shorter doses, spacing, eligible substitutions or rest. The before/after forecasts show the full sequence. Unknown or excessive affected running/lifting load, current running holds (a hold from recent running load alone blocks only runs before the Hub's projected clear date; a hop test that is merely due is a run-morning precondition and holds only today's run; symptom, failed hop-test, readiness and return-to-run holds block every run in the window), unresolved overlap, remaining running/lifting conflicts, and worsened forecast-limit breaches block Apply.
3. After athlete approval, `apply_coaching_change` saves the exact `draft_id` with `approved: true`. Re-read the outlook and saved calendar. Changed athlete inputs/source versions or an expired six-hour draft require a fresh review; retained retries return a receipt. Completed days are protected.
4. Capacity candidates appear when recorded work and delayed responses supply sufficient matched evidence. Preview `kind: capacity`, `target: running_block` or `lift_<region>`. The Hub proposes direction and size from the evidence; the assistant cannot supply an arbitrary larger number. The before/after outlook exposes the modeled consequences. Apply uses the same approved-draft workflow.

## Running load: targets, deloads and weekly adaptation

These are provisional product policies (the rider's design), not validated thresholds.

**Targets.** `outlook.running_progression` compares the blocks carried on the coming week's run days with a target for the athlete's current state:

| State | Target (blocks) |
|---|---|
| Building running (build, peak, event-specific), waved week to week | light 0.8–1.0 · middle 1.0–1.2 · heavy 1.2–1.45 |
| Base | 0.8–1.2 |
| Running not the focus (maintain): about a third of the middle | 0.3–0.5 |
| Assessment · taper · recovery | 0.4–0.8 · 0.3–0.6 · 0.1–0.4 |
| Automatic deload, then deep deload | 0.3–0.4, then 0–0.1 |
| Re-entry after a deload (one week) | 0.8–0.9 |

The 1.5-block line remains the hard limit. Runs are spaced so each one lands in the target, not stacked. Maintenance running keeps a little intensity, such as strides: endurance holds through large volume cuts when intensity is kept (Hickson, 1981–85).

**Automatic deload.** Any of these in the last four weeks deloads running to 0.4:
- tightness or pain in a run report;
- a run reported too hard;
- legs or feet 6+ in the morning;
- a hop-test drop of two or more.

If negative reports continue past a week, the target drops to 0.1. Two weeks of them means stop running and get it assessed. Running comes back in at 0.8 for a week, after at least a week and two clean mornings (legs and feet 3 or lower). It's recomputed from the reports every day, so it ends without a manual reset. Shortness of breath or a heart-rate issue is a whole-body warning, not a running one. The Hub changes the target automatically. Calendar changes still go through preview and the athlete's approval, and preview rejects runs over a deload target.

**Weekly cap.** Planned weekly running load (in blocks) may rise at most 15% over the most of the last three weeks, whatever the block says. This guards against any estimate being wrong upward: novice runners who increased weekly distance by more than 30% had more injuries (Nielsen et al., 2014).

**Weekly adaptation (automatic block learning).** A too-small block is the safe error: the plan comes out a little too easy. A too-large one hides real load. So the block shrinks fast and grows slow:
- A run followed by rough mornings, a hop-test drop, or slower running at the same heart rate shrinks it 15% at once. It can't regrow past its earlier size until two clean in-band runs.
- Each week with runs that carried at least 0.8 blocks is scored on how easily they were absorbed:
  - mornings against the prediction for the load (1.5 + 2 × blocks carried, capped at 9);
  - the share of runs that read as too easy;
  - pace per heartbeat against the previous comparable run;
  - heart-rate drift on steady runs of 30+ minutes;
  - the hop test.
- The week grows the block only if it read as too easy: mornings at least a point better than predicted, or the athlete said so. Pace per heartbeat must not have fallen more than 3%, and drift must be under 8%.
- Growth is 1% + 9% × the score. It's capped at 5% with one run and at 3% with no heart-rate evidence.
- Runs under 0.8 blocks are never evidence. Nobody has to carry a heavy load to prove capacity.

**Emphasis phases.** With several goals, build one or two sports in their bands while the others hold about a third, then rotate. Running's deload and maintenance weeks are when the bike or swim builds. Shared tissue competes: running and leg lifting share the legs, and swimming and upper-body lifting share the shoulders. Cycling and lifting coexist best (Wilson et al., 2012).

## Evidence rules

These are provisional product policies, not validated physiological thresholds:

- Ordinary running: three distinct completed run dates with a pre-work forecast and both following mornings' feet/leg reports. Clean responses to predicted high load plus too-easy build/base work can support an increase candidate. Poor responses to predicted low load can support a decrease. Easy recovery/taper sessions do not count as evidence of under-prescription.
- A race contributes only alongside the imported run, saved prediction and delayed recovery reports. Its date or result alone does not establish tolerance. Multiple races/sessions on a date do not multiply the observation count.
- A completed, positively graded benchmark with both clean following mornings may independently support a running review. A benchmark is not scheduled through a current hold or an unknown/excessive forecast on its proposed date. Its grade is stored as a candidate, rather than silently writing a new block during a page read.
- Lifting: compare saved regional block predictions with dated regional follow-ups at least three days after logged work. At least three distinct workout dates with a consistent discrepancy are required. Two rating points of discrepancy, clean reports at 3 or below, or adverse reports at 6 or above are the initial policy. Mixed directions require more evidence. A strength estimate alone is insufficient.
- An eligible review proposes a bounded 10% increase or decrease, requiring approval. A test session or test week can reassess instead; it is not designed to produce a predetermined increase. Multiple sports needing reassessment can justify a test week; it is not automatically scheduled.
- Protected running plateaus, adverse current running readiness and unresolved regional symptoms block capacity changes here. Existing 60% plateau review and personal minimum waits remain part of the separate return-to-run protocol. Resolving a restriction requires its existing review workflow.
- Evidence used before the most recent capacity review cannot trigger it again. Missing pre-work forecasts remain missing; historical forecasts are never invented retrospectively.

## What changes, and what remains recorded

A reviewed running block becomes the reference used by the normal load calculation. For athletes outside the return-to-run protocol, automatic block learning then continues from that reviewed anchor using only runs after the review date; earlier runs never re-teach it. Protected recovery keeps automatic learning off. A reviewed lifting region becomes its reference, after which new follow-ups continue to fit capacity around it. This allows gradual reviewed recalibration beyond an excessively light first-three-session baseline. It does not change the fixed lifting half-life or invent physiological force values.

Recorded activity doses, lifting logs, strength estimates, completed sessions, saved forecast snapshots and protected recovery reviews remain unchanged. Current blocks are explicitly recalculated under the reviewed reference, so their numerical representation can change; the physical work and original predictions remain in history. Reforecast the program before prescribing additional work. Phase sets the program's intent, while evidence supports capacity; a new phase does not itself grant capacity.

Exercise volume, repetitions, tempo, effort and specific machine identity can inform lifting interpretation. Optional range-of-motion persistence remains separate future work. Machine label × repetitions is volume load, not measured tissue force or mechanical work.

## Verification

Synthetic tests cover peak-week/openers conflicts, exact calendar replacements, completed-day protection, current holds, benchmark grading without silent capacity growth, missing forecasts, clean vs adverse delayed responses, race-only limits, recovery purpose, mixed evidence, increase/decrease proposals, approval, expiry, stale state, no evidence reuse and unchanged logs/forecasts. The installable bundle exercises the tools against a real local HTTP server. These tests verify implementation; they do not validate recovery predictions or guarantee assistant decision quality.
