import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import hub_release
import packs


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "panel.py").write_text("# official code\n")
        self.secret = bytes(range(32))
        self.keys = {"fixture": packs.public_key(self.secret).hex()}
        self.manifest = {"format": hub_release.FORMAT, "version": "fixture",
                         "files": {"panel.py": packs.fingerprint(self.root / "panel.py")}}
        self.sign()

    def sign(self):
        self.manifest["signature"] = {"key": "fixture", "sig": packs.sign(self.secret, packs.signed_bytes(self.manifest)).hex()}
        (self.root / "hub-release.json").write_text(json.dumps(self.manifest))

    def check(self):
        return hub_release.check(self.root, self.keys)[1]

    def test_original_and_personal_data_changes(self):
        self.assertIsNone(self.check())
        (self.root / "coach.json").write_text('{"reports": []}')
        (self.root / "profile.json").write_text('{"ftp": 200}')
        self.assertIsNone(self.check())

    def test_changed_code(self):
        (self.root / "panel.py").write_text("# patched code\n")
        self.assertIsNotNone(self.check())

    def test_added_module(self):
        (self.root / "urllib.py").write_text("# shadow dependency\n")
        self.assertIsNotNone(self.check())

    def test_changed_inventory_without_signature(self):
        self.manifest["version"] = "fake"
        (self.root / "hub-release.json").write_text(json.dumps(self.manifest))
        self.assertIsNotNone(self.check())

    def test_unknown_publisher_missing_file_and_traversal(self):
        self.assertIsNotNone(hub_release.check(self.root, {})[1])
        self.manifest["files"] = {"../outside.py": "0" * 64}
        self.sign()
        self.assertIsNotNone(self.check())
        self.manifest["files"] = {"missing.py": "0" * 64}
        self.sign()
        self.assertIsNotNone(self.check())

    def test_malformed_inventory(self):
        for value in [[], None, {"format": hub_release.FORMAT, "signature": []}]:
            (self.root / "hub-release.json").write_text(json.dumps(value))
            self.assertIsNotNone(self.check())


if __name__ == "__main__":
    unittest.main()
