"""journal.py - flags from the rider's journal: it flags, it never scores.

Asked for on 2026-09-29. The journal is the rider's own words with each check-in. Letting
the words move the numbers invites drift - writing yourself into a longer (or shorter)
recovery without meaning to. So the journal never changes a number by itself. It raises a
FLAG when the words and the sliders disagree, or when the words name something that
matters whatever the sliders say:

  bone     sharp or pin-point pain, pain on hopping or walking, swelling, a limp  -> feet & bones
  muscle   a pull, a strain, a cramp that won't let go, a muscle that gave out    -> leg muscles
  illness  fever, chest pain, dizziness, being sick                               -> heart & lungs
  better   "no pain at all, feel great" while the sliders say 6+/10 - the other direction

A flag is open until the rider settles it: CONFIRM ("it's real - count it") or DISMISS
("it's fine"). Only a confirmed flag counts, and it counts the way a slider would:
  bone    -> that day's feet & bones read as 6/10 (a high report, judged by the phase rules)
  muscle  -> that day's legs read as 6/10
  illness -> heart & lungs easy that day
  better  -> nothing is raised; it's a prompt to move the sliders if they're wrong
The matching is plain phrases with a negation check ("no pain", "not sore"), on purpose:
it's predictable, and it can only ask - never decide.
"""
import re

KINDS = {
    "bone": {"system": "feet & bones", "slider": "feet", "phrases": [
        "sharp pain", "stabbing", "shooting pain", "pin point", "pinpoint", "point tender", "tender spot",
        "hurts to walk", "hurt to walk", "pain when i walk", "pain walking", "pain on the stairs", "hurts to hop",
        "hurt to hop", "pain hopping", "pain when hopping", "pain on hopping", "limp", "limping", "swelling", "swollen",
        "bruis", "shin pain", "shin hurts", "shins hurt", "bone pain", "bone hurts", "stress fracture", "stress reaction",
        "can't put weight", "cant put weight", "can't bear weight", "hurts at night", "pain at night", "throbbing",
        "numb", "tingling", "heel pain", "arch pain", "foot pain", "ankle pain", "knee pain", "achilles"]},
    "muscle": {"system": "leg muscles", "slider": "legs", "phrases": [
        "pulled a", "pulled my", "pull in my", "strain", "strained", "torn", "tweaked", "gave out", "gave way", "cramp",
        "knot in", "spasm", "can't straighten", "cant straighten", "hamstring hurts", "calf hurts", "quad hurts",
        "calf pain", "hamstring pain", "quad pain", "groin"]},
    "illness": {"system": "heart & lungs", "slider": "breathing", "phrases": [
        "fever", "chills", "chest pain", "chest tight", "tight chest", "dizzy", "lightheaded", "light headed",
        "faint", "nausea", "nauseous", "threw up", "vomit", "sick", "flu", "covid", "sore throat", "short of breath",
        "palpitation", "heart racing", "racing heart"]},
    "better": {"system": None, "slider": None, "phrases": [
        "no pain", "pain free", "pain-free", "feel great", "feeling great", "feel amazing", "feel fantastic",
        "best i've felt", "best ive felt", "fully recovered", "100%", "brand new", "fresh as"]},
}
# looser patterns: pain tied to hopping, walking or stairs within a few words, either order
PATTERNS = {
    "bone": [(r"\b(pain|hurt|hurts|hurting|ache|aches|sore)\b[^.;!?]{0,30}\b(hop|hopping|hops|walk|walking|stairs)",
              "pain when hopping or walking"),
             (r"\b(hop|hopping|hops|walk|walking|stairs)\b[^.;!?]{0,30}\b(pain|painful|hurt|hurts|hurting)\b",
              "pain when hopping or walking")],
}
NOT_ILLNESS = ("sick of", "sick and tired", "sick burn", "sick ride")
NEGATIONS = ("no", "not", "without", "never", "zero", "isn't", "isnt", "wasn't", "wasnt", "don't", "dont",
             "didn't", "didnt", "free of", "barely")
SEVERE = {"stress fracture", "can't bear weight", "cant put weight", "can't put weight", "chest pain", "faint",
          "palpitation", "hurts at night", "pain at night", "swollen", "swelling", "limp", "limping"}
CONFIRMED_AS = 6        # a confirmed bone/muscle flag reads as this on its slider


def _negated(text, start):
    before = re.findall(r"[\w']+", text[max(0, start - 30):start])[-3:]
    return any(w in NEGATIONS for w in before) or text[max(0, start - 8):start].endswith("free of ")


def find(text):
    """{kind: [phrases found]} - phrases not negated just before ("no pain", "not swollen")."""
    t = " " + (text or "").lower().replace("’", "'") + " "
    out = {}
    for kind, k in KINDS.items():
        for ph in k["phrases"]:
            for m in re.finditer(r"(?<![\w])" + re.escape(ph), t):
                if kind != "better" and _negated(t, m.start()):
                    continue
                if kind == "illness" and any(t.startswith(x, m.start()) for x in NOT_ILLNESS):
                    continue
                out.setdefault(kind, [])
                if ph not in out[kind]:
                    out[kind].append(ph)
                break
        for rx, label in PATTERNS.get(kind, []):
            for m in re.finditer(rx, t):
                if _negated(t, m.start()) or label in out.get(kind, []):
                    continue
                out.setdefault(kind, []).append(label)
                break
    return out


def flags(checkin):
    """The flags for one check-in (id, kind, words, message). Each needs the rider to confirm or dismiss it."""
    found = find(checkin.get("journal"))
    out = []
    for kind, words in found.items():
        k = KINDS[kind]
        val = checkin.get(k["slider"]) if k["slider"] else None
        severe = [w for w in words if w in SEVERE]
        if kind == "better":
            high = [(n, checkin[s]) for s, n in (("feet", "feet & bones"), ("legs", "legs"))
                    if checkin.get(s) is not None and checkin[s] >= 6]
            if not high:
                continue
            msg = (f"Your journal says \"{words[0]}\", but you rated " + " and ".join(f"{n} {v}/10" for n, v in high)
                   + ". If the sliders are too high, move them - that's what counts.")
        elif severe:
            msg = (f"Your journal mentions \"{severe[0]}\". That's worth taking seriously whatever the sliders say"
                   + (f" ({k['system']} {val}/10)" if val is not None else "") + ".")
        elif val is not None and val >= 6:
            continue                                       # the slider already says it - no contradiction
        else:
            msg = (f"Your journal mentions \"{words[0]}\", but " + (f"{k['system']} is {val}/10" if val is not None
                   else f"{k['system']} wasn't rated") + ".")
        out.append({"id": kind, "kind": kind, "words": words[:4], "system": k["system"], "severe": bool(severe),
                    "message": msg, "status": "open"})
    return out


def refresh(checkin):
    """Recompute a check-in's flags after an edit, keeping how the rider settled any that are still there."""
    before = {f["id"]: f for f in checkin.get("flags") or []}
    new = flags(checkin)
    for f in new:
        old = before.get(f["id"])
        # settled stays settled - unless the entry now says something new of that kind, which asks again
        if old and old.get("status") != "open" and set(f["words"]) <= set(old.get("words", [])):
            f["status"], f["settled"] = old["status"], old.get("settled")
    if new:
        checkin["flags"] = new
    else:
        checkin.pop("flags", None)
    return new


def settle(checkin, flag_id, action, when=None):
    if action not in ("confirm", "dismiss", "reopen"):
        raise ValueError("action is confirm, dismiss or reopen")
    for f in checkin.get("flags") or []:
        if f["id"] == flag_id:
            f["status"] = {"confirm": "confirmed", "dismiss": "dismissed", "reopen": "open"}[action]
            f["settled"] = when
            return f
    raise ValueError(f"no flag {flag_id!r} on that day")


def effective(checkin):
    """The check-in as the model reads it: a confirmed bone/muscle flag raises its slider to 6/10."""
    c = dict(checkin or {})
    for f in c.get("flags") or []:
        if f.get("status") != "confirmed":
            continue
        slider = KINDS[f["kind"]]["slider"]
        if f["kind"] in ("bone", "muscle") and (c.get(slider) or 0) < CONFIRMED_AS:
            c[slider] = CONFIRMED_AS
            c.setdefault("_flagged", []).append(slider)
        if f["kind"] == "illness":
            c["illness"] = True
    return c
