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
    "feet": ("Feet and bones", {"impact": 1.0}),
}


def build(run_blocks, swim_blocks, bike_leg_ratio, run_leg_ratio=0):
    """Normalize each source to its own reference, then show the strongest.

    The map illustrates where recorded sport exposure is concentrated. Its
    shade is not a per-muscle diagnosis, injury probability, or additive dose.
    """
    source = {"impact": (run_blocks or 0) / 1.5,
              "run": max(0, run_leg_ratio or 0),
              "swim": (swim_blocks or 0) / 1.5,
              "bike": max(0, bike_leg_ratio or 0)}
    regions = {}
    for key, (name, weights) in REGIONS.items():
        parts = {sport: round(source[sport] * weight, 2) for sport, weight in weights.items() if weight}
        lead = max(parts, key=parts.get)
        regions[key] = {"name": name, "level": round(parts[lead], 2), "driver": lead,
                        "contributions": parts, "coefficients": weights}
    return {"regions": regions, "sources": {k: round(v, 2) for k, v in source.items()},
            "method": "relative participation · provisional, not measured muscle force",
            "references": ["https://pubmed.ncbi.nlm.nih.gov/22903317/",
                           "https://pubmed.ncbi.nlm.nih.gov/22278390/",
                           "https://pubmed.ncbi.nlm.nih.gov/26539511/",
                           "https://pubmed.ncbi.nlm.nih.gov/15696315/"]}
