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
check('FLAG_SECURE' not in java and 'WindowManager' not in java, "Android screenshots must not be blocked")
check('long_pressed_ = true' in view and '!long_pressed_' in view, "Long press must send one right click without a trailing left click")
check('sendClick(proto::input::MouseEvent::RIGHT_BUTTON)' in view, "Right click missing")
check('if (armed_drag_)' in view and 'startDrag()' in view, "Tap-and-hold drag regression")
check('TwoFingerMode::SCROLL' in view and 'TwoFingerMode::PAN' not in view, "Two-finger remote wheel scroll must remain at every zoom")
check('sendWheel(steps)' in view and 'pinch_centroid_.y() - centroid.y()' in view, "Wheel scroll gesture disabled")
check('edge_pan_timer_' in view and 'trigger_x = view_width * 0.12' in view and 'comfort_x = view_width * 0.24' in view, "Finite cursor-follow threshold/comfort band missing")
check('content_pos_ += QPointF(dx, dy)' in view, "Viewport must follow the moving remote cursor")
check('fittedSize() const' in view and 'QSizeF(width(), viewportHeight())' in view, "Fit excludes neither keyboard nor toolbar")
check('height() - keyboard_inset_ - key_bar_height_' in view, "Persistent shortcut bar must reduce visible area")
check('sendWinLock()' not in view_h, "Preserve the existing lock path, no Win+L fallback")
check('proto::power::Control::ACTION_LOCK' in window, "Host native Lock action missing")
check('sig_lockRequested' not in key_h and 'sig_rightClickRequested' in key_h, "No duplicate lock button; right click remains")
check('sig_modifierToggled' in key_h and 'sig_specialKey' in key_h, "Existing Ctrl/Alt/special key toolbar removed")
check('key_bar_->show()' in window and 'key_bar_->raise()' in window, "Shortcut bar is hidden")
check('setRequestedOrientation' in window and 'runOnAndroidMainThread' in window, "Android rotation must run on its UI thread")
check('if (forced_orientation_)' in window and '\"(I)V\", -1' in window, "Restore device orientation when session closes")
check('onMouseEvent' in window and 'proto::desktop::CHANNEL_ID_LEGACY' in window, "Legacy 2.7 input channel removed")
check('action_sheet_->addItem(tr("Power")' in window and 'showPowerActions();' in window, "Preserve existing Power -> Lock submenu")
check('AabImporter' not in view, "Unexpected book importer in remote view")
print("PASS: Mobile 5 remote UI regression guard (source-level only)")
