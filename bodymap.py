"""Display-oriented regional load map.

Participation coefficients are provisional, qualitative biomechanical priors.
They are not measured force percentages and are not added to the training score.
"""

REGIONS = {
    "shoulders": ("Shoulders", {"swim": 1.0, "bike": 0.05}),
    "scapula": ("Scapular muscles", {"swim": 0.82, "bike": 0.12}),
    "lats": ("Latissimus dorsi", {"swim": 0.88, "bike": 0.08}),
    "serratus": ("Serratus anterior", {"swim": 0.70, "bike": 0.08}),
    "pecs": ("Pectorals", {"swim": 0.64, "bike": 0.04}),
    "traps": ("Trapezius", {"swim": 0.68, "bike": 0.12}),
    "trunk": ("Trunk and back", {"swim": 0.50, "run": 0.30, "bike": 0.32}),
    "hip_flexors": ("Hip flexors", {"swim": 0.32, "run": 0.62, "bike": 0.45}),
    "glutes": ("Glutes", {"swim": 0.28, "run": 0.70, "bike": 0.75}),
    "quads": ("Quadriceps", {"swim": 0.27, "run": 0.75, "bike": 1.0}),
    "hamstrings": ("Hamstrings", {"swim": 0.25, "run": 0.70, "bike": 0.50}),
    "calves": ("Calves and Achilles", {"swim": 0.20, "run": 0.45, "bike": 0.20, "impact": 1.0}),
    # finer regions for lifting and functional work (lifting.py); the sports reach them lightly
    "abs": ("Abdominals", {"swim": 0.30, "run": 0.20, "bike": 0.15}),
    "obliques": ("Obliques", {"swim": 0.40, "run": 0.20, "bike": 0.10}),
    "lower_back": ("Lower back", {"swim": 0.30, "run": 0.25, "bike": 0.30}),
    "adductors": ("Adductors", {"swim": 0.20, "run": 0.40, "bike": 0.20}),
    "biceps": ("Biceps", {"swim": 0.20}),
    "triceps": ("Triceps", {"swim": 0.45}),
    "forearms": ("Forearms and grip", {"swim": 0.20, "bike": 0.05}),
    "neck": ("Neck", {"swim": 0.15, "bike": 0.10}),
    "feet": ("Feet and bones", {"impact": 1.0}),
}


def build(run_blocks, swim_blocks, bike_leg_ratio, run_leg_ratio=0, lift=None, swim_leg_ratio=None):
    """Normalize each source to its own reference, then show the strongest.

    The map illustrates where recorded sport exposure is concentrated. Its
    shade is not a per-muscle diagnosis, injury probability, or additive dose.
    """
    source = {"impact": (run_blocks or 0) / 1.5,
              "run": max(0, run_leg_ratio or 0),
              "swim": (swim_blocks or 0) / 1.5,
              "bike": max(0, bike_leg_ratio or 0)}
    if swim_leg_ratio is not None:
        source["swim_kick"] = max(0, swim_leg_ratio)
    regions = {}
    for key, (name, weights) in REGIONS.items():
        parts = {sport: round(source[sport] * weight, 2) for sport, weight in weights.items() if weight}
        if swim_leg_ratio is not None and key in ("hip_flexors", "glutes", "quads", "hamstrings", "calves", "adductors"):
            parts.pop("swim", None)
            parts["swim_kick"] = round(source["swim_kick"] * weights.get("swim", 0), 2)
        if (lift or {}).get(key):                                   # lifting lands on the regions each exercise named
            parts["lift"] = round(lift[key] / 1.5, 2)
        lead = max(parts, key=parts.get)
        regions[key] = {"name": name, "level": round(parts[lead], 2), "driver": lead,
                        "contributions": parts, "coefficients": weights,
                        "active_sources":[s for s,v in parts.items() if v>=.1],
                        "overlap_index":round(sum(v for v in parts.values() if v>=.1),2),
                        "shared":sum(v>=.1 for v in parts.values())>=2}
    if lift:
        source["lift"] = max(lift.values()) / 1.5
    return {"regions": regions, "sources": {k: round(v, 2) for k, v in source.items()},
            "method": "relative participation · provisional, not measured muscle force",
            "references": ["https://pubmed.ncbi.nlm.nih.gov/22903317/",
                           "https://pubmed.ncbi.nlm.nih.gov/22278390/",
                           "https://pubmed.ncbi.nlm.nih.gov/26539511/",
                           "https://pubmed.ncbi.nlm.nih.gov/15696315/"]}


def overlap_advice(body, sport, regions=None):
    """Provisional scheduling caution; normalized contributions are not tissue doses."""
    notes=[]
    for key,r in body.get("regions",{}).items():
        if regions is not None and key not in regions: continue
        participation=REGIONS.get(key,("",{}))[1].get(sport,0)
        if regions is None and participation<.2: continue
        if r.get("shared") and r.get("overlap_index",0)>=1:
            names=", ".join(r.get("active_sources",[]))
            notes.append(f"shared {r['name'].lower()} exposure ({names}); keep work easy and review the response")
    return notes[:3]


def from_state(state):
    """Build recommendations from the current metric values, not a stale rendered map."""
    systems=state.get("systems") or {}
    mechanical=((systems.get("impact") or {}).get("tissue") or {}).get("remodeling") or {}
    muscle=systems.get("muscle") or {};usual=max(muscle.get("usual_week") or 1,1)
    sports=state.get("sports_last7") or {}
    leg=lambda sport:(sports.get(sport) or {}).get("muscle",0)/usual if muscle.get("last7",0)>0 else 0
    lifts={k:v["blocks"] for k,v in ((state.get("lifting") or {}).get("regions") or {}).items()}
    return build(None if (state.get("running_response") or {}).get("active") else mechanical.get("score"),(state.get("swim_recovery") or {}).get("score"),leg("bike"),leg("run"),lifts,swim_leg_ratio=leg("swim"))
