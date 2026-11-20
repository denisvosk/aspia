"""Checks release-kit completeness and identity-preservation comparisons."""

import importlib.util
import json
import shutil
import sqlite3
import sys
import tempfile
import time
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
inventory = load("test-inventory-worker")


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

    def test_inventory_probe_preserves_arbitrary_binary_pipes(self):
        payload = bytes(range(256)) * 40
        code, output, errors = inventory.run_bounded(
            [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
            timeout=5, stdout_limit=len(payload), data=payload)
        self.assertEqual((code, output, errors), (0, payload, b""))

    def test_inventory_probe_rejects_excess_output(self):
        with self.assertRaisesRegex(inventory.ProbeFailure, "stdout exceeded"):
            inventory.run_bounded(
                [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x' * 131073)"],
                timeout=5, stdout_limit=131072)

    def test_inventory_probe_terminates_a_stalled_worker(self):
        started = time.monotonic()
        with self.assertRaisesRegex(inventory.ProbeFailure, "deadline"):
            inventory.run_bounded(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                timeout=0.2, stdout_limit=131072)
        self.assertLess(time.monotonic() - started, 5)

    def test_inventory_probe_rejects_empty_identity_and_old_snapshot(self):
        snapshot = ('collection_id: "\\000\\377abcdefghijklmn"\n'
                    'collected_at: 1000\ncomputer_name: "runner"\nos_name: "Windows"\n'
                    'os_version: "10.0"\nos_arch: "x86_64"\ncpu_model: "Virtual CPU"\n'
                    'cpu_packages: 1\ncpu_cores: 2\ncpu_threads: 4\ncpu_clock_mhz: 2400\n'
                    'ram_bytes: 8589934592\n')
        inventory.validate_snapshot(snapshot, 1000, 1001)
        with self.assertRaisesRegex(inventory.ProbeFailure, "nonempty"):
            inventory.validate_snapshot(snapshot.replace('computer_name: "runner"', 'computer_name: ""'), 1000, 1001)
        with self.assertRaisesRegex(inventory.ProbeFailure, "timestamp"):
            inventory.validate_snapshot(snapshot, 2000, 2001)

    @unittest.skipUnless(shutil.which("protoc"), "protoc is installed by the Linux CI gate")
    def test_inventory_probe_uses_real_schema_decoder(self):
        protoc = shutil.which("protoc")
        schema = Path(__file__).resolve().parents[1] / "source/proto/inventory.proto"
        text = b'collection_id: "\\000\\377abcdefghijklmn"\ncollected_at: 1000\n'
        code, payload, _ = inventory.run_bounded(
            [protoc, "--encode=proto.InventorySnapshot", f"--proto_path={schema.parent}", schema.name],
            timeout=5, stdout_limit=131072, data=text, cwd=schema.parent)
        self.assertEqual(code, 0)
        decoded = inventory.decode_snapshot(protoc, schema, payload)
        self.assertEqual(inventory.decoded_bytes(decoded, "collection_id"), b"\x00\xffabcdefghijklmn")
        with self.assertRaisesRegex(inventory.ProbeFailure, "not a valid"):
            inventory.decode_snapshot(protoc, schema, b"\xff")


if __name__ == "__main__":
    unittest.main()
