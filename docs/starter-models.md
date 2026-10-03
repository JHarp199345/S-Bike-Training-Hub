# Starter workload models and boundaries

The starter catalog is intentionally small: squat, horizontal press, row, bridge and core, plus basic endurance sessions. We use two lifting dose families already supported by the Hub, rather than a database of tissue forces.

1. **Relative strength:** approximate Epley maximum from a reported set; prescribed weight as a modest fraction of that maximum; sets × reps × relative-intensity factor, with tempo/side modifiers. Regional shares allocate that dose.
2. **Effort and exposure time:** bodyweight, bands and holds use reps or hold seconds, intended effort, exercise-type and tempo factors. An easier variation is reduced in difficulty; unscored custom movements are unavailable for reliable regional forecasts.

Body mass matters to applicable activity models. It is not automatically converted into shoulder, Achilles or knee forces for every movement. Without movement geometry, technique and measurement, such a conversion would give unjustified precision.

The three Easy/Moderate/Higher choices are parameterized workload scenarios forecast through existing cardio, muscle, impact, swim and lifting models. They are not an optimal-program search. Some constraints can make candidates similar. Existing saved workouts remain; new starters fill empty dates. Limit flags and missing data are displayed for review.

## Inputs

- Selected sports, experience, weekly time, dates, starting condition and priorities.
- Optional reported lifting weight, reps and repetitions in reserve for squat, bench and row.
- Personal FTP, recorded comparable workout doses, current recovery state and available workout details.
- Explicit provisional neutral defaults where data is missing, if enabled; these are not observations or proven population averages.

## What remains to develop

- Search candidate prescriptions against explicit multi-load budgets, with sport maintenance requirements and bounded progression; stop or report infeasible plans rather than violating constraints.
- Exercise-specific calibration of effort/time doses and variation difficulty from logged sessions and next-day responses.
- Evaluation of forecast error and sensitivity before changing default coefficients or promoting recovery estimates as validated.

Research informs input choice and general programming principles. It does not validate the Hub's regional percentages, block threshold, nonlinear dose multipliers or recovery dates. See README for research links.
