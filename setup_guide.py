"""setup_guide.py - how the assistant walks a new athlete through setup (2026-10-11).

The welcome page introduces the hub and offers a starter prompt; the assistant does the setup through its MCP
connection, one question at a time, helping with answers the athlete isn't sure of. status() says what's done,
what's next and how to ask it; every answer is saved through the hub's normal checks.

Order: basics -> health check -> sports and experience -> current routine -> goal, time and days -> program
(pass 1) -> first week (pass 2).
"""
import datetime as dt

ASK = {
    "basics": ("Ask for weight (either unit), age and gender (female, male, another gender, or prefer not to say). If "
               "they don't know their exact weight, an honest estimate is fine. Save with save_athlete_basics."),
    "health": ("Run the health check from get_health_history, one question at a time, in its words. Explain a question if "
               "asked (for example what counts as moderate effort) without steering the answer. Save with "
               "record_health_history action=screening. Then ask whether there are conditions, past injuries, medications "
               "or a doctor's advice they'd like the plan to respect, and record each with their agreement."),
    "sports": ("Ask which sports they want: cycling, running, swimming, lifting, any mix. For each, their experience: new to "
               "it, returning after a break, or training regularly. Help them choose when unsure (e.g. 'returning' if they "
               "trained before but not in the last few months). Save with save_athlete_basics (sports and experience)."),
    "routine": ("For each chosen sport without recorded history, ask what they do now (sessions a week, typical length or "
                "distance) and their best in the past, if any. 'Nothing yet' is a fine answer. Offer to import watch files if "
                "they have a tracker (import_activities). Save with set_sport_baseline."),
    "goal": ("Ask what they want from training and by when: an event (name and date), a date, or an open goal like "
             "'lose weight over six months'. Then the hours a week they can train now (and later, if it will grow), and "
             "which days work. These go into the program in the next step."),
    "program": ("Build pass 1: get_planning_context(scope=program), then preview_program with phases and weekly placeholders "
                "for the whole period. Show it plainly, then ask: approve, regenerate, or what would you change? Apply only "
                "after approval."),
    "first_week": ("Build pass 2 for the coming week: get_planning_context(scope=week), draft real workouts with "
                   "preview_coaching_change kind=calendar, explain 'why this week', and apply only after approval."),
}
LABELS = {"basics": "Your basics", "health": "A quick health check", "sports": "Sports and experience",
          "routine": "What you do now", "goal": "Goal, time and days", "program": "Your program", "first_week": "Your first week"}


def status(profile, d, activities=(), today=None):
    """What's done and what's next, for the assistant (and the welcome page)."""
    today = today or dt.date.today().isoformat()
    p, d = profile or {}, d or {}
    sports = p.get("sports") or []
    recorded = {str(a.get("sport")) for a in activities or []}
    seen = {"bike": {"bike", "ride"}, "run": {"run"}, "swim": {"swim"}, "lift": {"gym", "lift"}}
    baselines = d.get("sport_baselines") or {}
    missing_routine = [s for s in sports if not (seen.get(s, {s}) & recorded) and s not in baselines]
    week = [(dt.date.fromisoformat(today) + dt.timedelta(days=i)).isoformat() for i in range(7)]
    done = {
        "basics": bool(p.get("weight_kg") and p.get("age") and p.get("gender")),
        "health": bool((d.get("health_history") or {}).get("screenings")),
        "sports": bool(sports) and all((p.get("experience") or {}).get(s) for s in sports),
        "routine": bool(sports) and not missing_routine,
        "goal": bool(d.get("program_goal")),
        "program": bool(d.get("phase_profiles")),
        "first_week": any(((d.get("plans") or {}).get(day) or {}).get("sessions") for day in week),
    }
    steps = [{"step": k, "label": LABELS[k], "done": done[k]} for k in ASK]
    nxt = next((k for k in ASK if not done[k]), None)
    out = {"steps": steps, "next": nxt, "complete": nxt is None,
           "how_to_ask": ASK.get(nxt) if nxt else "Setup is complete. From here, plan each week on request.",
           "known": {"weight_kg": p.get("weight_kg"), "age": p.get("age"), "gender": p.get("gender"), "sports": sports,
                     "experience": p.get("experience") or {}},
           "style": ("Ask one question at a time, in plain words. Help with answers the athlete isn't sure of and say why a "
                     "question matters if they ask. Confirm before saving. Never diagnose; follow anything a doctor advised. "
                     "Everything stays on the athlete's computer.")}
    if nxt == "routine":
        out["routine_needed_for"] = missing_routine
    return out
