#!/usr/bin/env python3
"""Mobile11: adjust icon artwork size without altering key geometry or Shift semantics.

Apply after mobile11-input-stability.py. Only changes the rendered size of
Shift/Backspace icons and the letter font; numbers and layout stay unchanged.
"""
from pathlib import Path
import sys


def once(path: Path, before: str, after: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(before)
    if count != 1:
        raise RuntimeError(f"{path}: expected one matching UI anchor, got {count}: {before!r}")
    path.write_text(text.replace(before, after, 1), encoding="utf-8")


def apply(root: Path) -> None:
    keyboard = root / "source/client/android/compact_keyboard.cc"

    # Samsung-style visual balance: the ICONS are 1.5x smaller,
    # not the touch targets. Shift never changes key width.
    once(keyboard, "shift_key_->setIconSize(QSize(31, 30));",
         "shift_key_->setIconSize(QSize(21, 20));")
    once(keyboard, "backspace->setIconSize(QSize(32, 25));",
         "backspace->setIconSize(QSize(21, 17));")

    # Letter faces become 20px instead of 18px; the smaller number-row
    # geometry, numbers, dark utility keys and gutters are untouched.
    once(keyboard, "font.setPixelSize(18);",
         "font.setPixelSize(20);")
    print("PASS: Mobile11 icon art shrunk by ~1.5x and letters enlarged; "
          "key geometry, remote Shift and keyboard behavior untouched")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: mobile11-visual.py <prepared-mobile11-input-tree>")
    apply(Path(sys.argv[1]).resolve())
