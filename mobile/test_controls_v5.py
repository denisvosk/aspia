#!/usr/bin/env python3
"""Static source safety/regression guard; not a device UI or host-protocol test."""
from pathlib import Path
import re
import sys

root = Path(sys.argv[1]).resolve()
def source(name):
    return (root / "source/client/android" / name).read_text(encoding="utf-8")
view = source("desktop_view.cc")
view_h = source("desktop_view.h")
window = source("desktop_window.cc")
key = source("key_bar.cc")
key_h = source("key_bar.h")
java = (root / "source/client/android/packaging/src/org/aspia/client/ClientActivity.java").read_text()

def check(condition, message):
    if not condition: raise AssertionError(message)

check('QT_ANDROID_NO_FULLSCREEN_KEYBOARD' in java, "Landscape extract-mode suppression missing")
check('long_pressed_ = true' in view and '!long_pressed_' in view, "Long press must send one right click without a trailing left click")
check('sendClick(proto::input::MouseEvent::RIGHT_BUTTON)' in view, "Right click missing")
check('if (armed_drag_)' in view and 'startDrag()' in view, "Tap-and-hold drag regression")
check('TwoFingerMode::PAN' in view and 'zoom_ > 1.01' in view, "Magnified two-finger pan missing")
check('content_pos_ += centroid - pinch_centroid_' in view, "Viewport pan missing")
check('fittedSize() const' in view and 'QSizeF(width(), viewportHeight())' in view, "Fit excludes neither keyboard nor toolbar")
check('height() - keyboard_inset_ - key_bar_height_' in view, "Persistent shortcut bar must reduce visible area")
check('sendWinLock()' in view_h and 'sendRawKey(kUsbLeftMeta, true)' in view and 'sendRawKey(kUsbLeftMeta, false)' in view, "Win+L fallback missing a key release")
check('proto::power::Control::ACTION_LOCK' in window, "Host native Lock action missing")
check('sig_lockRequested' in key_h and 'sig_rightClickRequested' in key_h, "Persistent quick controls missing")
check('sig_modifierToggled' in key_h and 'sig_specialKey' in key_h, "Existing Ctrl/Alt/special key toolbar removed")
check('key_bar_->show()' in window and 'key_bar_->raise()' in window, "Shortcut bar is hidden")
check('setRequestedOrientation' in window and 'runOnAndroidMainThread' in window, "Android rotation must run on its UI thread")
check('if (forced_orientation_)' in window and '\"(I)V\", -1' in window, "Restore device orientation when session closes")
check('onMouseEvent' in window and 'proto::desktop::CHANNEL_ID_LEGACY' in window, "Legacy 2.7 input channel removed")
check('AabImporter' not in view, "Unexpected book importer in remote view")
print("PASS: Mobile 5 remote UI regression guard (source-level only)")
