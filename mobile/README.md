# Aspia+ Mobile 2.7.2-mobile.8 — reduced Samsung keyboard

Based on Samsung S10 Android 12 testing of the signed Mobile7. The old
Host 2.7, Router, Relay, signing identity, local AAB, input and clipboard
protocols remain unchanged. Mobile7 continues to be the rollback build.

- App-local Qt Widgets keyboard, not a new Android IME. The keyboard opens
  and closes with the existing **Клав.** control, retaining focus and zoom.
- Reduced Samsung-like Russian/English layout: **1..0** digit row, 11-letter
  RU rows, ordinary Shift and Backspace. Hold Е for Ё and Ь for Ъ (500 ms).
- Bottom typing row: symbols, comma, **< Русский >** / English space, dot,
  Enter. No duplicate Esc, Tab or navigation arrows inside the keyboard.
- Portrait fills available width; landscape keys are **centered at 75%**
  of the full width. The surrounding widget consumes touches safely.
- More gaps between fingers and clearer key caps. No Samsung/Google
  toolbar with emoji, microphone, settings, or suggestions.
- Bottom Aspia control bar remains scrollable with the existing holdable
  **ЛКМ**, **Клав.**, **Вставить**, Ctrl, Alt, Shift, etc.
- The **Впис.** control is removed, to prevent accidental fit/zoom resets.
  Rotation remains only in the floating three-dot menu.
- On dark themes, the control bar now uses white text rather than Android's
  blue accent. In light themes it uses the palette foreground (usually dark).
- Desktop touch mapping, two-finger gestures, pan above keyboard, clipboard,
  encryption, connection and resume after phone lock are unchanged.

Build: .github/workflows/mobile-v8-build.yml. Source invariants and the
Android 12 emulator startup smoke are CI gates. Actual Samsung keyboard
comfort, symbol display, Unicode and gestures still need device testing.
