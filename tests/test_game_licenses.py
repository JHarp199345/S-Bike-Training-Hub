import base64
import copy
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import game_licenses as licenses
import packs


class LicenseTest(unittest.TestCase):
    def setUp(self):
        self.secret = bytes(range(32))
        self.config = {"provider": "keygen", "account": "00000000-0000-0000-0000-000000000001",
                       "product": "00000000-0000-0000-0000-000000000002", "policy": "00000000-0000-0000-0000-000000000003",
                       "public_key": packs.public_key(self.secret).hex()}
        self.machine = "a" * 64
        relationships = {k: {"data": {"id": self.config[k]}} for k in ("account", "product", "policy")}
        self.payload = {"meta": {"issued": "2026-10-01T00:00:00Z", "expiry": "2026-10-31T00:00:00Z"},
                        "data": {"id": "m", "type": "machines", "attributes": {"fingerprint": self.machine},
                                 "relationships": {"license": {"data": {"id": "l"}}}},
                        "included": [{"id": "l", "type": "licenses", "relationships": relationships,
                                      "attributes": {"status": "ACTIVE", "suspended": False, "expiry": None}}]}
        self.now = licenses.timestamp("2026-10-13T00:00:00Z")

    def certificate(self, payload=None):
        enc = base64.b64encode(json.dumps(payload or self.payload).encode()).decode()
        envelope = {"alg": "base64+ed25519", "enc": enc,
                    "sig": base64.b64encode(packs.sign(self.secret, ("machine/" + enc).encode())).decode()}
        body = base64.b64encode(json.dumps(envelope).encode()).decode()
        return "-----BEGIN MACHINE FILE-----\n" + body + "\n-----END MACHINE FILE-----"

    def verify(self, certificate=None, **args):
        return licenses.verify_certificate(certificate or self.certificate(), self.config, args.get("machine", self.machine), args.get("now", self.now))

    def test_valid_offline(self):
        self.assertTrue(self.verify()["valid"])

    def test_copied_to_another_installation(self):
        with self.assertRaises(ValueError): self.verify(machine="b" * 64)

    def test_expired_or_not_yet_issued(self):
        for now in [licenses.timestamp("2026-11-01T00:00:00Z"), licenses.timestamp("2026-09-30T00:00:00Z")]:
            with self.assertRaises(ValueError): self.verify(now=now)

    def test_wrong_publisher_product_policy_or_suspended(self):
        for key in ["account", "product", "policy", "suspended", "expired"]:
            payload = copy.deepcopy(self.payload)
            license = payload["included"][0]
            if key == "suspended": license["attributes"]["suspended"] = True
            elif key == "expired": license["attributes"]["expiry"] = "2026-10-02T00:00:00Z"
            else: license["relationships"][key]["data"]["id"] = "wrong"
            with self.assertRaises(ValueError): self.verify(self.certificate(payload))

    def test_extended_offline_period(self):
        self.payload["meta"]["expiry"] = "2027-01-01T00:00:00Z"
        with self.assertRaises(ValueError): self.verify()

    def test_forged_signature_and_algorithm(self):
        text = self.certificate()
        body = text.splitlines()[1]
        value = json.loads(base64.b64decode(body))
        for key, replacement in [("sig", base64.b64encode(bytes(64)).decode()), ("alg", "none")]:
            forged = dict(value); forged[key] = replacement
            certificate = text.replace(body, base64.b64encode(json.dumps(forged).encode()).decode())
            with self.assertRaises(ValueError): self.verify(certificate)

    def test_free_packs_and_incomplete_configuration(self):
        with patch("hub_release.require", side_effect=AssertionError("Free Hub must not be gated")):
            self.assertTrue(licenses.require({"id": "free"})["valid"])
        with self.assertRaises(ValueError): licenses.config({"licensing": {"provider": "keygen"}})

    def test_corrupted_host_cannot_activate(self):
        manifest = {"id": "test", "licensing": self.config}
        with patch("hub_release.require", side_effect=ValueError("changed")), patch("game_licenses.request") as request:
            with self.assertRaises(ValueError): licenses.activate(manifest, "test-key")
            request.assert_not_called()

    def test_activation_sends_only_license_and_installation(self):
        manifest = {"id": "test", "licensing": self.config}
        resource = copy.deepcopy(self.payload["included"][0]); resource["id"] = "00000000-0000-0000-0000-000000000004"
        responses = [{"meta": {"valid": True}, "data": resource}, {"data": {"attributes": {"certificate": self.certificate()}}}]
        with tempfile.TemporaryDirectory() as tmp, patch("paths.DATA", pathlib.Path(tmp)), patch("hub_release.require"), patch("game_licenses.installation", return_value=self.machine), patch("game_licenses.request", side_effect=responses) as request:
            # Time is deterministic; no real Keygen request or real athlete data.
            original = licenses.verify_certificate
            with patch("game_licenses.verify_certificate", side_effect=lambda t,c,f:original(t,c,f,self.now)):
                self.assertTrue(licenses.activate(manifest, "customer-key")["valid"])
            self.assertEqual(set(request.call_args_list[0].args[2]), {"meta"})
            self.assertNotIn("ftp", str(request.call_args_list))
            self.assertNotIn("profile", str(request.call_args_list))
            self.assertTrue((pathlib.Path(tmp) / "licenses/test.cert").exists())


if __name__ == "__main__": unittest.main()
