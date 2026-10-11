"""health_history.py - the health and history records an athlete chooses to share (2026-10-11).

Private brief: docs/design/program-setup-fixes.md section 4. Everything here stays in coach.json on the athlete's
computer: never in the public repo, never sent to any service.

  screening     a short pre-exercise health screening in the hub's own words, following the ACSM 2015 screening
                logic: whether to check with a doctor first, before vigorous training, or not at all. Advice only.
  conditions    medical conditions in the athlete's words, with a category, status and note
  injuries      past and current injuries: site, roughly when, status, what aggravates them
  medications   in the athlete's words; the ones that change heart rate are marked, because heart-rate readings
                and efficiency mislead without it
  guidance      what a doctor or physiotherapist advised, in the athlete's words: the assistant plans around it

It records and describes. It never diagnoses, never clears anyone to exercise, and never overrides a clinician.
Following the hub's rule, nothing here blocks training by itself: it's evidence and the athlete's own guidance.
"""
import datetime as dt
import uuid

# A short pre-exercise screening in the hub's own words, following the logic of the American College of Sports
# Medicine's 2015 preparticipation screening recommendations (Riebe et al., Med Sci Sports Exerc 2015): current
# exercise, known heart / metabolic / kidney disease, warning symptoms, and the intensity the athlete wants. The
# hub's own extra checks add notes. General guidance, not a validated or medical tool, and never a block.
SCREENING = [
    ("active_now", "Have you exercised on purpose at least 3 days a week, about 30 minutes at a moderate effort, for the last 3 months?", "yes/no"),
    ("heart_disease", "Do you have a heart condition or heart disease that a doctor has diagnosed?", "yes/no"),
    ("metabolic_disease", "Do you have diabetes or another metabolic condition that a doctor has diagnosed?", "yes/no"),
    ("kidney_disease", "Do you have kidney disease that a doctor has diagnosed?", "yes/no"),
    ("symptoms", "Do you get any of these: chest, neck, jaw or arm pain or pressure; unusual breathlessness at rest or with "
                 "light effort; dizziness or fainting; swollen ankles; a racing or pounding heartbeat; leg pain when walking "
                 "that eases with rest; or unusual tiredness with everyday activities?", "yes/no"),
    ("intensity", "How hard do you want to train: light, moderate (you can talk but not sing) or vigorous (only a few words "
                  "at a time)?", "light/moderate/vigorous"),
    ("pregnant", "Are you pregnant or recently gave birth?", "yes/no"),
    ("bone_joint", "Is there a bone, joint, muscle, tendon or ligament problem that more activity might make worse?", "yes/no"),
    ("heart_rate_medication", "Do you take a medication that changes your heart rate (for example a beta blocker)?", "yes/no"),
    ("supervised_only", "Has a doctor told you to exercise only under medical supervision?", "yes/no"),
]
OUTCOMES = {
    "no_clearance_needed": "No need to see a doctor first. Start gradually and report anything unusual.",
    "clearance_before_vigorous": ("Moderate exercise is fine to continue. Check with your doctor before moving to "
                                  "vigorous training."),
    "clearance_before_starting": ("Check with your doctor before starting. Light to moderate exercise, built up "
                                  "gradually, is usually what they'll suggest; share what they advise and the plan "
                                  "will follow it."),
    "stop_and_see_doctor": ("Your answers include warning symptoms. Pause exercise and see a doctor before training. "
                            "If symptoms are severe or sudden, get urgent medical help."),
}
CATEGORIES = ("heart", "kidney", "diabetes", "lung", "nerve_or_back", "joint", "bone", "mental_health", "pregnancy", "other")
INJURY_STATUS = ("healed", "flares", "current")
CONDITION_STATUS = ("current", "managed", "past")
KINDS = {"condition": "conditions", "injury": "injuries", "medication": "medications", "guidance": "guidance"}


def state(d):
    h = d.setdefault("health_history", {})
    for k in ("conditions", "injuries", "medications", "guidance"):
        h.setdefault(k, [])
    return h


def _text(v, n=300):
    return str(v or "").strip()[:n]


def assess(answers):
    """The outcome for a set of answers (the ACSM 2015 logic, plus the hub's own notes)."""
    disease = [k for k in ("heart_disease", "metabolic_disease", "kidney_disease") if answers.get(k)]
    if answers["symptoms"]:
        outcome = "stop_and_see_doctor"
    elif answers["active_now"]:
        outcome = "clearance_before_vigorous" if disease and answers["intensity"] == "vigorous" else "no_clearance_needed"
    else:
        outcome = "clearance_before_starting" if disease else "no_clearance_needed"
    notes = []
    if answers["supervised_only"]:
        notes.append("A doctor advised supervised exercise only: follow that, and share what they said.")
        if outcome == "no_clearance_needed":
            outcome = "clearance_before_starting"
    if answers.get("pregnant"):
        notes.append("Pregnancy or recent birth: check with your doctor or midwife about what's right for you now.")
    if answers.get("bone_joint"):
        notes.append("A bone, joint or soft-tissue problem: record it as an injury so the plan works around it.")
    if answers.get("heart_rate_medication"):
        notes.append("A medication that changes heart rate: heart-rate readings and efficiency will be read with care.")
    if disease and outcome == "no_clearance_needed":
        notes.append("Known " + ", ".join(k.split("_")[0] for k in disease) + " disease: keep your doctor in the loop as training grows.")
    if not answers["active_now"] and outcome == "no_clearance_needed":
        notes.append("Not exercising regularly yet: start light to moderate and build gradually.")
    return outcome, notes


def screen(d, answers, today, clearance=None):
    """Save the screening. Advice only: nothing here blocks training."""
    known = {k for k, _, _ in SCREENING}
    if not isinstance(answers, dict) or set(answers) != known:
        raise ValueError("Answer all ten screening questions: " + ", ".join(sorted(known)))
    if answers["intensity"] not in ("light", "moderate", "vigorous"):
        raise ValueError("intensity is light, moderate or vigorous")
    if not all(isinstance(v, bool) for k, v in answers.items() if k != "intensity"):
        raise ValueError("Answer the yes/no questions with true or false")
    outcome, notes = assess(answers)
    entry = {"date": today, "answers": dict(answers), "result": outcome, "advice": OUTCOMES[outcome], "notes": notes,
             "basis": "The hub's own questions following the ACSM 2015 preparticipation screening logic. General guidance, not a medical assessment."}
    if clearance:
        entry["clearance"] = {"obtained": bool(clearance.get("obtained")), "date": _text(clearance.get("date"), 10),
                              "by": _text(clearance.get("by"), 80), "note": _text(clearance.get("note"))}
    h = state(d)
    h.setdefault("screenings", []).append(entry)
    h["screenings"] = h["screenings"][-10:]
    return entry


def add(d, kind, fields, today):
    if kind not in KINDS:
        raise ValueError("Record kind is condition, injury, medication or guidance")
    f = fields or {}
    rec = {"id": uuid.uuid4().hex[:10], "added": today}
    if kind == "condition":
        if not _text(f.get("name"), 120):
            raise ValueError("Name the condition")
        category = f.get("category", "other")
        if category not in CATEGORIES:
            raise ValueError("Category is one of " + ", ".join(CATEGORIES))
        status = f.get("status", "current")
        if status not in CONDITION_STATUS:
            raise ValueError("Status is current, managed or past")
        rec.update(name=_text(f["name"], 120), category=category, status=status, since=_text(f.get("since"), 40), note=_text(f.get("note")))
    elif kind == "injury":
        if not _text(f.get("site"), 80):
            raise ValueError("Say where the injury is")
        status = f.get("status", "healed")
        if status not in INJURY_STATUS:
            raise ValueError("Status is healed, flares or current")
        rec.update(site=_text(f["site"], 80), when=_text(f.get("when"), 40), status=status,
                   aggravated_by=_text(f.get("aggravated_by")), note=_text(f.get("note")))
    elif kind == "medication":
        if not _text(f.get("name"), 120):
            raise ValueError("Name the medication")
        rec.update(name=_text(f["name"], 120), affects_heart_rate=bool(f.get("affects_heart_rate")), note=_text(f.get("note")))
    else:
        if not _text(f.get("text"), 600):
            raise ValueError("Write what was advised")
        rec.update(text=_text(f["text"], 600), source=_text(f.get("source"), 80), date=_text(f.get("date"), 10))
    state(d)[KINDS[kind]].append(rec)
    return rec


def update(d, kind, rid, fields, today):
    if kind not in KINDS:
        raise ValueError("Record kind is condition, injury, medication or guidance")
    items = state(d)[KINDS[kind]]
    i = next((n for n, r in enumerate(items) if r["id"] == rid), None)
    if i is None:
        raise ValueError("No such record")
    fresh = add({"health_history": {k: [] for k in KINDS.values()}}, kind, {**items[i], **(fields or {})}, items[i]["added"])
    fresh.update(id=rid, updated=today)
    items[i] = fresh
    return fresh


def remove(d, kind, rid):
    if kind not in KINDS:
        raise ValueError("Record kind is condition, injury, medication or guidance")
    items = state(d)[KINDS[kind]]
    keep = [r for r in items if r["id"] != rid]
    if len(keep) == len(items):
        raise ValueError("No such record")
    state(d)[KINDS[kind]] = keep
    return {"removed": rid}


def summary(d):
    """What the athlete has shared, for the athlete and the assistant."""
    h = d.get("health_history") or {}
    latest = (h.get("screenings") or [None])[-1]
    return {"screening": latest, "screening_questions": [{"topic": k, "question": q, "answer": a} for k, q, a in SCREENING],
            "conditions": h.get("conditions", []), "injuries": h.get("injuries", []),
            "medications": h.get("medications", []), "guidance": h.get("guidance", []),
            "heart_rate_note": ("A medication that changes heart rate is recorded: read heart-rate efficiency and zones "
                                "with care.") if any(m.get("affects_heart_rate") for m in h.get("medications", [])) else None,
            "how_to_use": ("Plan around what the athlete shared, as their own guidance: follow clinician guidance, choose "
                           "movements that don't aggravate recorded injuries or conditions, and when the screening "
                           "suggests seeing a doctor first, say so plainly and plan gently until they report clearance. "
                           "Never diagnose, never clear anyone to exercise, never override a clinician."),
            "privacy": "Kept only on this computer, in coach.json."}
