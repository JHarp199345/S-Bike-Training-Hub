"""tls.py - a secure (https) door to the hub for tablets and phones on the Wi-Fi (2026-10-12).

Browsers only share a device's tilt sensor (and the camera) with secure pages, so ride modes that steer by leaning need
https. The hub makes its own certificate for this Mac's Wi-Fi address and .local name (no outside authority; the tablet's
browser warns once, you accept it, and the connection is encrypted from then on). It is remade when the address changes.
The same pages, pairing and rules apply as on the plain port; this is only a second door, at port + 1.
"""
import json
import shutil
import ssl
import subprocess

import paths
import remote

DIR = paths.DATA / "tls"


def _names():
    return sorted(set(remote.lan_addresses()) | {"localhost", "127.0.0.1"})


def ensure():
    """(certfile, keyfile) for the current addresses, made if needed; None when this Mac has no openssl."""
    names = _names()
    cert, key, meta = DIR / "hub.crt", DIR / "hub.key", DIR / "names.json"
    try:
        if cert.is_file() and key.is_file() and json.loads(meta.read_text()) == names:
            return cert, key
    except (OSError, ValueError):
        pass
    tool = shutil.which("openssl") or "/usr/bin/openssl"
    DIR.mkdir(parents=True, exist_ok=True)
    san = ",".join(("IP:" if n.replace(".", "").isdigit() else "DNS:") + n for n in names)
    try:
        subprocess.run([tool, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                        "-days", "825", "-subj", "/CN=S-Bike Training Hub", "-addext", f"subjectAltName={san}",
                        "-keyout", str(key), "-out", str(cert)], check=True, capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    key.chmod(0o600)
    meta.write_text(json.dumps(names))
    return cert, key


def context():
    made = ensure()
    if not made:
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(*map(str, made))
    return ctx
