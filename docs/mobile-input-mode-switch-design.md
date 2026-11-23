# Aspia+ Mobile: compact input-mode switch near Space

Status: proposed UX and technical plan, **not implemented**. 2026-11-23.
Android-only; do not change Host, Client, Console, Router, Relay or the desktop protocol.

## Goal

Add a compact dark utility key immediately **right of the spacebar**,
before the period key in the Samsung-like keyboard. Tap cycles through
three clearly labelled input methods:

1. **HID** (physical USB key positions) — default, sends scancodes with
   ordered down/up (Mobile11 32ms/6ms). The remote OS chooses its layout;
   nested Aspia/RDP/AnyDesk may forward the physical keys.
2. **TXT** (Unicode text) — ordinary letter keys send `TextEvent`
   containing the chosen characters, independent of the remote keyboard
   layout. Physical modifiers, Esc, Enter, Tab, Backspace and hotkeys
   remain physical events. Nested remote clients may ignore `VK_PACKET`.
3. **BUF** (clipboard-assisted **batch paste**) — this must **not**
   silently write to the OS clipboard on every letter tap. Collect a
   temporary text draft in an **app-private** buffer, with visible
   draft/commit/cancel affordances; only on explicit user confirmation
   attempt to transfer the draft via clipboard transport and issue
   a remote Ctrl+V. This method is for hard-to-reach nested text fields.
   It cannot guarantee reliable delivery through arbitrary RDP/AnyDesk
   nesting, or guarantee restoration of a multiformat clipboard.

Ctrl+C is **Copy**, Ctrl+V is **Paste**. Do not call Ctrl+C a text
transport mode. The existing **Вставить** button sends Android clipboard
text directly via `DesktopView::onVirtualText` / `TextEvent` without
overwriting the Windows clipboard; keep that feature and label it
clearly. A normal remote Ctrl+V only pastes whatever is already on the
remote system clipboard and is not equivalent to sending newly typed
text.

## UX

- Use a small key **between the long Space and the '.' key**. Modes have
  stable, legible labels `HID`, `ТЕК`/`TXT`, `БУФ`/`BUF`.
  The button is dark like other utility keys; fixed width/height and
  icon size across states. Do not change Shift/Backspace, number row,
  keyboard height or the KeyBar. Reduce spacer width minimally.
- **Mode changes only on long press (500 ms) and explicit selection**:
  hold HID/TXT/BUF to open a small three-option in-app popup above the key,
  then tap one mode or drag a held finger over it and release.
  A **short press never changes input mode**. While BUF has an unfinished
  draft, a short tap on BUF may open the explicit review/commit dialog.
  No mode changes when swiping Space (RU/EN visual layout remains independent
  of transport mode).
- Start each **new connection** in `HID`; do not persist a dangerous BUF
  mode accidentally into a login/password field or next session.
  Indicate current mode in the key itself. Do not infer secure fields
  by inspecting inaccessible remote pixels.
- Local RU/EN only changes shown key labels; does not secretly switch
  Windows or Linux keyboard layout.
- In physical mode, use existing queued USB HID events and do not
  intercept ordinary shortcuts.
- In TXT mode, no double dispatch; no auto-copy into clipboard.
- In BUF mode, show a **local draft** with explicit Paste / Cancel,
  never send unconfirmed characters to remote or write remote clipboard
  on each key. Treat paste as a whole transaction, not a stream of
  per-character clipboard swaps.

## Buffer integrity and failure

The remote system clipboard can contain arbitrary binary formats,
file lists, Office private formats and delayed-rendered objects.
Temporarily replacing it and immediately restoring a saved text
snapshot is **not generally safe**, particularly across two or more
independent clipboard synchronization agents or when another user
presses Ctrl+C concurrently. No false promise of lossless clipboard
restore; do not overwrite an existing clipboard by default.

Implementation choices for BUF:
- **Safest initial variant:** an explicit one-shot **Ctrl+V** action
  using an already populated remote clipboard. This does not type
  arbitrary new text and should be labelled accordingly, not presented
  as a complete BUF input mode.
- **Experimental variant:** request the user explicitly authorize a
  clipboard overwrite before committing draft; send via existing
  clipboard channel, wait for synchronization/ack where available,
  perform Ctrl+V, and **never claim** the old multiformat clipboard
  is preserved. Do not auto-restore after an arbitrary timer; avoid
  racing with other users or applications. Show a clear warning before
  enabling.
- For a robust reusable arbitrary-text clipboard mode, design a
  transaction/ack on each hop. This is **not** a purely mobile feature
  and would require desktop changes, so it conflicts with the present
  desktop-stability priority and should be deferred.

## Acceptance

Test HID and TXT on direct Windows Notepad, password/login screens,
nested Aspia and RDP, Ctrl+C/V, physical modifier sequences, auto-Shift,
language swipe, repeated fast typing, and mobile resume.
For BUF test only in disposable text fields with noncritical clipboard
contents, failing closed on missing capability or confirmation.
Prioritize responsiveness fixes from Mobile11 before enabling BUF.

## Code references

- `mobile/mobile10-samsung.py` builds bottom row:
  `!#1 | , | Space | . | Enter`.
- `mobile/mobile11-input-stability.py` adds ordered physical key queue.
- `mobile/mobile7-keyboard.py` defines `DesktopView::onVirtualText`
  and existing `pastePhoneText` (Android clipboard -> TextEvent).
- `source/host/input_injector_win.cc` maps `TextEvent` through
  `KEYEVENTF_UNICODE`, which nested clients may ignore.
