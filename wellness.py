"""wellness.py - validated self-report instruments for check-ins.

  Daily: the Hooper questionnaire (Hooper & Mackinnon 1995): fatigue, sleep quality, stress and muscle soreness,
      each 1-7 (1 = very, very good / low, 7 = very, very bad / high); their sum is the Hooper index (4-28,
      higher = worse). Plus pain by site on a 0-10 numeric rating (0 = none), kept apart from soreness because pain
      is a possible-injury signal and soreness is a normal training response (pain-monitoring model,
      Silbernagel et al. 2007).
  Weekly: the OSTRC Overuse Injury Questionnaire (Clarsen et al. 2013): four questions per problem area, scored
      0-100 for severity.

The Hub's own questions (site soreness 1-10, breathing, gut call, hop test, journal) are unchanged and stay labelled
as the Hub's. Answers are stored with the instrument version; earlier records keep their scales.
"""

VERSION = "checkin-v2"
HOOPER = {
    "hooper_fatigue": ("Fatigue", "1 very, very low · 7 very, very high"),
    "hooper_sleep": ("Sleep quality last night", "1 very, very good · 7 very, very bad"),
    "hooper_stress": ("Stress", "1 very, very low · 7 very, very high"),
    "hooper_soreness": ("Muscle soreness, overall", "1 very, very low · 7 very, very high"),
}
PAIN_SITES = {"feet": "Feet & lower legs", "legs": "Knees & legs", "hips": "Hips & lower back",
              "shoulders": "Shoulders", "other": "Somewhere else"}

# OSTRC Overuse Injury Questionnaire (Clarsen et al. 2013): answer -> points; severity is the sum (0-100).
OSTRC = {
    "participation": ("Have you had any difficulties participating in normal training and competition due to problems in this area during the past week?",
                      [("Full participation without problems", 0), ("Full participation, but with problems", 8),
                       ("Reduced participation due to problems", 17), ("Cannot participate due to problems", 25)]),
    "volume": ("To what extent have you reduced your training volume due to problems in this area during the past week?",
               [("No reduction", 0), ("To a minor extent", 6), ("To a moderate extent", 13), ("To a major extent", 19),
                ("Cannot participate at all", 25)]),
    "performance": ("To what extent have problems in this area affected your performance during the past week?",
                    [("No effect", 0), ("To a minor extent", 6), ("To a moderate extent", 13), ("To a major extent", 19),
                     ("Cannot participate at all", 25)]),
    "pain": ("To what extent have you experienced pain in this area related to your sport during the past week?",
             [("No pain", 0), ("Mild pain", 8), ("Moderate pain", 17), ("Severe pain", 25)]),
}
OSTRC_AREAS = {"lower_leg": "Lower leg & Achilles", "foot": "Foot & ankle", "knee": "Knee", "hip": "Hip & groin",
               "low_back": "Lower back", "shoulder": "Shoulder", "other": "Other area"}


def _int(v, lo, hi, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v) or not lo <= v <= hi:
        raise ValueError(f"{what} is a whole number {lo}-{hi}")
    return int(v)


def clean_daily(fields):
    """The validated daily answers present in `fields`, ready to store."""
    out = {}
    for k, (name, _) in HOOPER.items():
        if fields.get(k) is not None:
            out[k] = _int(fields[k], 1, 7, name)
    if "pain" in fields:
        pain = fields["pain"] or {}
        if not isinstance(pain, dict) or any(k not in PAIN_SITES for k in pain):
            raise ValueError("pain is {site: 0-10} for " + ", ".join(PAIN_SITES))
        out["pain"] = {k: _int(v, 0, 10, PAIN_SITES[k] + " pain") for k, v in pain.items() if v is not None}
    if out:
        out["scale_version"] = VERSION
    return out


def hooper_index(c):
    """Sum of the four Hooper items, or None unless all four were answered."""
    vals = [c.get(k) for k in HOOPER]
    return sum(vals) if all(v is not None for v in vals) else None


def clean_ostrc(entries):
    """[{area, participation, volume, performance, pain}] with answers as option indexes -> scored entries."""
    if entries in (None, []):
        return []
    if not isinstance(entries, list):
        raise ValueError("ostrc is a list of problem areas")
    out = []
    for e in entries:
        if not isinstance(e, dict) or e.get("area") not in OSTRC_AREAS:
            raise ValueError("ostrc area is one of " + ", ".join(OSTRC_AREAS))
        row = {"area": e["area"]}
        for q, (_, options) in OSTRC.items():
            i = _int(e.get(q), 0, len(options) - 1, "OSTRC " + q)
            row[q] = {"answer": i, "points": options[i][1]}
        row["severity"] = sum(row[q]["points"] for q in OSTRC)
        # Substantial problem (Clarsen et al. 2013): moderate or greater reduction in volume or performance, or unable to participate.
        row["substantial"] = row["participation"]["points"] == 25 or row["volume"]["points"] >= 13 or row["performance"]["points"] >= 13
        out.append(row)
    return out
