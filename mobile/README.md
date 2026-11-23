# Aspia+ Mobile 2.7.2-mobile.10 — Samsung reduced keyboard, better KeyBar

This experimental Android 12+ ARM64 build revises Mobile9 following six
side-by-side screenshots from Samsung S10 (portrait + landscape).
The physical USB-scancode text path from Mobile9 is unchanged: the user has
verified that typing reaches a **nested Aspia client** on a Windows desktop.
The selected Android RU/EN layout still needs to match the active Windows
keyboard layout for scan-code-accurate text.

## Samsung-like keyboard

- A genuinely shorter number row (4:5 proportion vs letter rows), larger
  19px digit glyphs, 18px letter glyphs, near-black gaps and grey keycaps.
- Extra lower padding below the spacebar to avoid accidental KeyBar taps.
- Darker **!#1**, Shift, Backspace and Enter utility keys, with vector
  Backspace, Shift and Enter icons rather than unreliable Unicode glyphs.
- One uninterrupted wide spacebar, containing **< Русский >** or
  **< English (US) >** as visual labels. **Swipe left or right across the
  spacebar to change languages; arrows are not separate buttons.**
  Tapping inserts one space; a horizontal swipe inserts no space.
- Fixed-width, stable Shift icon:
  **white outline** = lowercase, **blue outline** = one uppercase letter,
  **white filled** = Caps Lock. From lowercase tap once for one-shot, tap
  again for Caps Lock, tap again for lowercase. Letters do not shift when
  the indicator changes. Initially the keyboard uses one-shot upper-case.
- Uppercase state returns to lowercase after one letter, and after
  end-of-sentence punctuation or Enter the next letter starts in one-shot.
  Do not claim automatic sentence detection across remote applications.
- Russian 11-letter rows, English 10/9/7 rows: the English middle row is
  indented while the bottom Shift and Backspace are wider.
- Hold Russian Е for Ё, Ь for Ъ, no top emoji/mic/settings toolbar,
  and 75% centered keyboard width in landscape.

## Auxiliary control rail

- Same **ЛКМ**, **Клав.**, **Вставить**, Ctrl, Alt, Shift, Esc and
  other working remote commands from Mobile9.
- Rail reduced from Mobile9 33 to **30 Qt logical pixels**; keys 26px
  and captions vertically centered. Only **horizontal** finger-scrolling
  is allowed; vertical scrollbar movement and kinetic overshoot are
  disabled. Removed **Впис.** remains absent.
- On returning from biometric unlock, suppress Samsung IME when the
  custom keyboard was open. Do not bypass the normal relock policy.
- Existing pan/zoom, clipboard paste and local AAB stay untouched.

## Validation and release caveats

This branch uses `mobile/prepare-source.py` with hash-pinned
`mobile10-keybar.py` and `mobile10-samsung.py` overlays; compilation,
package checks, and Android 12 emulator startup are CI gates.
A green emulator startup does not demonstrate the keyboard visual match,
a full language-swipe gesture on a real Samsung, or biometric-cycle
behavior. Test landscape, portrait, Shift state transitions, space
swipes, LMB, clipboard and resume before calling the release stable.

Workflows: `.github/workflows/mobile-v10-build.yml`.
Android application ID and signing identity stay identical to Mobile9;
Mobile9 remains available for fallback testing.

Aspia+ is an unofficial Aspia fork under GPL-3.0.
