"""ideas.py - famous rides to start from, for when the map is a blank page.

Each idea is a start and a finish (lat, lon); the planner routes it on real
roads, so the points only need to be near the right road. Climbs run bottom
to top the way the races and everyone else ride them.
"""
IDEAS = [
    # --- California ---
    {"region": "California", "name": "PCH: Santa Monica to Malibu", "kind": "a-b",
     "start": [34.0094, -118.4973], "end": [34.0356, -118.6775], "blurb": "Along the ocean, rolling"},
    {"region": "California", "name": "Topanga Canyon climb", "kind": "a-b",
     "start": [34.0386, -118.5816], "end": [34.1300, -118.6030], "blurb": "From the beach to the top of the canyon"},
    {"region": "California", "name": "Griffith Observatory", "kind": "a-b",
     "start": [34.1109, -118.2878], "end": [34.1184, -118.3004], "blurb": "Short, steep, famous view at the top"},
    {"region": "California", "name": "Mulholland: Sepulveda to Beverly Glen", "kind": "a-b",
     "start": [34.1285, -118.4717], "end": [34.1333, -118.4417], "blurb": "Ridge road above the city"},
    {"region": "California", "name": "Mt. Baldy Road", "kind": "a-b",
     "start": [34.1600, -117.7080], "end": [34.2700, -117.6280], "blurb": "A big one: Claremont to the ski lifts"},
    {"region": "California", "name": "Golden Gate to Sausalito", "kind": "a-b",
     "start": [37.8060, -122.4370], "end": [37.8590, -122.4852], "blurb": "Across the bridge from the Marina"},
    {"region": "California", "name": "Mt. Diablo (South Gate)", "kind": "a-b",
     "start": [37.8230, -121.9690], "end": [37.8816, -121.9142], "blurb": "Bay Area classic climb"},
    {"region": "California", "name": "Mt. Tamalpais", "kind": "a-b",
     "start": [37.9060, -122.5450], "end": [37.9290, -122.5780], "blurb": "Mill Valley up to East Peak"},
    # --- France: the Tour's roads ---
    {"region": "France", "name": "Champs-Élysées", "kind": "a-b",
     "start": [48.8656, 2.3212], "end": [48.8738, 2.2950], "blurb": "The Tour's finish: Concorde up to the Arc de Triomphe"},
    {"region": "France", "name": "Alpe d'Huez", "kind": "a-b",
     "start": [45.0556, 6.0306], "end": [45.0917, 6.0694], "blurb": "21 hairpins from Le Bourg-d'Oisans"},
    {"region": "France", "name": "Mont Ventoux from Bédoin", "kind": "a-b",
     "start": [44.1242, 5.1797], "end": [44.1740, 5.2786], "blurb": "The Giant of Provence, the hard side"},
    {"region": "France", "name": "Col du Tourmalet from Luz", "kind": "a-b",
     "start": [42.8728, -0.0028], "end": [42.9086, 0.1453], "blurb": "The Pyrenees' most-raced col"},
    {"region": "France", "name": "Col du Galibier from Valloire", "kind": "a-b",
     "start": [45.1650, 6.4290], "end": [45.0642, 6.4078], "blurb": "Over 2,600 m, high Alps"},
    {"region": "France", "name": "Col d'Izoard from Briançon", "kind": "a-b",
     "start": [44.8990, 6.6440], "end": [44.8203, 6.7350], "blurb": "Through the moonscape of the Casse Déserte"},
    {"region": "France", "name": "Loire valley loop, Amboise", "kind": "loop", "km": 30,
     "start": [47.4126, 0.9826], "blurb": "Easy châteaux country"},
]
