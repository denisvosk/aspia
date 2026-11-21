#!/usr/bin/env python3
"""Run the existing ARM64 APK on a clean API31 Google APIs x86_64 emulator.

Uses the image's ARM native bridge, not a rebuilt x86 client. A temporary debug
certificate is used only for this virtual device. No release key, address book,
Router configuration or user account is read. Logs are local CI artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import zipfile


PACKAGE = "org.aspiaplus.client"
COMPONENT = PACKAGE + "/org.aspia.client.ClientActivity"


def payload_hashes(apk: Path) -> dict[str, str]:
    """Ignore only signature entries; compare every compiled payload entry."""
    with zipfile.ZipFile(apk) as archive:
        return {name: hashlib.sha256(archive.read(name)).hexdigest()
                for name in archive.namelist()
                if not name.upper().startswith("META-INF/")}


def has_app_anr(log: str) -> bool:
    for line in log.splitlines():
        if re.search(r"\bANR in " + re.escape(PACKAGE) + r"\b", line):
            return True
        if "am_anr" in line and re.search(r"\b" + re.escape(PACKAGE) + r"\b", line):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--avd", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--boot-timeout", type=int, default=600)
    parser.add_argument("--observe-seconds", type=int, default=60)
    args = parser.parse_args()
    if args.boot_timeout < 1 or args.observe_seconds < 60:
        parser.error("boot timeout must be positive; observation must be at least 60 seconds")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sdk = args.sdk_root.resolve()
    adb = str(sdk / "platform-tools/adb")
    emulator = str(sdk / "emulator/emulator")
    build_tools = sdk / "build-tools/36.0.0"
    serial = "emulator-5554"
    report: dict = {"passed": False, "package": PACKAGE, "component": COMPONENT,
                    "avd": args.avd, "observation_seconds": args.observe_seconds,
                    "certificate": "temporary CI debug certificate; not a release APK",
                    "limitations": [
                        "A live process and resumed activity do not prove an interactive or fully initialized UI.",
                        "This test does not verify a physical phone, local book import or remote sessions.",
                        "The original ARM64 native code runs through the emulator's native bridge.",
                    ],
                    "original_apk_sha256": None, "samples": []}
    emu = logcat = None
    emulator_log = logcat_log = None

    def run(command: list[str], *, timeout: int = 30, check: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace", timeout=timeout)
        if check and result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}): {command[0]}\n{result.stdout}")
        return result

    def device(*command: str, timeout: int = 30, check: bool = True) -> subprocess.CompletedProcess:
        return run([adb, "-s", serial, *command], timeout=timeout, check=check)

    def capture(name: str, *command: str) -> str:
        try:
            result = device(*command, timeout=20, check=False)
            text = result.stdout
        except (OSError, subprocess.TimeoutExpired) as exc:
            text = f"Evidence collection failed: {exc}\n"
        (output / name).write_text(text, encoding="utf-8")
        return text

    try:
        original = args.apk.resolve(strict=True)
        report["original_apk_sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
        original_payload = payload_hashes(original)
        if "lib/arm64-v8a/libaspia_client_arm64-v8a.so" not in original_payload:
            raise RuntimeError("The original APK has no ARM64 Aspia client library")

        with tempfile.TemporaryDirectory(prefix="aspia-emulator-only-") as work_dir:
            temporary = Path(work_dir)
            keystore = temporary / "emulator-debug.p12"
            aligned = temporary / "aligned.apk"
            signed = temporary / "emulator-debug.apk"
            keytool = shutil.which("keytool")
            if not keytool:
                raise RuntimeError("keytool not found; install JDK 21")
            run([keytool, "-genkeypair", "-noprompt", "-storetype", "PKCS12",
                 "-keystore", str(keystore), "-alias", "androiddebugkey",
                 "-storepass", "android", "-keypass", "android", "-keyalg", "RSA",
                 "-keysize", "2048", "-validity", "2",
                 "-dname", "CN=Aspia CI Emulator Only"], timeout=60)
            run([str(build_tools / "zipalign"), "-P", "16", "-f", "4",
                 str(original), str(aligned)])
            run([str(build_tools / "apksigner"), "sign", "--ks", str(keystore),
                 "--ks-key-alias", "androiddebugkey", "--ks-pass", "pass:android",
                 "--key-pass", "pass:android", "--out", str(signed), str(aligned)])
            signature = run([str(build_tools / "apksigner"), "verify", "--verbose",
                             "--print-certs", str(signed)])
            (output / "debug-signature.txt").write_text(signature.stdout, encoding="utf-8")
            if payload_hashes(signed) != original_payload:
                raise RuntimeError("Compiled APK payload changed while applying the debug signature")
            report["compiled_payload_unchanged"] = True

            run([adb, "start-server"])
            emulator_log = (output / "emulator.log").open("w", encoding="utf-8")
            emu = subprocess.Popen([
                emulator, "-avd", args.avd, "-port", "5554", "-accel", "on",
                "-no-window", "-no-audio", "-no-boot-anim", "-no-snapshot", "-wipe-data",
                "-gpu", "swiftshader", "-memory", "3072", "-cores", "2",
                "-camera-back", "none", "-camera-front", "none",
            ], stdout=emulator_log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + args.boot_timeout
            print("Waiting for a clean Android boot...", flush=True)
            while time.monotonic() < deadline:
                if emu.poll() is not None:
                    raise RuntimeError(f"Emulator exited during boot: {emu.returncode}")
                try:
                    boot = device("shell", "getprop", "sys.boot_completed", timeout=10, check=False)
                    if boot.returncode == 0 and boot.stdout.strip() == "1":
                        break
                except subprocess.TimeoutExpired:
                    pass
                time.sleep(5)
            else:
                raise RuntimeError(f"Android did not finish booting within {args.boot_timeout}s")

            props = {}
            for name in ("ro.build.version.release", "ro.build.version.sdk", "ro.product.model",
                         "ro.product.cpu.abilist", "ro.product.cpu.abilist64",
                         "ro.dalvik.vm.native.bridge", "ro.enable.native.bridge.exec"):
                props[name] = device("shell", "getprop", name).stdout.strip()
            report["device_properties"] = props
            (output / "device-properties.json").write_text(json.dumps(props, indent=2), encoding="utf-8")
            if "arm64-v8a" not in props["ro.product.cpu.abilist"]:
                raise RuntimeError("This system image does not advertise ARM64 translation; APK not run")

            # AVD was wiped and receives only the APK. No production settings or book is imported.
            for name in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
                device("shell", "settings", "put", "global", name, "0")
            device("shell", "svc", "wifi", "disable")
            device("shell", "svc", "data", "disable")
            device("shell", "input", "keyevent", "82")
            installed = device("install", "--abi", "arm64-v8a", str(signed), timeout=120)
            (output / "install.txt").write_text(installed.stdout, encoding="utf-8")
            if "Success" not in installed.stdout:
                raise RuntimeError("adb did not confirm APK installation")

            device("logcat", "-c")
            logcat_log = (output / "logcat-startup.txt").open("w", encoding="utf-8")
            logcat = subprocess.Popen([adb, "-s", serial, "logcat", "-v", "threadtime",
                                      "-b", "main", "-b", "system", "-b", "crash", "-b", "events"],
                                     stdout=logcat_log, stderr=subprocess.STDOUT)
            launch = device("shell", "am", "start", "-W", "-n", COMPONENT, timeout=90, check=False)
            (output / "launch.txt").write_text(launch.stdout, encoding="utf-8")
            if launch.returncode or re.search(r"^Error:", launch.stdout, re.MULTILINE):
                raise RuntimeError("Android activity launch failed; see launch.txt")
            started = time.monotonic()
            known_pids: set[str] = set()
            while True:
                elapsed = time.monotonic() - started
                if emu.poll() is not None:
                    raise RuntimeError("Emulator exited while observing the app")
                pid_text = device("shell", "pidof", PACKAGE, check=False).stdout.strip()
                pids = set(pid_text.split()) if re.fullmatch(r"\d+(?:\s+\d+)*", pid_text) else set()
                report["samples"].append({"elapsed_seconds": round(elapsed, 1), "pids": sorted(pids)})
                if not pids:
                    raise RuntimeError(f"App process disappeared after {elapsed:.1f}s")
                if known_pids and not (pids & known_pids):
                    raise RuntimeError("App process restarted during startup observation")
                known_pids.update(pids)
                if elapsed >= args.observe_seconds:
                    break
                time.sleep(min(5, args.observe_seconds - elapsed))

            activity = capture("activities.txt", "shell", "dumpsys", "activity", "activities")
            resumed_lines = [line.strip() for line in activity.splitlines()
                             if "mResumedActivity" in line or "topResumedActivity" in line]
            report["resumed_activity"] = resumed_lines
            if not any(COMPONENT in line for line in resumed_lines):
                raise RuntimeError("Aspia is not the resumed foreground activity after observation")
            crashes = capture("crash-buffer.txt", "logcat", "-b", "crash", "-d", "-v", "threadtime")
            if PACKAGE in crashes:
                raise RuntimeError("Android crash buffer contains an Aspia crash")
            startup_log = capture("logcat-final.txt", "logcat", "-d", "-v", "threadtime",
                                  "-b", "main", "-b", "system", "-b", "crash", "-b", "events")
            if has_app_anr(startup_log):
                raise RuntimeError("Android recorded an ANR for Aspia during startup")
            for line in startup_log.splitlines():
                if "Fatal signal" in line and any(re.search(rf"\bpid {pid}\b", line) for pid in known_pids):
                    raise RuntimeError("Native fatal signal recorded for the Aspia process")
            report["passed"] = True
            print("PASS: original ARM64 client remained running and foreground for 60 seconds.", flush=True)
            print("Alive + foreground does not prove an interactive or fully initialized UI.", flush=True)
            print("Physical-device behavior, local book import and remote sessions are not tested.", flush=True)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, zipfile.BadZipFile) as exc:
        report["error"] = str(exc)
        print(f"FAIL: {exc}", flush=True)
    finally:
        if emu is not None:
            capture("crash-buffer-final.txt", "logcat", "-b", "crash", "-d", "-v", "threadtime")
            capture("window-final.txt", "shell", "dumpsys", "window", "windows")
            capture("activities-final.txt", "shell", "dumpsys", "activity", "activities")
            capture("last-anr.txt", "shell", "dumpsys", "activity", "lastanr")
            capture("package-final.txt", "shell", "dumpsys", "package", PACKAGE)
            try:
                shot = subprocess.run([adb, "-s", serial, "exec-out", "screencap", "-p"],
                                      capture_output=True, timeout=20)
                if shot.returncode == 0 and shot.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
                    (output / "screen.png").write_bytes(shot.stdout)
                    report["screenshot_note"] = "FLAG_SECURE may hide protected app contents in the screenshot"
            except (OSError, subprocess.TimeoutExpired):
                pass
        for process in (logcat, emu):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        for handle in (logcat_log, emulator_log):
            if handle:
                handle.close()
        (output / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
