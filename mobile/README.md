# Aspia+ Mobile 2.7.2-mobile.5 — remote controls

This patch builds on the **user-verified mobile.4**: Samsung S10 on Android 12
starts, locally imports `.aab`, reaches the old 2.7 Router/Relay and even Host 2.7.0 and displays
the remote Windows desktop. Do not change any 2.7 keys or server components.

Mobile.5 improves only the Android remote desktop interaction:

- A persistent, horizontally scrollable bottom bar gives one-tap Keyboard,
  right mouse button (ПКМ), Ctrl, Alt, Fit (Вписать), Rotate
  (Поворот), Shift, Win and useful navigation keys.
- Long press of one finger sends one right-click. A double tap followed by
  holding/moving still drags using the left mouse button. A two-finger tap still
  sends right click.
- Two-finger drag up/down **always** scrolls the remote window, at fit and
  magnified zoom, like TeamViewer's mouse mode. Pinch zoom remains available.
- When zoomed, moving the remote cursor toward an edge automatically shifts
  the visible frame to keep the pointer onscreen. No two-finger pan mode is
  substituted for the useful wheel scrolling gesture.
- Fit mode computes size from the visible area above the bottom bar and keyboard;
  moving/pinching no longer forces the view back to the remote pointer.
- Based on user feedback, the established **Power → Lock** submenu is
  preserved without duplicate lock controls or an additional Win+L fallback.
  The original safety confirmation remains; opening Power does not shut down.
  Ctrl+Alt+Del remains a separate action.
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

## Finite cursor-triggered automatic panning

The viewport does not perpetually scroll when the user parks the mouse at the
edge. When the remote pointer reaches the outer 12% of a zoomed viewport, it
arms one finite pan target bringing it to an inner 24% comfort boundary. The
pointer stays at its original remote coordinate; only the image shifts over
16 ms timer ticks, with damped steps and no inertia beyond the target. The
move stops at the comfort threshold or at a real edge of the remote image,
even when the controlling finger has already stopped. In corners both axes
move together. Additional pointer movement may re-target the finite pan;
pinching cancels it. Two-finger scroll continues to scroll the remote window.
Existing long-drag auto-cursor movement is disabled specifically while
zoomed, to prevent a stationary held finger from walking the mouse endlessly.

`mobile/test_edge_pan.py` checks source invariants and simulates stationary
pointer, diagonal and remote-border cases. Real Samsung UI remains unverified.
