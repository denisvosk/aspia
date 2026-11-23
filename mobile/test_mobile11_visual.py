#!/usr/bin/env python3
"""Regression checks for Mobile11 glyph sizing, without changing Samsung keys."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
android = root / "source/client/android"
kb = (android / "compact_keyboard.cc").read_text(encoding="utf-8")
h = (android / "compact_keyboard.h").read_text(encoding="utf-8")
bar = (android / "key_bar.cc").read_text(encoding="utf-8")
view = (android / "desktop_view.cc").read_text(encoding="utf-8")

def check(ok, reason):
    if not ok:
        raise AssertionError(reason)

check("shift_key_->setIconSize(QSize(21, 20));" in kb and
      "shift_key_->setIconSize(QSize(31, 30));" not in kb,
      "Shift arrow artwork must be ~1.5x smaller while keeping same key size")
check("backspace->setIconSize(QSize(21, 17));" in kb and
      "backspace->setIconSize(QSize(32, 25));" not in kb,
      "Backspace artwork must shrink, not its tap target")
check("font.setPixelSize(20);" in kb and
      "digit_font.setPixelSize(19);" in kb,
      "Letter glyphs should be 20px; digits keep the Samsung number-row design")
check('QIcon shiftIcon(bool dark, bool oneShot, bool capsLock)' in kb and
      'enum class ShiftState { Off, Once, CapsLock };' in h,
      "Keep three-state Shift semantics and artwork")
check('QSizePolicy::Ignored, QSizePolicy::Expanding' in kb and
      'bottom->setStretch(0, english ? 4 : 1)' in kb,
      "Changing a glyph must not resize or shift any keycaps")
check('queueKeyboardStroke(usb, local_shift);' in view and
      'QTimer::singleShot(32, this' in view,
      "Preserve reliability fix for physical typing through nested Aspia")
check('constexpr int kKeyHeight = 26;' in bar,
      "Keep compact auxiliary control bar unchanged")
print("PASS: Mobile11 Shift/Backspace icon scale and larger letters; touch geometry unchanged")
