"""Signed application-file inventory, independent of athlete data.

This detects changed release files when this verifier is used. A modified host
can replace the verifier or lie to a browser; this is not remote attestation.
"""
import json
from pathlib import Path
import packs
import paths

FORMAT = "s-bike-hub-release-1"


def check(code=None, keys=None):
    root = Path(code or paths.CODE).resolve()
    try:
        manifest = json.loads((root / "hub-release.json").read_text())
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
            raise ValueError("Invalid Hub release inventory")
        sig = manifest.get("signature", {})
        public = (packs.TRUSTED_KEYS if keys is None else keys).get(sig.get("key"))
        if not public or not packs.verify(bytes.fromhex(public), packs.signed_bytes(manifest), bytes.fromhex(sig.get("sig", ""))):
            raise ValueError("The Hub release signature could not be verified")
        files = manifest.get("files")
        if not isinstance(files, dict) or not files:
            raise ValueError("Missing Hub application fingerprints")
        for name, digest in files.items():
            file = (root / name).resolve()
            if not file.is_relative_to(root) or not file.is_file() or packs.fingerprint(file) != digest:
                raise ValueError("Hub application files differ from the signed release")
        # An extra Python module can shadow a signed module or dependency.
        if any(p.name not in files for p in root.glob("*.py")):
            raise ValueError("The Hub contains unsigned application modules")
        return manifest, None
    except (OSError, ValueError, TypeError, AttributeError):
        return None, "This game needs an intact, signed official Hub release. Update or restore the Hub application."


def require():
    manifest, error = check()
    if error:
        raise ValueError(error)
    return manifest
