# Aspia+ Mobile 2.7.2-mobile.7 — compact app-only RU/EN keyboard

Built on user-tested mobile.6 with **unchanged** 2.7 Router, Relay, Host,
local encrypted address book and the signing certificate.

- The existing horizontal KeyBar is permanently anchored to the **bottom
  of the display**, whether the keyboard is open or closed. It never
  relocates to a narrow left rail.
- A separate `CompactKeyboard` QWidget module expands directly **above**
  the bottom bar, across the full width. Includes RU/EN ЙЦУКЕН/QWERTY,
  Ё/ё, number row (NOT a numpad), punctuation and symbols,
  Shift, language switch, Enter, Backspace. In landscape, extra
  Esc, Tab and arrow keys appear within the keyboard.
- No Samsung/Gboard/Yandex IME or system keyboard toolbar is shown for
  normal remote typing. No phone keyboard settings are changed.
- Text is forwarded using Aspia's existing legacy-compatible
  UTF-8 TextEvent and USB KeyEvent paths.
- «Повор.» removed from the shortcut bar; only available from three dots.
  Swipe-scrolling the bar suppresses accidental button clicks while moving
  and briefly after the scroll stops. Dedicated holdable LMB remains.
- Text copied in another Android app can be transferred with «Вставить»
  (direct remote TextEvent). Android clipboard is also rechecked
  when the application returns to foreground and on connection.
- Showing the custom keyboard does not refit the remote image. After
  intentional pointer movement, a bounded pan uses the visible area
  above keyboard + KeyBar, making bottom-screen fields reachable.

**Module choice:** investigated official Qt Virtual Keyboard (GPLv3) and
CuteKeyboard (MIT, RU/EN, Qt6), but both require QtQuick/QML and an input
context plugin while the current Android Client is Qt Widgets-only.
For the narrow remote input task this release keeps a self-contained
Qt Widgets module and reuses the already working Aspia 2.7 input events.

`.github/workflows/mobile-v7-build.yml` checks hashes, source invariants,
builds ARM64, validates APK and smoke tests Android 12. Samsung S10
multitouch/IME, Unicode and clipboard remain **device tests**; keep the
working signed Mobile6 installer as a rollback.
