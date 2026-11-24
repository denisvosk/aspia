#!/usr/bin/env python3
"""Prepare the complete, pinned Aspia+ Mobile source tree (Python 3 + Git)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def run(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(args, cwd=cwd, check=True, text=True,
                               stdout=subprocess.PIPE, stderr=None)
    if completed.stdout:
        print(completed.stdout, end="")
    return completed.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="New or empty directory for the complete source tree")
    parser.add_argument("--no-submodules", action="store_true",
                        help="Do not download build dependencies yet")
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    lock = json.loads((bundle / "source-lock.json").read_text(encoding="utf-8"))
    patch = bundle / lock["patch_file"]
    digest = hashlib.sha256(patch.read_bytes()).hexdigest()
    if digest != lock["patch_sha256"]:
        raise RuntimeError("Patch SHA-256 mismatch. Download the source package again.")
    output = args.output.expanduser().resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise RuntimeError("Output must be a new or empty directory; existing files are preserved.")
    output.parent.mkdir(parents=True, exist_ok=True)
    run("git", "clone", "--depth", "1", "--branch", lock["upstream_tag"],
        lock["upstream_repository"], str(output))
    actual = run("git", "rev-parse", "HEAD", cwd=output)
    if actual != lock["upstream_commit"]:
        raise RuntimeError("Upstream tag does not match the pinned source commit; patch not applied.")
    run("git", "apply", "--check", str(patch), cwd=output)
    run("git", "apply", str(patch), cwd=output)
    overlay = bundle / "upgrade-mobile-v2.py"
    if not overlay.is_file():
        raise RuntimeError("Missing Mobile v2 source overlay")
    if hashlib.sha256(overlay.read_bytes()).hexdigest() != lock["overlay_sha256"]:
        raise RuntimeError("Mobile v2 source overlay SHA-256 mismatch")
    run(sys.executable, str(overlay), str(output), cwd=output)
    startup_fix = bundle / lock["startup_fix_file"]
    if hashlib.sha256(startup_fix.read_bytes()).hexdigest() != lock["startup_fix_sha256"]:
        raise RuntimeError("Mobile startup fix SHA-256 mismatch")
    run("git", "apply", "--check", str(startup_fix), cwd=output)
    run("git", "apply", str(startup_fix), cwd=output)
    picker_fix = bundle / lock["picker_fix_file"]
    if hashlib.sha256(picker_fix.read_bytes()).hexdigest() != lock["picker_fix_sha256"]:
        raise RuntimeError("Mobile document picker patch SHA-256 mismatch")
    run("git", "apply", "--check", str(picker_fix), cwd=output)
    run("git", "apply", str(picker_fix), cwd=output)
    controls_overlay = bundle / lock["controls_overlay_file"]
    if hashlib.sha256(controls_overlay.read_bytes()).hexdigest() != lock["controls_overlay_sha256"]:
        raise RuntimeError("Mobile 5 controls overlay SHA-256 mismatch")
    run(sys.executable, str(controls_overlay), str(output), cwd=output)
    # Keep the viewport policy isolated and hash-pinned after the controls overlay.
    edge_pan_overlay = bundle / lock["edge_pan_overlay_file"]
    if hashlib.sha256(edge_pan_overlay.read_bytes()).hexdigest() != lock["edge_pan_overlay_sha256"]:
        raise RuntimeError("Mobile 5 edge-pan overlay SHA-256 mismatch")
    run(sys.executable, str(edge_pan_overlay), str(output), cwd=output)
    mobile6_overlay = bundle / lock["mobile6_overlay_file"]
    if hashlib.sha256(mobile6_overlay.read_bytes()).hexdigest() != lock["mobile6_overlay_sha256"]:
        raise RuntimeError("Mobile 6 UI overlay SHA-256 mismatch")
    run(sys.executable, str(mobile6_overlay), str(output), cwd=output)
    mobile7_overlay = bundle / lock["mobile7_overlay_file"]
    if hashlib.sha256(mobile7_overlay.read_bytes()).hexdigest() != lock["mobile7_overlay_sha256"]:
        raise RuntimeError("Mobile 7 overlay checksum mismatch")
    run(sys.executable, str(mobile7_overlay), str(output), cwd=output)
    mobile8_overlay = bundle / lock["mobile8_overlay_file"]
    if hashlib.sha256(mobile8_overlay.read_bytes()).hexdigest() != lock["mobile8_overlay_sha256"]:
        raise RuntimeError("Mobile 8 overlay checksum mismatch")
    run(sys.executable, str(mobile8_overlay), str(output), cwd=output)
    mobile9_overlay = bundle / lock["mobile9_overlay_file"]
    if hashlib.sha256(mobile9_overlay.read_bytes()).hexdigest() != lock["mobile9_overlay_sha256"]:
        raise RuntimeError("Mobile 9 overlay checksum mismatch")
    run(sys.executable, str(mobile9_overlay), str(output), cwd=output)
    # KeyBar layout and Samsung keyboard behavior are independently pinned.
    mobile10_bar = bundle / lock["mobile10_keybar_overlay_file"]
    if hashlib.sha256(mobile10_bar.read_bytes()).hexdigest() != lock["mobile10_keybar_overlay_sha256"]:
        raise RuntimeError("Mobile 10 KeyBar overlay checksum mismatch")
    run(sys.executable, str(mobile10_bar), str(output), cwd=output)
    mobile10_keyboard = bundle / lock["mobile10_samsung_overlay_file"]
    if hashlib.sha256(mobile10_keyboard.read_bytes()).hexdigest() != lock["mobile10_samsung_overlay_sha256"]:
        raise RuntimeError("Mobile 10 Samsung keyboard overlay checksum mismatch")
    run(sys.executable, str(mobile10_keyboard), str(output), cwd=output)
    mobile11_input = bundle / lock["mobile11_input_overlay_file"]
    if hashlib.sha256(mobile11_input.read_bytes()).hexdigest() != lock["mobile11_input_overlay_sha256"]:
        raise RuntimeError("Mobile 11 physical input overlay checksum mismatch")
    run(sys.executable, str(mobile11_input), str(output), cwd=output)
    mobile11_visual = bundle / lock["mobile11_visual_overlay_file"]
    if hashlib.sha256(mobile11_visual.read_bytes()).hexdigest() != lock["mobile11_visual_overlay_sha256"]:
        raise RuntimeError("Mobile 11 icon/font overlay checksum mismatch")
    run(sys.executable, str(mobile11_visual), str(output), cwd=output)
    mobile12_overlay = bundle / lock["mobile12_overlay_file"]
    if hashlib.sha256(mobile12_overlay.read_bytes()).hexdigest() != lock["mobile12_overlay_sha256"]:
        raise RuntimeError("Mobile 12 input mode and punctuation overlay checksum mismatch")
    run(sys.executable, str(mobile12_overlay), str(output), cwd=output)
    mobile13_overlay = bundle / lock["mobile13_overlay_file"]
    if hashlib.sha256(mobile13_overlay.read_bytes()).hexdigest() != lock["mobile13_overlay_sha256"]:
        raise RuntimeError("Mobile 13 Samsung key popup overlay checksum mismatch")
    run(sys.executable, str(mobile13_overlay), str(output), cwd=output)
    if not args.no_submodules:
        run("git", "submodule", "sync", "--recursive", cwd=output)
        run("git", "submodule", "update", "--init", "--recursive", cwd=output)
    print(f"Complete Aspia+ Mobile {lock['version']} source is ready: {output}")
    print("Build instructions: .github/workflows/mobile-v13-build.yml and mobile/README.md")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Source preparation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
