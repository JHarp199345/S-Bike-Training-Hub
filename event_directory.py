"""Bounded public-event lookup. Never sends athlete records to the provider."""
import datetime as dt
import json
import os
import threading
import time
import urllib.parse
import urllib.request

_lock = threading.Lock()
_cache = {}
TYPES = {'run': 'running_race', 'bike': 'bike_race', 'swim': 'swim', 'tri': 'triathlon', 'obstacle': 'obstacle_course'}


def safe_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        url = urllib.parse.urlsplit(value)
    except ValueError:
        return None
    return value if url.scheme in ('http', 'https') and url.hostname and not url.username and not url.password else None


def metadata(data):
    data = data if isinstance(data, dict) else {}
    result = {}
    for field in ('website', 'source_url', 'promotion_url'):
        url = safe_url(data.get(field))
        if url:
            result[field] = url
    for field in ('source', 'source_id', 'location', 'timezone', 'time', 'distance'):
        if isinstance(data.get(field), str):
            result[field] = data[field][:180]
    # Only the athlete's explicit permission attestation activates optional artwork.
    if data.get('artwork_permission') is True and safe_url(data.get('organizer_artwork')):
        import event_url
        event_url.public_target(data['organizer_artwork'])
        result['organizer_artwork'] = data['organizer_artwork']
        result['artwork_permission'] = True
    return result


def normalize(payload, start, end):
    out = []
    for item in payload.get('races', [])[:30]:
        race = item.get('race', {})
        if race.get('is_private_race') == 'T' or race.get('is_draft_race') == 'T':
            continue
        for event in race.get('events', [])[:50]:
            if event.get('volunteer') == 'T':
                continue
            try:
                when = dt.datetime.strptime(event['start_time'], '%m/%d/%Y %H:%M')
            except (ValueError, KeyError, TypeError):
                continue
            date = when.date().isoformat()
            if not start <= date <= end:
                continue
            kind = event.get('event_type', '')
            sport = next((s for s, kinds in {'tri': ['triathlon', 'duathlon', 'aqua_bike', 'swim_run'], 'swim': ['swim'], 'bike': ['bike_race', 'bike_ride', 'mountain_bike_race', 'gravel_grinder', 'fundraising_ride'], 'run': ['running_race', 'running_only', 'trail_race', 'ultra', 'obstacle_course', 'race_walk', 'virtual_race']}.items() if kind in kinds), 'other')
            address = race.get('address') or {}
            source_id = f"{race.get('race_id')}:{event.get('event_id')}:{date}"
            out.append({'name': str(race.get('name') or event.get('name') or 'Event')[:80], 'category': str(event.get('name') or '')[:120], 'date': date, 'kind': 'race', 'sport': sport, **metadata({'source': 'RunSignup', 'source_id': source_id, 'source_url': race.get('url'), 'website': race.get('external_race_url') or race.get('url'), 'location': ', '.join(str(address.get(k)) for k in ('city', 'state', 'country_code') if address.get(k)), 'timezone': race.get('timezone'), 'time': when.strftime('%H:%M'), 'distance': str(event.get('distance') or '')})})
    return sorted(out, key=lambda e: (e['date'], e['name'], e['source_id']))[:100]


def search(query):
    token = os.environ.get('HUB_RUNSIGNUP_API_REG', '')
    secret = os.environ.get('HUB_RUNSIGNUP_API_REG_SECRET', '')
    if not token or not secret:
        return {'status': 'setup_required', 'events': [], 'message': 'Event search needs the Hub’s RunSignup developer registration. You can browse the directories below or add an event yourself.'}
    start = dt.date.fromisoformat(query.get('start') or dt.date.today().isoformat())
    end = dt.date.fromisoformat(query.get('end') or (start + dt.timedelta(days=365)).isoformat())
    if end < start or (end - start).days > 366:
        raise ValueError('Choose a date range of up to one year.')
    sport = query.get('sport', '')
    if sport not in ('', *TYPES):
        raise ValueError('This directory does not cover that sport. Use its official directory link.')
    params = {'format': 'json', 'events': 'T', 'results_per_page': 30, 'sort': 'date ASC', 'start_date': start.isoformat(), 'end_date': end.isoformat(), 'search_start_date_only': 'T'}
    for key in ('name', 'city', 'state', 'country'):
        value = query.get(key, '').strip()[:100]
        if value:
            params[key] = value
    if sport:
        params['event_type'] = TYPES[sport]
    key = tuple(sorted(params.items()))
    # One request at a time; short bounded cache, not a bulk directory mirror.
    with _lock:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < 300:
            return cached[1]
        params['rsu_api_reg'] = token
        req = urllib.request.Request('https://api.runsignup.com/rest/races?' + urllib.parse.urlencode(params), headers={'X-RSU-API-REG-SECRET': secret, 'User-Agent': 'S-Bike-Training-Hub-EventSearch'})
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Directory response was too large. Narrow your search.')
        payload = json.loads(raw)
        if not isinstance(payload, dict) or 'error' in payload:
            raise ValueError('The directory could not complete this search.')
        result = {'status': 'ready', 'events': normalize(payload, start.isoformat(), end.isoformat()), 'message': 'RunSignup listings · first 30 matching races. Narrow the search for more specific results.'}
        if len(_cache) >= 30:
            _cache.clear()
        _cache[key] = (time.monotonic(), result)
        return result
