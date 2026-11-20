"""Seed and check an isolated Router 2.7 upgrade fixture; never print key material."""

import argparse
import hashlib
import json
import secrets
import sqlite3
from pathlib import Path


def snapshot(db):
    if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
        raise RuntimeError("Router database integrity check failed")
    statements = {
        "users": 'SELECT id, name, "group", hex(salt), hex(verifier), sessions, flags FROM users ORDER BY id',
        "hosts": 'SELECT id, hex("key") FROM hosts ORDER BY id',
    }
    result = {}
    for name, sql in statements.items():
        rows = db.execute(sql).fetchall()
        if not rows:
            raise RuntimeError(f"Router fixture has no {name}")
        encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        result[name] = {"count": len(rows), "sha256": hashlib.sha256(encoded).hexdigest()}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("seed", "verify"))
    parser.add_argument("database", type=Path)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    if not args.database.is_file():
        raise RuntimeError("Router database does not exist")
    with sqlite3.connect(args.database) as db:
        if args.mode == "seed":
            # Non-empty host identity table catches an upgrade that recreates the
            # DB and silently reassigns machine IDs, not only lost admin accounts.
            db.execute('INSERT INTO hosts (id, "key") VALUES (?, ?)', (424242, secrets.token_bytes(32)))
            db.commit()
            args.snapshot.write_text(json.dumps(snapshot(db)), encoding="utf-8")
        else:
            expected = json.loads(args.snapshot.read_text(encoding="utf-8"))
            if snapshot(db) != expected:
                raise RuntimeError("Router users or Host IDs/keys changed during upgrade")
    print(f"Router data {args.mode}: passed")


if __name__ == "__main__":
    main()
