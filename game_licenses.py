"""Keygen machine certificates for paid packs; no athlete data leaves the Hub.

Only the customer's license and a random installation ID are sent to Keygen.
Certificates are signed, bounded to 30 days, and stored outside application files.
This is a local enforcement mechanism, not proof of an untampered running host.
"""
import base64
import datetime as dt
import json
import os
import re
import secrets
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
import packs
import paths
import hub_release

TTL = 30 * 86400
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_installation_lock = threading.Lock()


def config(manifest):
    value = manifest.get("licensing")
    if value is None:
        return None  # Existing inspection/free packs continue to work.
    if not isinstance(value, dict) or value.get("provider") != "keygen":
        raise ValueError("Unsupported game licensing configuration")
    for key in ("account", "product", "policy"):
        if not isinstance(value.get(key), str) or not UUID.fullmatch(value[key]):
            raise ValueError("The publisher has not finished configuring game licensing")
    if not re.fullmatch(r"[0-9a-f]{64}", str(value.get("public_key", ""))):
        raise ValueError("The publisher has not supplied the license verification key")
    return value


def private_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(prefix=".license-", dir=path.parent)
    temp = Path(filename)
    try:
        with os.fdopen(fd, "w") as file:
            file.write(value)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def installation():
    path = paths.DATA / "licenses/installation"
    with _installation_lock:
        if not path.exists():
            private_write(path, secrets.token_hex(32))
        value = path.read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("The saved game installation ID is invalid")
    return value


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Missing certificate dates")
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Certificate dates must include a timezone")
    return result.timestamp()


def relation(resource, name):
    return resource.get("relationships", {}).get(name, {}).get("data", {}).get("id")


def verify_certificate(text, settings, fingerprint, now=None):
    if not isinstance(text, str) or len(text) > 131072:
        raise ValueError("Invalid license certificate")
    prefix, suffix = "-----BEGIN MACHINE FILE-----", "-----END MACHINE FILE-----"
    stripped = text.strip()
    if not stripped.startswith(prefix) or not stripped.endswith(suffix):
        raise ValueError("Expected a Keygen machine certificate")
    try:
        encoded = "".join(stripped[len(prefix):-len(suffix)].split())
        envelope = json.loads(base64.b64decode(encoded, validate=True))
        if envelope.get("alg") != "base64+ed25519":
            raise ValueError("Unsupported certificate signature algorithm")
        message = ("machine/" + envelope["enc"]).encode()
        signature = base64.b64decode(envelope["sig"], validate=True)
        if not packs.verify(bytes.fromhex(settings["public_key"]), message, signature):
            raise ValueError("The license certificate signature is invalid")
        payload = json.loads(base64.b64decode(envelope["enc"], validate=True))
        meta, machine = payload["meta"], payload["data"]
        issued, expires = timestamp(meta["issued"]), timestamp(meta["expiry"])
        now = dt.datetime.now(dt.timezone.utc).timestamp() if now is None else now
        if not issued <= now < expires or expires - issued > TTL + 60:
            raise ValueError("Reconnect to renew this game's offline license")
        if machine.get("type") != "machines" or machine["attributes"].get("fingerprint") != fingerprint:
            raise ValueError("This game license belongs to another installation")
        license_id = relation(machine, "license")
        license = next((r for r in payload.get("included", []) if r.get("type") == "licenses" and r.get("id") == license_id), None)
        if not license or any(relation(license, k) != settings[k] for k in ("account", "product", "policy")):
            raise ValueError("This license is for another game or publisher")
        attr = license["attributes"]
        if attr.get("suspended") or attr.get("status") != "ACTIVE":
            raise ValueError("This game license is not active")
        if attr.get("expiry") and timestamp(attr["expiry"]) <= now:
            raise ValueError("This game license has expired")
        return {"valid": True, "offline_until": meta["expiry"]}
    except (KeyError, TypeError, AttributeError, StopIteration, UnicodeError) as error:
        raise ValueError("Malformed game license certificate") from error


def require(manifest):
    settings = config(manifest)
    if settings is None:
        return {"valid": True, "license_required": False}
    hub_release.require()
    try:
        certificate = (paths.DATA / "licenses" / (manifest["id"] + ".cert")).read_text()
    except OSError as error:
        raise ValueError("Activate this game with the license supplied with your purchase") from error
    return verify_certificate(certificate, settings, installation())


def request(settings, endpoint, payload=None, license_key=None):
    # Fixed HTTPS destination; signed manifests cannot redirect credentials elsewhere.
    url = f'https://api.keygen.sh/v1/accounts/{settings["account"]}/{endpoint}'
    headers = {"Accept": "application/vnd.api+json", "Content-Type": "application/vnd.api+json"}
    if license_key:
        headers["Authorization"] = "License " + license_key
    data = json.dumps(payload).encode() if payload is not None else None
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url, data=data, headers=headers), timeout=12) as response:
            body = response.read(131073)
        if len(body) > 131072:
            raise ValueError("License service response is too large")
        return json.loads(body)
    except (urllib.error.URLError, OSError) as error:
        raise ValueError("Could not activate the game. Check your license and internet connection.") from error


def activate(manifest, license_key):
    settings = config(manifest)
    if settings is None:
        raise ValueError("This game does not require activation")
    hub_release.require()
    if not isinstance(license_key, str) or not 1 <= len(license_key.strip()) <= 1024 or any(ord(c) < 33 for c in license_key.strip()):
        raise ValueError("Enter a valid game license key")
    license_key = license_key.strip()
    fingerprint = installation()
    result = request(settings, "licenses/actions/validate-key", {"meta": {"key": license_key,
                     "scope": {"product": settings["product"], "policy": settings["policy"], "fingerprint": fingerprint}}})
    license = result.get("data") or {}
    if any(relation(license, k) != settings[k] for k in ("account", "product", "policy")) or not UUID.fullmatch(str(license.get("id", ""))):
        raise ValueError("The license is not for this game")
    meta = result.get("meta", {})
    if not meta.get("valid"):
        if meta.get("code") not in ("NO_MACHINE", "NO_MACHINES", "FINGERPRINT_SCOPE_MISMATCH"):
            raise ValueError("The license is not valid for this installation")
        request(settings, "machines", {"data": {"type": "machines", "attributes": {"fingerprint": fingerprint},
                "relationships": {"license": {"data": {"type": "licenses", "id": license["id"]}}}}}, license_key)
        result = request(settings, "licenses/actions/validate-key", {"meta": {"key": license_key,
                         "scope": {"product": settings["product"], "policy": settings["policy"], "fingerprint": fingerprint}}})
        if not result.get("meta", {}).get("valid"):
            raise ValueError("The license could not be activated")
    # The API accepts a machine fingerprint as the path identifier.
    result = request(settings, f"machines/{fingerprint}/actions/check-out?algorithm=base64%2Bed25519&ttl={TTL}&include=license",
                     {"meta": {}}, license_key)
    certificate = result.get("data", {}).get("attributes", {}).get("certificate")
    verified = verify_certificate(certificate, settings, fingerprint)
    private_write(paths.DATA / "licenses" / (manifest["id"] + ".cert"), certificate)
    return verified
