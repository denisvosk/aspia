#!/usr/bin/env python3
"""Static regression gate: Mobile11 input serialization preserves Mobile10 UI."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
android = root / "source/client/android"

def source(name):
    return (android / name).read_text(encoding="utf-8")

def require(ok, message):
    if not ok:
        raise AssertionError(message)

view = source("desktop_view.cc")
header = source("desktop_view.h")
keyboard = source("compact_keyboard.cc")
bar = source("key_bar.cc")
bar_header = source("key_bar.h")
window = source("desktop_window.cc")

# Key presses must be real HID USB down/up, held for non-zero time and in
# deterministic order even when typing faster than the network can deliver.
require('void DesktopView::queueKeyboardStroke(quint32 usb_keycode, bool extra_shift)' in view,
        'physical key queue is missing')
require('void DesktopView::drainKeyboardStrokeQueue()' in view,
        'queued key sender missing')
require('timed_keyboard_stroke_active_' in view and 'timed_keyboard_strokes_' in header,
        'physical key press serialization state missing')
require('QTimer::singleShot(32, this' in view and 'QTimer::singleShot(6, this' in view,
        'hardware keystroke needs a controlled down interval and release gap')
segment = view.split('void DesktopView::drainKeyboardStrokeQueue()',1)[1].split('void DesktopView::sendRawKey(',1)[0]
require(segment.index('sendRawKey(stroke.usb_keycode, true)') < segment.index('sendRawKey(stroke.usb_keycode, false)'),
        'key down must occur before key up')
require('stroke.modifiers.crbegin()' in segment and 'stroke.modifiers.crend()' in segment,
        'modifier keys must release in reverse order')
require('timed_keyboard_strokes_.takeFirst()' in segment,
        'physical key sequence must preserve touch order')
require('queueKeyboardStroke(usb, local_shift)' in view,
        'touch keyboard must use paced key events')
require('queueKeyboardStroke(usb_keycode, false)' in view,
        'Enter/Backspace must preserve typing order')
require('emit sig_modifiersCleared()' in view and 'sticky_modifiers_.clear();' in view,
        'sticky modifiers must reset after one queued key')

# A small amount of drift cannot cancel a legitimate tap on a small mobile key.
require('class TolerantTouchKey final : public QPushButton' in keyboard and
        'new TolerantTouchKey(title, keys_panel_)' in keyboard,
        'finger-drift tolerant keys missing')
require('manhattanLength() <= 20.0' in keyboard,
        'tap movement tolerance must remain bounded')
require('QPushButton::mouseReleaseEvent(event);' in keyboard and 'if (nearby)' in keyboard,
        'tolerant click should only fire for a slightly out-of-bounds release')

# User confirmed Shift is good; do not modify its 3 states or visual style.
require('enum class ShiftState { Off, Once, CapsLock };' in source('compact_keyboard.h'),
        'Mobile10 Shift state must remain unchanged')
require('QIcon shiftIcon(bool dark, bool oneShot, bool capsLock)' in keyboard and
        'switch (shift_state_)' in keyboard and
        'case ShiftState::CapsLock:' in keyboard,
        'Mobile10 Shift indicator and behavior were modified')
require('space_key_->installEventFilter(this)' in keyboard and
        'void CompactKeyboard::changeLanguage()' in keyboard,
        'Samsung spacebar language swipe must remain')
require('const QString ru = QStringLiteral("йцукенгшщзхъфывапролджэячсмитьбю")' in view and
        'QChar key = character.toLower();' in view,
        'existing physical Russian key map must remain')
require('void DesktopView::onVirtualText(const QString& text)' in view and
        'view_->onVirtualText(text)' in window,
        'Unicode clipboard paste must remain distinct from the physical key queue')
require('int barThickness() const { return 30; }' in bar_header and
        'constexpr int kKeyHeight = 26;' in bar and
        'OvershootAlwaysOff' in bar,
        'Mobile10 compact horizontal-only KeyBar must remain')
require('QStringLiteral("ЛКМ")' in bar and 'QStringLiteral("Клав.")' in bar and
        'QStringLiteral("Вставить")' in bar,
        'remote controls must be preserved')
print('PASS: Mobile11 ordered held HID keys, tolerated touch drift, Mobile10 Shift and compact rail preserved')
