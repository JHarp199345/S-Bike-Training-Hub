# App 1.11.0 — One-line install, assistant-led setup and evidence-led planning

2026-10-11. Use with MCP 1.11.0.

## Install in one line

The whole hub (app, web pages and MCP server) is now one package on PyPI, `s-bike-training-hub`:

```bash
claude mcp add --scope user s-bike-hub -- uvx s-bike-training-hub@latest
```

Ask your assistant to set you up: the MCP server starts the hub by itself when it isn't running. `uvx` runs the latest release, so updates arrive automatically. A packaged install keeps your data in your own data folder (macOS `~/Library/Application Support/S-Bike Hub`), never in the app. **GitHub installs are unchanged:** their data stays exactly where it is.

## Included

- **Assistant-led setup.** The welcome page introduces the hub, shows whether your assistant is connected, and offers a prompt to copy. The assistant walks you through your basics, a short health check, sports and experience, your current routine and your goal, one question at a time. The manual form remains, under "No assistant? Set up by hand", and now has a gender field.
- **Health and history.** A short pre-exercise health check in the hub's own words, following the ACSM's 2015 screening logic (no doctor needed; check before vigorous training; check before starting; or pause and see a doctor). Conditions, past and current injuries, medications that change heart rate and what a clinician advised can be recorded. The assistant plans around them. It never diagnoses or clears anyone.
- **Two-pass planning.** Pass 1 lays out the season as placeholder sessions (sport, role improve or maintain, a minutes band, lifting joint groups). Pass 2 plans the coming week's workouts on request, from your weekly volumes, your reports (a 45-day trend plus the last 7 days word for word) and an evidence playbook. Calendar drafts show a "mirror": the drafted week against your recent weeks.
- **Improvement beyond volume.** Each session's efficiency (pace or power per heartbeat), matched with your closest earlier session of similar duration, with heart-rate drift and, if you turn it on, the day's air temperature.
- **Holds come from your reports.** Running is held only for symptoms you've reported and not yet resolved, a check-in reporting feet or legs at 7/10 or more or pain at a site at 5/10 or more, or a waiting period you chose. Model readings, hop tests and checklists are shown as evidence, not rules.
- **Lifting by joints.** The joint framework (upper: shoulder, elbow, wrist; trunk: spine, hip; lower: knee, ankle), load levels and session shapes, for the assistant to compose original sessions.

## New MCP tools

`get_setup_status`, `save_athlete_basics`, `get_health_history`, `record_health_history`, `get_planning_context`, `set_sport_baseline`, `get_lifting_framework`, `describe_lift_structure`.

## Privacy

Your records stay on your computer. The optional air-temperature lookup is off until you turn it on; it sends only a place rounded to about 10 km and a date to Open-Meteo, and caches the answer locally. Health records are kept locally like everything else. No athlete records, personal workouts, design notes or unreleased scenery are included in this release.
