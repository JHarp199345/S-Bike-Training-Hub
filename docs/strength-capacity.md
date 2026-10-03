# Strength capacity and recovery calibration

Two estimates are separate: the strength estimate for an exercise and the recovery block for each muscle region. Light recent workouts are not a lifetime strength ceiling. Machine labels are specific to the machine, its lever geometry and setup; a machine hip thrust should have a distinct exercise name from a barbell hip thrust or glute bridge.

## What the implementation does today

- Completed weighted sets update an exercise-specific Epley estimated maximum using weight, repetitions and session effort. This is an estimate, not a measured maximum. The logger uses a maximum of four repetitions in reserve, so very easy sets give limited information about true maximum capacity.
- Actual heavier work is scored against the existing strength yardstick first. The new estimate informs later work. Existing logged doses are retained; discovering strength does not erase their recovery burden.
- Regional load blocks start from three times the median of the first three daily regional doses, with a five-point floor. These doses include sets, relative intensity, tempo and estimated regional allocations, rather than pounds alone.
- Follow-up regional ratings and Sunday lifting reports fit the regional reference. The fit currently searches approximately 0.33–3 times the starting reference. Its half-life stays fixed at 1.75 days; the reports change block size, not recovery speed independently.
- The starter calibration form covers squat, bench and row. Custom machine exercises can be planned and logged through the existing lifting workflow, but are not in that starter form.

## How to interpret a return to heavier work

Log the same machine under a consistent, specific name, including its setup and units. A past load without repetitions, effort and date is historical context, not a current strength anchor or a completed workout. Use current controlled working sets and subsequent regional reports to inform a reviewed plan. The model's willingness to schedule a workout is not evidence of biological clearance.

A light starting history can leave the regional reference too restrictive even after the exercise's strength estimate rises. The current bounded automatic fit does not solve every such transition on its own; reviewed reference adjustments can establish a new anchor from fresh evidence. The [reviewed recalibration workflow](coaching-review.md) can now compare predicted and observed recovery over repeated sessions, retain the old estimate and forecast, and make any capacity update explicit. It preserves existing doses and running restrictions rather than reducing them merely because a heavier load was lifted.

The load formulas and fitted blocks are provisional proxies. Strength, willingness to lift and recovery tolerance are different observations.
