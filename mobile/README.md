# Aspia+ Mobile 2.7.2-mobile.11 — reliable nested Aspia typing, refined icons

Experimental Android 12+ ARM64 update after hands-on Samsung S10 testing.
Keeps Mobile10's layout, swipe-to-switch RU/EN spacebar, dark corner keys,
three-mode Shift, compact 30px horizontal KeyBar and network compatibility.

## Changes

- **Nested remote session typing:** touch-screen letters, numbers and
  Backspace/Enter now travel as **ordered USB scan-code down/up events** with
  a 32 ms press and a 6 ms release gap rather than a 0-ms burst. This aims
  to improve delivery through two consecutive Aspia remote desktop sessions.
  The actual double-hop scenario still needs testing on the phone.
- **Finger tolerance:** accept a short tap even when the finger moves just
  outside the key during release, within a 20px Manhattan movement budget.
  A long movement does not become a letter.
- **Smaller icons, not smaller keys:** Shift symbol reduced from 31x30px to
  21x20px; Backspace from 32x25px to 21x17px (~1.5x smaller). Key rectangles,
  touch areas and fixed Shift geometry are unchanged.
- **Larger letters:** font size 20px instead of 18px, retaining the smaller
  number row with 19px digits. English/Russian key positions unchanged.
- **Shift itself is unchanged:** white outlined / blue one-shot / filled
  Caps Lock behavior from Mobile10 remains in place.
- Android biometric relock, keyboard foreground resume, LMB dragging,
  pinch/scroll, AAB file selection and paste of exact Unicode text all
  retain their previous paths.

## Important: RU/EN is not yet synchronized with remote Windows

The on-screen RU/EN layout switches with the spacebar swipe **on the
phone only**. USB scan codes produce characters using the active layout of
the focused **remote Windows** (or of the computer reached through a nested
Aspia session). For Russian keys to generate Russian text, set the active
remote Windows language to Russian, and likewise for English. The old
Aspia 2.7 Host/Router protocol does not report the focused Windows input
language back to this Android client, so one cannot reliably force the
correct layout just by changing the key labels on the phone. Do not claim
that the layout-synchronization bug is solved in this Mobile11 build.

The «Вставить» button retains the existing Unicode clipboard mechanism;
it is separate from the physical-key stream. For exact text in normal
Windows fields, this can be used when hardware scan codes are unsuitable.

## Validation

The hash-pinned Mobile11 input and visual overlays run after Mobile10
in `mobile/prepare-source.py`. CI runs dedicated regression checks plus
the Android 12 emulator startup smoke test. **Green CI does not certify
the responsiveness of typing through two Windows Aspia hops**; the user
must test it on Samsung S10. Mobile10 remains available to roll back.

This is an unofficial fork of Aspia, distributed under GPL-3.0.
