"""Checks release-kit completeness and identity-preservation comparisons."""

import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


site = load("make-download-site")
router = load("router-upgrade-data")


class ReleaseHelpers(unittest.TestCase):
    def packages(self, folder):
        for product in site.PRODUCTS:
            for arch in ("x86", "x86_64"):
                (folder / f"aspia-{product}-2.7.2-{arch}.msi").write_bytes(bytes.fromhex("d0cf11e0a1b11ae1") + product.encode())
        for name in ("aspia-2.7.2-audit-inventory-source.zip", "LICENSE.md", "README-preview.md", "build-info-x86.json", "build-info-x86_64.json"):
            (folder / name).write_text("test fixture", encoding="utf-8")

    def test_missing_architecture_cannot_be_published_as_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.packages(root)
            (root / "aspia-router-2.7.2-x86.msi").unlink()
            with self.assertRaisesRegex(ValueError, "Missing release file"):
                site.package_site(root, root / "out", "2.7.2", "a" * 40, "preview.1")
            self.assertFalse((root / "out").exists())

    def test_complete_kit_has_local_links_and_stable_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.packages(root)
            archive = site.package_site(root, root / "out", "2.7.2", "a" * 40, "preview.1")
            with zipfile.ZipFile(archive) as bundle:
                self.assertTrue(all(name.startswith("aspia-downloads/") for name in bundle.namelist()))
                manifest = json.loads(bundle.read("aspia-downloads/site/manifest.json"))
                self.assertEqual(sum(e["file"].endswith(".msi") for e in manifest["files"]), 8)
                page = bundle.read("aspia-downloads/site/index.html").decode("utf-8")
                for entry in manifest["files"]:
                    if entry["file"].endswith(".msi"):
                        self.assertIn('href="files/' + entry["file"] + '"', page)
                self.assertNotIn("releases/download", page)

    def test_router_snapshot_survives_extra_tables_but_detects_changed_keys(self):
        with sqlite3.connect(":memory:") as db:
            db.executescript('CREATE TABLE users (id INTEGER, name TEXT, "group" TEXT, salt BLOB, verifier BLOB, sessions INTEGER, flags INTEGER); CREATE TABLE hosts (id INTEGER, "key" BLOB);')
            db.execute("INSERT INTO users VALUES (1,'admin','',X'01',X'02',3,1)")
            db.execute("INSERT INTO hosts VALUES (424242,X'abcdef')")
            before = router.snapshot(db)
            db.execute("CREATE TABLE audit (id INTEGER)")
            self.assertEqual(router.snapshot(db), before)
            db.execute("UPDATE hosts SET key=X'fedcba'")
            self.assertNotEqual(router.snapshot(db), before)

    def test_empty_router_database_is_not_a_preservation_success(self):
        with sqlite3.connect(":memory:") as db:
            db.execute('CREATE TABLE users (id INTEGER, name TEXT, "group" TEXT, salt BLOB, verifier BLOB, sessions INTEGER, flags INTEGER)')
            with self.assertRaisesRegex(RuntimeError, "no users"):
                router.snapshot(db)


if __name__ == "__main__":
    unittest.main()
