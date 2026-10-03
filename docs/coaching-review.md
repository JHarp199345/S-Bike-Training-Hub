# Forecast review and capacity recalibration

The assistant has two separate levers: change the future program within current constraints, or review a capacity estimate when outcomes repeatedly disagree with expectations. This is an assistant-driven workflow; the Hub supplies calculations and enforces reviewed writes, not autonomous optimization or biological clearance.

## Tools and sequence

1. `get_coaching_review` returns 1–14 days of running/lifting forecasts, each day's readings across sports, current running restrictions, unresolved symptoms and capacity candidates. It is also included in `get_recent_weeks` and the MCP Today response. Read the whole sequence, including openers after a peak week.
2. `preview_coaching_change` with `kind: calendar` takes replacements for all sessions on 1–14 uncompleted dates within the next two weeks. Use shorter doses, spacing, eligible substitutions or rest. The before/after forecasts show the full sequence. Unknown or excessive affected running/lifting load, current running holds, unresolved overlap, remaining running/lifting conflicts, and worsened forecast-limit breaches block Apply.
3. After athlete approval, `apply_coaching_change` saves the exact `draft_id` with `approved: true`. Re-read the outlook and saved calendar. Changed athlete inputs/source versions or an expired six-hour draft require a fresh review; retained retries return a receipt. Completed days are protected.
4. Capacity candidates appear when recorded work and delayed responses supply sufficient matched evidence. Preview `kind: capacity`, `target: running_block` or `lift_<region>`. The Hub proposes direction and size from the evidence; the assistant cannot supply an arbitrary larger number. The before/after outlook exposes the modeled consequences. Apply uses the same approved-draft workflow.

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

A reviewed running block becomes the reference used by the normal load calculation, with automatic historical block learning disabled for that reviewed anchor. A reviewed lifting region becomes its reference, after which new follow-ups continue to fit capacity around it. This allows gradual reviewed recalibration beyond an excessively light first-three-session baseline. It does not change the fixed lifting half-life or invent physiological force values.

Recorded activity doses, lifting logs, strength estimates, completed sessions, saved forecast snapshots and protected recovery reviews remain unchanged. Current blocks are explicitly recalculated under the reviewed reference, so their numerical representation can change; the physical work and original predictions remain in history. Reforecast the program before prescribing additional work. Phase sets the program's intent, while evidence supports capacity; a new phase does not itself grant capacity.

Exercise volume, repetitions, tempo, effort and specific machine identity can inform lifting interpretation. Optional range-of-motion persistence remains separate future work. Machine label × repetitions is volume load, not measured tissue force or mechanical work.

## Verification

Synthetic tests cover peak-week/openers conflicts, exact calendar replacements, completed-day protection, current holds, benchmark grading without silent capacity growth, missing forecasts, clean vs adverse delayed responses, race-only limits, recovery purpose, mixed evidence, increase/decrease proposals, approval, expiry, stale state, no evidence reuse and unchanged logs/forecasts. The installable bundle exercises the tools against a real local HTTP server. These tests verify implementation; they do not validate recovery predictions or guarantee assistant decision quality.
