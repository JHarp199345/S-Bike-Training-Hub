# Changelog

## App 1.12.1 · 2026-10-13 · optional games and support

Use with MCP 1.12.1. Games are separate downloads; no game pack is bundled.

- Quiet Ko-fi help badge with one optional invitation after three module rides, deferred until the ride ends. Local browser counts, permanent dismissal/opt-out, FAQs and reviewed GitHub feedback.

- Optional signed game ZIP/folder installation with a permissions review and replacement backup.
- Isolated game frames, a bounded ride-data/control bridge and the non-threaded Godot 4.7.1 engine.
- Ride World selection, optional module catalogue, in-place workout builder and retained free scenery.
- Reliable return from standalone game pages to the Ride menu; normal Hub page navigation remains available.
- Games are optional: the Hub's planning, reports and free riding remain available without installed modules.


The app and the assistant bundle (MCP) have their own version numbers. The **What's new** button in the Coach header shows the same history inside the hub.

## Unreleased · ride modes

- **Ride modes (games):** The hub runs game packs on one shared, built-in game engine, and only packs signed by the publisher whose files are unchanged since signing. A game reads live power, cadence, speed and your FTP, can set the hill (the hub clamps it, refuses during a route, and flattens it if the game goes quiet), marks moments, and finishes with a result in the ride's events.
- **Lean to steer:** Games can read a lean from a tilted tablet or phone (a phone on a bike on a rocker plate works too) or from your camera, which looks only at your head and shoulders, keeps the video in your browser and is off until you turn it on.
- **A secure port for tablets:** The hub also listens with its own certificate on port 8730 (one above the usual port), since browsers share motion sensors and cameras only with secure pages.

## App 1.12.0 · 2026-10-12 · plan by hand, your reports decide, lifting classifiers, a leaner assistant connection

Use with MCP 1.12.0.

- **Plan by hand on a day grid:** Each phase is a Monday-to-Sunday grid of its days: click or shift-click days and pick a session type; copy, paste and fill forward with a preview before anything is replaced; undo and redo. Saved workouts show on it.
- **One goal field:** Type a goal, or paste an event's web address and the hub fills in the name, the peak date, the planning horizon and the sport.
- **Your program on the calendar:** Planned sessions show faded on every day until the week's workouts are written.
- **Your reports decide:** The daily verdicts come from what you report (feet, legs, shoulders, breathing, illness, the overnight watch reading). Load ratios, recovery blocks and lifting carry-over are shown as evidence to weigh. Two sessions on the same tissue in a day are a caution judged by the combined load.
- **Lifting by type, duration, intensity and style:** Sessions are described by how many muscle groups they work, exercises per group, intensity (light 30-60%, medium 61-80%, heavy 81-105% of each lift's estimated max; never maxing) and style, each lift judged against what you moved last time. The assistant designs a session in one call and the hub suggests the intensity from your phase and your own responses.
- **A faster assistant connection:** Planning reads come as a short brief with sections on request; programs and reviews are compact by default; the server's instructions are a short core with topic guides. The same planning conversation uses about a fifth of the data.
- **Hub-logged lifts take session reports:** No watch file needed.

## App 1.11.0 · 2026-10-11 · one-line install, assistant-led setup, evidence-led planning

Use with MCP 1.11.0.

- **One-line install:** `claude mcp add --scope user s-bike-hub -- uvx s-bike-training-hub@latest` installs the whole hub; the assistant starts it for you and updates arrive automatically. Packaged installs keep data in your own data folder; GitHub installs are unchanged.
- **Assistant-led setup:** the welcome page shows whether your assistant is connected and offers a prompt to copy; the assistant asks one question at a time. The manual form stays, with a gender field.
- **Health and history:** a short health check following the ACSM's 2015 screening logic, plus conditions, injuries, medications and clinician advice the plan respects.
- **Two-pass planning:** a season of placeholder sessions, then each week's workouts from your weekly volumes and reports, with a mirror against your recent weeks.
- **Improvement beyond volume:** efficiency against heart rate, matched with similar earlier sessions, with the day's air temperature if you turn it on.
- **Holds come from your reports:** model readings and checklists are evidence, not rules.
- **Lifting by joints:** a joint framework the assistant composes sessions with.

[Release notes](docs/releases/APP-1.11.0.md)

## App 1.10.3 · 2026-10-11 · training calendar and sport history

Use with MCP 1.10.0.

- **Training calendar:** three months per row with year headings, jump to a month or today, saved phases in color, and every day's planned and recorded sessions. Works without an installed program.
- **Events:** schedule an optional goal by hand, from an event-directory link, or from a public event page. Details pulled from a page are shown for review before anything is saved. Organizer artwork appears only with permission. Removing an event leaves its training in place.
- **Today follows your computer's date.** The midnight rollover waits until open editors and dialogs are closed, so nothing unsaved is lost.
- **Sport training history:** switch between lifting, swimming, cycling and running. Lifting has benchmark lifts, dated session comparisons and saved strength estimates. Running and cycling show weekly totals and session readings.
- **TANK and lifting work:** comparisons can show estimated external work in kJ next to recorded lb × reps. Click an estimate to see its formula and assumptions. These are estimates of external work, not calories burned or recovery predictions.
- **Body workload** can be filtered by sport.

[Release notes](docs/releases/APP-1.10.3.md)

## App 1.10.2 · 2026-10-09 · editable planned workouts, clearer swim comparisons

- A pencil on an unfinished Today workout reopens its warm-up, main work and cool-down. Completed workouts keep their original record.
- Plan's swim details: a larger stroke donut beside the body map, with separate keys for estimated intensity and stroke distance.
- Swim history as vertical columns by session or day over 5–90 days. **Compare** stacks the written plan above what the watch detected.
- A distance-based swim gets a full calendar check when the distance is done, even if it finished early.

[Release notes](docs/releases/APP-1.10.2.md)

## App 1.10.1 · 2026-10-09 · Windows watch imports corrected

Watch-file import works on Windows (the validation step had held a file open). [Release notes](docs/releases/APP-1.10.1.md)

## App 1.10.0 and MCP 1.10.0 · 2026-10-09 · workout records, swim timing, linked watch data

- **Energy units:** calories or joules/watts, with the other shown small alongside.
- **Watch import:** link a watch file to a scheduled workout or add it as a new session. A hub bike recording and a watch file of the same ride count once.
- **One workout format** across sports, with session reports that stay linked to the original workout.
- **Swim timing:** goals and expected times per set, sets matched to the watch by distance and order, drills kept as one block when the watch can't separate them. No split times are made up.
- **Swim history** on the Fitness Dashboard by month, quarter, phase or custom period.
- **Workout library** with hearts, record cards and history per routine.
- MCP 1.10.0: 114 tools.

[Release notes](docs/releases/APP-1.10.0.md)

## App 1.9.0 · 2026-10-07 · recorded work, standard check-ins, load-guided planning

- **Energy from the most reliable source:** bike power, then distance and gradient for runs and walks, then the watch. The watch's own number stays alongside.
- **Report snapshots:** each check-in and workout report freezes the load figures from the moment it was saved.
- **Standard check-ins:** the Hooper questionnaire, pain by body site, session effort on the CR-10 scale, and the weekly OSTRC overuse questionnaire.
- **Plan load outlook:** recorded and projected load through the plan against each phase's target.
- **Bad-report protocol:** high or rising pain holds running and schedules a short re-check.
- **Fitness Dashboard** on one page, with the body workload map.
- MCP 1.9.0: 107 tools.

[Release notes](docs/releases/APP-1.9.0.md)

## App 1.8.1 · 2026-10-05 · music library and clearer workout records

One cycling workout builder with live previews, a private music library for rides, and recorded time shown apart from planned time. [Release notes](docs/releases/APP-1.8.1.md)

## MCP 1.8.0 · 2026-10-05 · the run-walk test

A three-day run-walk test for coming back to running after a hold.

## MCP 1.7.0 · 2026-10-03 · clearer workouts and reliable reports

Workout purpose and test explanations reviewed during check-ins; lifting effort reports fixed. The app gained morning artwork and the update history.

## MCP 1.6.0 and 1.6.1 · 2026-10-03 · race predictions and lifting holds

- Race predictions the assistant makes from the hub's numbers, saved, refreshed after tests and graded against the result.
- Holds count as time under load (every 3 s held counts as a rep at that weight), and sets to failure count as the limit for strength estimates.

## MCP 1.5.0 and earlier · 2026-09-27 to 2026-10-03

- **1.5.0:** whole-sequence coaching review, training rules, the check-in attention list.
- **1.4.0:** guided setup and progression.
- **1.3.0:** apply exactly the plan you reviewed.
- **1.2.0 / 1.2.1:** build and compare programs; smaller planning context.
- **1.1.0:** lifting.
- **1.0.0:** connect an assistant.
- **2026-09-27:** first public release: the bike bridge, coach, training load and dashboard.

Every MCP release is on the [releases page](https://github.com/JHarp199345/S-Bike-Training-Hub/releases).
