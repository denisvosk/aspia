# Aspia+ Mobile 2.7.2-mobile.6 — experimental Android UX release

Based on the user-tested mobile.5, with the **existing Aspia 2.7.0 Router,
Relay, Host, local encrypted .aab book and signing identity left unchanged**.

## What's new

- **Press-and-hold ЛКМ:** a dedicated left mouse button remains visible when
  the auxiliary row scrolls. Holding it with one finger and dragging the remote
  desktop with another transmits mouse movement with LEFT_BUTTON down; releasing
  the button always releases the Windows mouse state. Tap–hold drag remains.
- **Correct shortcut gestures:** touching the remote view, fitting or resizing
  no longer consumes latched Ctrl/Alt/Shift before the next key. The bar also
  adds a reliable «Задачи» (Ctrl+Shift+Esc), direct «Пуск» and F2.
- **Reachable buttons:** the special-key strip uses a horizontal scrollable area
  plus a small fallback next-arrow, so keys cannot disappear past the right
  edge in portrait.
- **Keyboard on Android:** the Samsung keyboard opens OVER the remote desktop
  (adjustNothing), without fitting or moving the existing frame. The «Клав.»
  action now toggles open/close. While the keyboard is up, the auxiliary bar
  becomes a narrow vertical rail on the LEFT side of the visible area, instead
  of a second strip above the keyboard. Standard letters/IME remain Samsung's.
- **Screenshots:** no FLAG_SECURE; native Android capture is allowed.
- **Return from lockscreen:** queue app password/biometric relock after the
  activity foreground event and request repaint on session resume. This is
  a defensive change, NOT proof that the reported device hang is fixed.
- Removed redundant right-click item from the three-dot menu, while
  keeping long-press/two-finger right click, the floating menu and
  «Питание → Блокировка» as they were.
- Mouse-follow 12/24% finite edge pan and remote wheel scrolling unchanged.

## Build and tests

`python3 mobile/prepare-source.py --output ../aspia-mobile-src` recreates the
pinned upstream and applies all verified overlays, then
`mobile/mobile6-uifixes.py`. The exact file SHA-256 is in
`mobile/source-lock.json`; any unexpected source fails before build.

`.github/workflows/mobile-v6-build.yml` validates source and packaged ARM64
APK and performs the Android 12 emulator startup test. A green build cannot
prove multi-touch, keyboard resizing or lockscreen behavior on Samsung S10
or actual remote session I/O. Test on a NONCRITICAL Host 2.7.0 first.

**Preserve a known-good mobile.5 APK** as rollback. Install the signed mobile.6
APK over mobile.5 to retain local books and credentials. Do not uninstall,
clear app data or publish the encrypted address book on a public website.
