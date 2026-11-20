"""Bounded smoke test of the installed Windows Host's real inventory worker.

No protobuf binary ever passes through PowerShell or a text codec. The actual
build's protoc validates InventorySnapshot from raw stdin; only protoc's text
representation is inspected for the required hardware fields afterwards.
"""

import argparse
import ast
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time


class ProbeFailure(RuntimeError):
    pass


def run_bounded(command, *, timeout, stdout_limit, stderr_limit=16384, data=b"", cwd=None):
    """Capture binary pipes with hard memory caps and a process deadline."""
    process = subprocess.Popen(
        [str(part) for part in command],
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    results = queue.Queue()

    def read_pipe(name, stream, limit):
        chunks = []
        size = 0
        try:
            while True:
                chunk = stream.read(min(4096, limit + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise ProbeFailure(f"{name} exceeded its {limit}-byte limit")
                chunks.append(chunk)
            results.put((name, b"".join(chunks)))
        except Exception as error:
            results.put(("error", error))
        finally:
            stream.close()

    def write_input():
        try:
            remaining = memoryview(data)
            while remaining:
                written = process.stdin.write(remaining)
                if not written:
                    raise ProbeFailure("Child process did not accept protobuf stdin")
                remaining = remaining[written:]
            results.put(("stdin", None))
        except Exception as error:
            results.put(("error", error))
        finally:
            process.stdin.close()

    # Daemon pipe readers cannot extend a failed smoke test indefinitely if a
    # driver prevents the worker from exiting after TerminateProcess.
    threads = [
        threading.Thread(target=read_pipe, args=("stdout", process.stdout, stdout_limit), daemon=True),
        threading.Thread(target=read_pipe, args=("stderr", process.stderr, stderr_limit), daemon=True),
        threading.Thread(target=write_input, daemon=True),
    ]
    for thread in threads:
        thread.start()
    captured = {}
    deadline = time.monotonic() + timeout
    try:
        while len(captured) < 3 or process.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProbeFailure(f"Process exceeded its {timeout}-second deadline")
            try:
                name, value = results.get(timeout=min(remaining, 0.1))
            except queue.Empty:
                continue
            if name == "error":
                raise ProbeFailure(str(value)) from value
            captured[name] = value
        return process.returncode, captured["stdout"], captured["stderr"]
    finally:
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            # The smoke fails; it must not wait forever on a faulty storage driver.
            pass
        for thread in threads:
            thread.join(timeout=0.1)


def decoded_bytes(text, name):
    """Read one top-level bytes/string field emitted by protoc TextFormat."""
    # Windows protoc emits CRLF on its text stdout. Accept that line ending;
    # the captured protobuf stdin/stdout remains raw bytes throughout the probe.
    matches = re.findall(r'^' + re.escape(name) + r': ("(?:[^"\\]|\\.)*")\r?$', text, re.MULTILINE)
    if len(matches) != 1:
        raise ProbeFailure(f"Missing or duplicate {name} in decoded snapshot")
    # protoc's default TextFormat escapes non-ASCII bytes with C/octal escapes.
    # literal_eval accepts no executable expressions and preserves those bytes.
    try:
        value = ast.literal_eval("b" + matches[0])
    except (SyntaxError, ValueError) as error:
        raise ProbeFailure(f"Invalid escaped {name} in decoded snapshot") from error
    if not isinstance(value, bytes):
        raise ProbeFailure(f"Invalid {name} field type")
    return value


def decoded_integer(text, name):
    matches = re.findall(r'^' + re.escape(name) + r': (-?[0-9]+)\r?$', text, re.MULTILINE)
    if len(matches) != 1:
        raise ProbeFailure(f"Missing or duplicate {name} in decoded snapshot")
    return int(matches[0])


def validate_snapshot(text, started_at, finished_at):
    if len(decoded_bytes(text, "collection_id")) != 16:
        raise ProbeFailure("Inventory collection_id must be exactly 16 bytes")
    collected_at = decoded_integer(text, "collected_at")
    if not started_at - 300 <= collected_at <= finished_at + 300:
        raise ProbeFailure("Inventory collected_at is not a plausible current timestamp")
    for name in ("computer_name", "os_name", "os_version", "os_arch", "cpu_model"):
        if not decoded_bytes(text, name).strip():
            raise ProbeFailure(f"Inventory {name} must be nonempty on the Windows CI runner")
    packages = decoded_integer(text, "cpu_packages")
    cores = decoded_integer(text, "cpu_cores")
    threads = decoded_integer(text, "cpu_threads")
    mhz = decoded_integer(text, "cpu_clock_mhz")
    ram = decoded_integer(text, "ram_bytes")
    if not 1 <= packages <= cores <= threads <= 65536:
        raise ProbeFailure("Inventory CPU counts are missing or inconsistent")
    if not 1 <= mhz <= 100000:
        raise ProbeFailure("Inventory CPU clock is missing or implausible")
    if not 64 * 1024 * 1024 <= ram <= (1 << 50):
        raise ProbeFailure("Inventory RAM is missing or implausible")
    # A hosted VM can hide physical media or expose no physical disk descriptor.
    # Missing/UNKNOWN disk types do not fail collection or invent a disk type.


def decode_snapshot(protoc, schema, payload):
    code, decoded, _ = run_bounded(
        [protoc, "--decode=proto.InventorySnapshot", f"--proto_path={schema.parent}", schema.name],
        timeout=15, stdout_limit=1024 * 1024, data=payload, cwd=schema.parent)
    if code != 0:
        raise ProbeFailure(f"Inventory stdout is not a valid InventorySnapshot protobuf (protoc exit {code})")
    return decoded.decode("utf-8", errors="strict")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--protoc", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_OS") != "Windows":
        raise ProbeFailure("Inventory smoke may run only on an isolated GitHub Windows runner")
    service, protoc, schema = (path.resolve(strict=True) for path in (args.service, args.protoc, args.schema))
    started_at = int(time.time())
    code, payload, _ = run_bounded(
        [service, "--inventory-stdout"], timeout=70, stdout_limit=128 * 1024, cwd=service.parent)
    finished_at = int(time.time())
    if code != 0 or not payload:
        raise ProbeFailure(f"Installed Host inventory worker failed (exit {code}; {len(payload)} output bytes)")
    validate_snapshot(decode_snapshot(protoc, schema, payload), started_at, finished_at)
    # Keep actual computer names, IDs and hardware descriptions out of public logs.
    print("Installed Host inventory worker: valid bounded protobuf, fresh 16-byte collection ID, "
          "current timestamp, computer/OS identity and CPU/RAM fields passed.")


if __name__ == "__main__":
    main()
