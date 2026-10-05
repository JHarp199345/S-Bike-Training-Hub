# Capacity planning (local experimental version)

Goal demands, energy estimates, tissue exposure and observed tolerance are separate. No predicted finish time is produced. A requested 5K in 25 minutes is a demand scenario, not an ability claim.

## Workflow

1. Read the orientation profile and recent activity, effort and symptoms.
2. `get_capacity_review` reads saved demands or previews structured demands without saving.
3. Draft phases, then sport session placement and budgets. Compare the entire projected sequence through the existing calendar/coaching-preview calculators. Repair conflicts and reconsider phase dates rather than clearing restrictions.
4. Detail the coming week; use longer-horizon budgets as provisional intent.
5. `preview_program` carries `capacity_demands`, assumptions and current evidence. Apply its exact reviewed draft and read back the calendar.
6. At weekly reviews record explicit delayed recovery using `record_capacity_followup` after an effort report; reassess and preview any changes.

## What the calculations mean

- Steady running: ACSM oxygen-cost equation, speed in meters/minute and grade as a fraction. Conservative supported speed range 134–300 m/min; no downhill extrapolation. Gross and net energy remain distinct. Estimated oxygen demand is not measured VO2max. Weight does not establish fitness.
- Impact: the existing custom `loads.foot_impact` model with explicit cadence and terrain assumptions. Not tissue force or clearance.
- Cycling: power × time yields external work. Illustrative 20–25% gross efficiency estimates metabolic energy separately; mechanical tissue exposure still needs cadence and regional evidence.
- Strength: external volume is weight × reps × sets. Not work, calories or regional strain. Existing strength anchors and region calculators remain authoritative.
- Swimming: do not invent an energy or force value without intensity/technique evidence.

Energy is ongoing calibration context, not a calorie target or prerequisite. Imported watch totals retain their source and unknown active/resting split. Six-week comparison series remain available with or without event demands. A candidate improving-tolerance signal requires repeated same-sport, similarly long efforts, comparable energy sources, no higher RPE and explicit good delayed responses. Comparison filters are provisional and exposed in the result. Silence is not recovery. A recovery week with less work is not evidence of declining capacity. This signal never changes a hold or fitted reference automatically.

## Current limitations

The phase generator and starter placement still use their existing templates. The MCP assistant performs the reconciliation passes; this is not a new autonomous physiological optimizer. Event energy does not specify the training volume needed to prepare. Technique, terrain, equipment, local tissue tolerance and systemic fatigue still require review. Existing long recovery assumptions and sport readiness gates were not relaxed by this change.

## Sources

- [ACSM running equation validation study](https://pmc.ncbi.nlm.nih.gov/articles/PMC3743617/)
- [Cycling work and efficiency study](https://pubmed.ncbi.nlm.nih.gov/3425344/)
- [IOC load monitoring consensus](https://doi.org/10.1136/bjsports-2016-096581)

Only local source was changed. No athlete plan was applied and no public bundle was released.
