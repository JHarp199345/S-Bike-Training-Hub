"""tls.py - a secure (https) door to the hub for tablets and phones on the Wi-Fi (2026-10-12).

Browsers only run the game engine, share a device's tilt sensor and allow the camera on secure pages, so ride modes on
a tablet need https. The hub is its own small certificate authority:
  - hub-ca.crt / hub-ca.key: made once, kept on this computer (the key never leaves it). It is name-constrained: it can
    only vouch for home-network addresses (10.x, 172.16-31.x, 192.168.x, 127.x), .local names and localhost, never a
    real website, so installing it on a tablet can't be used against any other site.
  - hub.crt / hub.key: the hub's certificate for this computer's current Wi-Fi address and .local name, signed by that
    authority, remade when the address changes or before it expires (397 days: the most Apple devices accept).
Without the authority installed, a tablet's browser warns once that the connection isn't private (it is: it's your own
hub); install /hub-certificate on the tablet once and the warning goes away. The same pages, pairing and rules apply as
on the plain port; this is only a second door, at port + 1.
"""
import json
import shutil
import ssl
import subprocess
import time

import paths
import remote

DIR = paths.DATA / "tls"
VERSION = 2                      # 2: signed by the hub's own name-constrained authority (1 was self-signed)
CA_NAME = "S-Bike Training Hub (this computer)"
PRIVATE_NETS = ["IP:10.0.0.0/255.0.0.0", "IP:172.16.0.0/255.240.0.0", "IP:192.168.0.0/255.255.0.0",
                "IP:127.0.0.0/255.0.0.0", "DNS:local", "DNS:localhost"]


def _names():
    return sorted(set(remote.lan_addresses()) | {"localhost", "127.0.0.1"})


def _openssl(*args):
    tool = shutil.which("openssl") or "/usr/bin/openssl"
    subprocess.run([tool, *args], check=True, capture_output=True, timeout=30)


def _authority():
    key, crt = DIR / "hub-ca.key", DIR / "hub-ca.crt"
    if key.is_file() and crt.is_file():
        return key, crt
    constraints = ",".join("permitted;" + n for n in PRIVATE_NETS)
    _openssl("req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-days", "3650",
             "-subj", f"/CN={CA_NAME}", "-keyout", str(key), "-out", str(crt),
             "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
             "-addext", "keyUsage=critical,keyCertSign,cRLSign",
             "-addext", f"nameConstraints=critical,{constraints}")
    key.chmod(0o600)
    return key, crt


def ensure():
    """(certfile, keyfile) for the current addresses, made if needed; None when this computer has no openssl."""
    names = _names()
    cert, key, meta = DIR / "hub.crt", DIR / "hub.key", DIR / "names.json"
    try:
        m = json.loads(meta.read_text())
        if (cert.is_file() and key.is_file() and m.get("version") == VERSION and m.get("names") == names
                and time.time() - m.get("made", 0) < 300 * 86400):
            return cert, key
    except (OSError, ValueError, AttributeError):
        pass
    DIR.mkdir(parents=True, exist_ok=True)
    try:
        ca_key, ca_crt = _authority()
        san = ",".join(("IP:" if n.replace(".", "").isdigit() else "DNS:") + n for n in names)
        ext = DIR / "hub.ext"
        ext.write_text(f"subjectAltName={san}\nextendedKeyUsage=serverAuth\nkeyUsage=critical,digitalSignature\n"
                       "basicConstraints=critical,CA:FALSE\n")
        csr = DIR / "hub.csr"
        _openssl("req", "-new", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                 "-subj", "/CN=S-Bike Training Hub", "-keyout", str(key), "-out", str(csr))
        _openssl("x509", "-req", "-in", str(csr), "-CA", str(ca_crt), "-CAkey", str(ca_key), "-CAcreateserial",
                 "-days", "397", "-sha256", "-extfile", str(ext), "-out", str(cert))
        csr.unlink(missing_ok=True)
    except (OSError, subprocess.SubprocessError):
        return None
    key.chmod(0o600)
    meta.write_text(json.dumps({"version": VERSION, "names": names, "made": time.time()}))
    return cert, key


def authority_certificate():
    """The authority's public certificate, for a tablet to install (never the key)."""
    try:
        return (DIR / "hub-ca.crt").read_bytes()
    except OSError:
        return None


def context():
    made = ensure()
    if not made:
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(*map(str, made))
    return ctx
