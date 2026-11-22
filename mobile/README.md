# Aspia+ Mobile 2.7.2-mobile.9 — keyboard usability & nested Aspia typing

Based on Samsung S10 Android 12 feedback about Mobile8. Full install and live
nested-client verification are still required after the CI smoke test.

## Fixes

- **Keyboard visual proportions:** reduced Samsung screenshot is the reference.
  The number row is 80% of the height of the letter rows (and 15px font instead
  of 17px). The caps remain charcoal grey, with visibly near-black (#080808)
  gaps in dark theme. Landscape keyboard stays centered at 75% of available width.
- **Backspace:** painted vector icon with arrow-shaped outline and X; no Unicode
  glyph that appears as a missing-character rectangle on Samsung.
- **KeyBar:** 33 logical px high versus 44px in Mobile8 (25% less); keys 28px
  versus 32px, adjusted lower padding. Existing text **ЛКМ**, **Клав.**,
  **Вставить**, modifiers and their behavior are preserved. «Впис.» stays out.
- **Nested Aspia:** individual touch keys now use actual USB keyboard events
  (Windows scan codes), which are suitable for Qt/remote clients that ignore
  injected Unicode VK_PACKET. This includes letters and digits; unsupported
  Unicode falls back to the existing TextEvent.
- **Important language constraint:** physical keyboard input follows the
  **active Windows keyboard layout**. When the phone keyboard displays Russian,
  switch the remote Windows input layout to Russian too; when English, to
  English. The phone cannot read the remote Windows layout through Aspia 2.7.
- **Android clipboard paste:** «Вставить» still sends exact UTF-8 TextEvent,
  not scancodes; useful for longer texts and text requiring exact Unicode.
- Desktop image zoom, two-finger pan, press-and-hold LMB, keyboard opening
  focus, Router/Relay/Host 2.7 wire protocol, book and keys are unchanged.

## Validation

`.github/workflows/mobile-v9-build.yml` checks existing Mobile5/6/9 source
and APK, package identity and Android 12 emulator startup. **Automated CI
cannot certify typing into a second Aspia client running inside a live remote
Windows desktop.** This must be checked on the Samsung S10 using a nested
session, both Russian and English Windows input layouts. The signed Mobile8
installer remains available for rollback testing.

Aspia+ is an unofficial Aspia fork under GPL-3.0.
