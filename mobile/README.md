# Aspia+ Mobile 2.7.2-mobile.5 — remote controls

This patch builds on the **user-verified mobile.4**: Samsung S10 on Android 12
starts, locally imports `.aab`, reaches the old 2.7 Router/Relay and displays
the remote Windows desktop. Do not change any 2.7 keys or server components.

Mobile.5 improves only the Android remote desktop interaction:

- A persistent, horizontally scrollable bottom bar gives one-tap Keyboard,
  right mouse button (ПКМ), Lock (Блок), Ctrl, Alt, Fit (Вписать), Rotate
  (Поворот), Shift, Win and useful navigation keys.
- Long press of one finger sends one right-click. A double tap followed by
  holding/moving still drags using the left mouse button. A two-finger tap still
  sends right click.
- At magnification over 1x, a two-finger drag pans the visible desktop rather
  than scrolling the remote application. At 1x, the existing two-finger wheel
  scroll remains. Pinch zoom remains available.
- Fit mode computes size from the visible area above the bottom bar and keyboard;
  moving/pinching no longer forces the view back to the remote pointer.
- The direct Lock action uses host power control when advertised; otherwise
  sends Windows Win+L keys via the **existing** legacy 2.7 input path, after a
  confirmation. The Ctrl+Alt+Del command remains separate.
- Rotate toggles the Android Activity between landscape and portrait *without
  changing the phone's global auto-rotate switch*, and restores automatic
  orientation on leaving the session.
- `QT_ANDROID_NO_FULLSCREEN_KEYBOARD=1` is set before Qt starts. Qt 6.11.1
  documents this as disabling full-screen landscape IME/extract UI. The remote
  desktop is still partially covered by the actual keyboard while typing.

This does not turn the phone into a Windows display, nor alter remote display
resolution; it only changes how the mobile viewport is presented.

## Source and build

Use `python3 mobile/prepare-source.py --output ../aspia-mobile-src` to recreate
the pinned source. The v5 overlay is recorded by SHA-256 in
`mobile/source-lock.json`. The full CI build / APK inspection / Android 12 startup
workflow is `.github/workflows/mobile-v5-build.yml`, and a static source guard
is `mobile/test_controls_v5.py`.

A passing build/startup smoke test does **not** test a real remote Windows
session, touch interactions on Samsung One UI, the IME, or actual locking
permissions. Try the new controls on a noncritical Windows PC first and keep
the known-good mobile.4 APK as a rollback option. Do not uninstall mobile.4
or publish any private `.aab` on your public web server.
