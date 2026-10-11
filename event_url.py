"""Read one public event page into an editable preview; never schedule on fetch."""
import datetime as dt
import html
import http.client
import ipaddress
import json
import re
import socket
import ssl
import urllib.parse
from html.parser import HTMLParser

MAX_BYTES = 1_500_000
EVENT_TYPES = {'Event', 'SportsEvent'}


def public_target(value):
    try:
        url = urllib.parse.urlsplit(value)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            raise ValueError('Use a public http or https event URL without login credentials.')
        if url.port not in (None, 80 if url.scheme == 'http' else 443):
            raise ValueError('Use the website’s standard web port.')
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(url.hostname, url.port or (443 if url.scheme == 'https' else 80), type=socket.SOCK_STREAM)})
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise ValueError('Only public event websites can be imported.')
        return url, addresses
    except (socket.gaierror, TypeError) as error:
        raise ValueError('Could not find that event website.') from error


class PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, address, port, timeout):
        super().__init__(host, port, timeout=timeout)
        self.address = address
    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), self.timeout)


class PinnedHTTPS(PinnedHTTP):
    def connect(self):
        super().connect()
        self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host)


def fetch_page(value):
    current = value
    for _ in range(4):
        url, addresses = public_target(current)
        connection = (PinnedHTTPS if url.scheme == 'https' else PinnedHTTP)(url.hostname, addresses[0], url.port or (443 if url.scheme == 'https' else 80), 10)
        try:
            connection.request('GET', urllib.parse.urlunsplit(('', '', url.path or '/', url.query, '')), headers={'Host': url.hostname, 'User-Agent': 'TrainingHub-EventPreview/1.0', 'Accept': 'text/html,application/xhtml+xml', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise ValueError('This page redirects without an event address.')
                current = urllib.parse.urljoin(current, location)
                continue
            if response.status != 200:
                raise ValueError('The website did not allow this preview. Use Add your own instead.')
            if not any(kind in response.getheader('Content-Type', '').lower() for kind in ('text/html', 'application/xhtml+xml')):
                raise ValueError('Use the event’s webpage, rather than a file or image URL.')
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError('This page is too large to preview. Use a more specific event page.')
            return data.decode('utf-8', errors='replace'), current
        finally:
            connection.close()
    raise ValueError('Too many redirects. Paste the event’s final website address.')


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.scripts, self.text, self.title = {}, [], [], []
        self.script = None
        self.skip = 0
        self.in_title = False
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            key = attrs.get('property') or attrs.get('name')
            if key:
                self.meta[key.lower()] = attrs.get('content', '')
        if tag == 'script':
            self.script = [] if attrs.get('type', '').lower() == 'application/ld+json' else None
        if tag in ('script', 'style', 'noscript'):
            self.skip += 1
        if tag == 'title':
            self.in_title = True
    def handle_endtag(self, tag):
        if tag == 'script':
            if self.script is not None:
                self.scripts.append(''.join(self.script))
            self.script = None
        if tag in ('script', 'style', 'noscript'):
            self.skip = max(0, self.skip - 1)
        if tag == 'title':
            self.in_title = False
    def handle_data(self, value):
        if self.script is not None:
            self.script.append(value)
        if self.in_title:
            self.title.append(value)
        if not self.skip:
            self.text.append(value)


def nodes(value, depth=0):
    if depth > 12:
        return
    if isinstance(value, dict):
        kind = value.get('@type', [])
        kind = [kind] if isinstance(kind, str) else kind
        if any(str(k).split('/')[-1] in EVENT_TYPES for k in kind):
            yield value
        for item in value.values():
            yield from nodes(item, depth + 1)
    elif isinstance(value, list):
        for item in value[:100]:
            yield from nodes(item, depth + 1)


def clean(value, limit=300):
    if not isinstance(value, str):
        return ''
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', value))).strip()[:limit]


def date_parts(value):
    if not isinstance(value, str):
        return '', '', ''
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.date().isoformat(), parsed.strftime('%H:%M') if 'T' in value else '', parsed.strftime('%z') if parsed.tzinfo else ''
    except ValueError:
        return '', '', ''


def sport_for(text):
    for sport, pattern in [('tri', r'\b(triathlon|duathlon|swimrun)\b'), ('gym', r'\b(powerlifting|weightlifting|lifting meet|strongman)\b'), ('swim', r'\b(swim|swimming|open.water)\b'), ('bike', r'\b(cycling|bicycle|bike|gravel|cyclocross)\b'), ('run', r'\b(run|running|marathon|5k|10k|trail race|spartan|obstacle|mud run)\b')]:
        if re.search(pattern, text, re.I):
            return sport
    return 'other'


def parse_page(content, source_url):
    page = Page(); page.feed(content)
    title = clean(page.meta.get('og:title') or ''.join(page.title), 80)
    description = clean(page.meta.get('description') or page.meta.get('og:description'), 600)
    text = clean(' '.join(page.text), 40_000)
    structured = []
    for script in page.scripts[:30]:
        try:
            structured.extend(nodes(json.loads(script)))
        except (ValueError, TypeError):
            pass
    candidates, seen = [], set()
    for node in structured[:50] or [{}]:
        name = clean(node.get('name') or title, 80)
        date, time, timezone = date_parts(node.get('startDate'))
        location = node.get('location') or {}
        location = location[0] if isinstance(location, list) and location else location
        address = location.get('address') or {} if isinstance(location, dict) else {}
        city = clean(address.get('addressLocality')) if isinstance(address, dict) else ''
        venue = clean(location.get('name')) if isinstance(location, dict) else clean(location)
        details = clean(node.get('description') or description, 600)
        evidence = ' '.join([name, details])
        distances = list(dict.fromkeys(re.findall(r'\b\d+(?:\.\d+)?\s*(?:km|kilometers?|kilometres?|miles?|yards?|meters?|metres?|k)\b', evidence, re.I)))
        images = node.get('image') or page.meta.get('og:image') or []
        images = images if isinstance(images, list) else [images]
        image_urls = []
        for image in images[:5]:
            if isinstance(image, dict):image = image.get('url') or image.get('contentUrl')
            if isinstance(image, str):
                resolved = urllib.parse.urljoin(source_url, image)
                from event_directory import safe_url
                if safe_url(resolved):image_urls.append(resolved)
        candidate = {'name': name, 'date': date, 'time': time, 'timezone': timezone, 'sport': sport_for(evidence), 'distance': distances[0] if len(distances) == 1 else '', 'distance_choices': distances, 'location': city or venue, 'website': source_url, 'source_url': source_url, 'note': details[:300], 'image_candidates': image_urls, 'evidence': 'Structured event fields' if node else 'Page title and description', 'missing': [key for key, value in [('name', name), ('date', date), ('sport', sport_for(evidence) != 'other'), ('distance', len(distances) == 1)] if not value]}
        identity = (name, date, time)
        if identity not in seen:
            candidates.append(candidate);seen.add(identity)
    return {'candidates': candidates, 'source_url': source_url, 'notice': 'Review the date, category and distance before approving. Blank fields were not found reliably. Previewing does not schedule the event.', 'page_excerpt': text[:1200] if not structured else ''}


def preview(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Paste a public event webpage URL.')
    content, source = fetch_page(value.strip())
    return parse_page(content, source)
