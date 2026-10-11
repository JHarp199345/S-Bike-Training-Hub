"""Saved exercise focus names; no workout or load calculation writes."""
import re

ALIASES = {
    'hip thrust machine': 'hip thrust', 'hip thruster': 'hip thrust', 'hip thrusters': 'hip thrust', 'hip thrusts': 'hip thrust',
    'lat pull down': 'lat pulldown', 'lat pull downs': 'lat pulldown', 'lat pulldowns': 'lat pulldown',
    'chest press': 'machine chest press', 'chest press machine': 'machine chest press',
    'bench press': 'barbell bench press',
}

def identity(value):
    if not isinstance(value, str): raise ValueError('Enter an exercise name')
    name = re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()
    if not name or len(value) > 80: raise ValueError('Exercise names must contain letters or numbers and fit within 80 characters')
    name = ALIASES.get(name, name)
    equipment = next((x for x in ('dumbbell', 'barbell', 'machine', 'cable', 'kettlebell') if x in name.split()), None)
    return {'key': name, 'name': name.title(), 'equipment': equipment}

def selections(data):
    return data.get('exercise_tracking', {}).get('exercises', [])

def save(data, values):
    if not isinstance(values, list) or len(values) > 50: raise ValueError('Provide up to 50 exercise names')
    output = []
    for value in values:
        item = identity(value)
        if not any(x['key'] == item['key'] for x in output): output.append(item)
    data['exercise_tracking'] = {'exercises': output}
    return output
