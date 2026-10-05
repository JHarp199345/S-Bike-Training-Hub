"""Exercise the assets through the Hub, including dependencies needed by WebGL.

Missing local module imports and GLB textures leave a blank or untextured world
even when the entry script parses successfully.
"""
import asyncio
import io
import json
import pathlib
import re
import struct
import sys
import tempfile
import types
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import mapserver
import setup_maps


class SceneryAssets(unittest.TestCase):
    def served(self, path):
        result = asyncio.run(mapserver.handle(types.SimpleNamespace(), b"GET", path, b"", "localhost"))
        self.assertIsNotNone(result, path)
        self.assertEqual(result[0], 200, path)
        return result

    def test_local_module_dependencies_resolve(self):
        pending = ["/web/course-haunted.js"]
        visited = set()
        while pending:
            path = pending.pop()
            if path in visited:
                continue
            visited.add(path)
            result = self.served(path)
            self.assertEqual(result[1], "text/javascript")
            for dependency in re.findall(r"^\s*import\s+(?:[^;]*?\bfrom\s*)?['\"]([^'\"]+)['\"]", result[2].decode(), re.M):
                self.assertTrue(dependency.startswith("."), (path, dependency))
                parts = pathlib.PurePosixPath(path).parent / dependency
                import posixpath
                pending.append(posixpath.normpath(str(parts)))
        self.assertGreaterEqual(len(visited), 6)

    def test_models_textures_and_animation_clips_are_served(self):
        models = sorted((mapserver.WEB / "graveyard").glob("*.glb"))
        self.assertGreaterEqual(len(models), 20)
        for model in models:
            result = self.served("/web/graveyard/" + model.name)
            self.assertEqual(result[1], "model/gltf-binary")
            blob = result[2]
            magic, version, total = struct.unpack_from("<4sII", blob)
            self.assertEqual((magic, version, total), (b"glTF", 2, len(blob)))
            chunk_size, chunk_type = struct.unpack_from("<I4s", blob, 12)
            self.assertEqual(chunk_type, b"JSON")
            gltf = json.loads(blob[20:20 + chunk_size])
            for image in gltf.get("images", []):
                uri = image.get("uri", "")
                if uri and not uri.startswith("data:"):
                    texture = self.served("/web/graveyard/" + uri)
                    self.assertEqual(texture[1], "image/png")
                    self.assertTrue(texture[2].startswith(b"\x89PNG\r\n\x1a\n"))
            if model.stem.startswith("character-"):
                clips = {clip["name"] for clip in gltf.get("animations", [])}
                self.assertIn("idle", clips)

    def test_static_traversal_is_rejected(self):
        for path in ["/web/graveyard/../../regions.json", "/web/graveyard/Textures/../../../regions.json"]:
            result = asyncio.run(mapserver.handle(types.SimpleNamespace(), b"GET", path, b"", "localhost"))
            self.assertEqual(result[0], 404)

    def test_map_archive_rejects_parent_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("../escaped.txt", "outside")
            with self.assertRaises(ValueError):
                setup_maps.unzip(archive.getvalue(), root / "maps")
            self.assertFalse((root / "escaped.txt").exists())


if __name__ == "__main__":
    unittest.main()
