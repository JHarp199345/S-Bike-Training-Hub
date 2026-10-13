"""The hub's secure door: its own certificate authority, limited to home-network addresses, signs the hub's certificate."""
import os, sys, pathlib, shutil, subprocess, tempfile
tmp = tempfile.mkdtemp()
os.environ["S_BIKE_HUB_DATA"] = tmp
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
tool = shutil.which("openssl") or "/usr/bin/openssl"
if not pathlib.Path(tool).exists():
    print("SKIP no openssl"); raise SystemExit
import tls
made = tls.ensure()
assert made and tls.context() is not None
d = pathlib.Path(tmp) / "tls"
run = lambda *a: subprocess.run([tool, *a], capture_output=True, text=True)
assert run("verify", "-CAfile", str(d / "hub-ca.crt"), str(d / "hub.crt")).returncode == 0, "hub certificate signed by the hub's authority"
ext = run("x509", "-in", str(d / "hub-ca.crt"), "-noout", "-ext", "nameConstraints").stdout
assert "IP:192.168.0.0/255.255.0.0" in ext and "DNS:local" in ext, "the authority only covers home networks"
if sys.platform != "win32":  # Windows uses ACLs, not these POSIX permission bits.
    assert (d / "hub-ca.key").stat().st_mode & 0o777 == 0o600 and (d / "hub.key").stat().st_mode & 0o777 == 0o600
assert tls.authority_certificate().startswith(b"-----BEGIN CERTIFICATE-----"), "the download is the public certificate"
assert b"PRIVATE" not in tls.authority_certificate()
# a certificate for a real website, signed by the hub's authority, is refused
(d / "x.ext").write_text("subjectAltName=DNS:www.example.com\n")
run("req", "-new", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-subj", "/CN=x", "-keyout", str(d / "x.key"), "-out", str(d / "x.csr"))
run("x509", "-req", "-in", str(d / "x.csr"), "-CA", str(d / "hub-ca.crt"), "-CAkey", str(d / "hub-ca.key"), "-CAcreateserial", "-days", "2", "-extfile", str(d / "x.ext"), "-out", str(d / "x.crt"))
assert run("verify", "-CAfile", str(d / "hub-ca.crt"), str(d / "x.crt")).returncode != 0, "a real website's name is outside the authority's limits"
assert tls.ensure() == made, "kept while the addresses don't change"
print("PASS secure door: hub authority limited to home networks, hub certificate signed by it, keys private, websites refused")
