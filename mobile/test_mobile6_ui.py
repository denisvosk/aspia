#!/usr/bin/env python3
"""Check Mobile 6 UI invariants after all pinned source overlays.

This is a source-level guard, NOT an interactive Samsung/remote Host test.
"""
from __future__ import annotations
from pathlib import Path
import sys

root=Path(sys.argv[1])
android=root/'source/client/android'

def read(name):
    return (android/name).read_text(encoding='utf-8')

def check(ok, message):
    if not ok:
        raise AssertionError(message)

manifest=read('packaging/AndroidManifest.xml')
view=read('desktop_view.cc')
viewh=read('desktop_view.h')
win=read('desktop_window.cc')
winh=read('desktop_window.h')
bar=read('key_bar.cc')
barh=read('key_bar.h')
app=read('main_window.cc')
java=read('packaging/src/org/aspia/client/ClientActivity.java')

check('android:windowSoftInputMode="adjustNothing"' in manifest, 'IME must overlay, not resize')
check('adjustResize' not in manifest, 'Old keyboard resize policy remains')
check('QT_ANDROID_NO_FULLSCREEN_KEYBOARD' in java, 'Landcape keyboard extract-mode guard missing')
check('FLAG_SECURE' not in java, 'Screenshots must work')
check('void DesktopView::showSoftwareKeyboard()' in view and 'method->hide();' in view,
      'Keyboard button must toggle closed')
check('    return qMax<qreal>(1.0, height() - key_bar_height_);' in view,
      'IME must not alter fitted viewport height')
check('    // change zoom, frame offset or cursor focus on its appearance.' in view,
      'Opening the keyboard still pans or scales the frame')
check('setVerticalMode(keyboard_visible)' in win and
      'key_bar_->setGeometry(0, 0, key_bar_->railThickness()' in win,
      'Keyboard-visible control bar must move left')
check('key_bar_->setVerticalMode(false)' not in win, 'Bar orientation must follow IME not a fixed flag')
check('QScroller::grabGesture(scroll_->viewport(), QScroller::TouchGesture)' in bar and
      'horizontalScrollBar()' in bar and 'verticalScrollBar()' in bar,
      'Control bar needs real 2-direction access')
check('sig_leftButtonHeld' in barh and 'void DesktopView::onLeftButtonHeld(bool held)' in view,
      'Physical LMB hold signal missing')
check('button_mask_ = left_button_held_ ? proto::input::MouseEvent::LEFT_BUTTON : 0;' in view,
      'First finger on screen must preserve panel LMB press')
check('!left_button_held_' in view and 'left_button_held_ = false' in view,
      'LMB must be released on cancel without false click')
check('QPushButton::pressed' in bar and 'QPushButton::released' in bar,
      'Mouse button needs separate press and release, not clicked')
check('sticky_modifiers_.clear();\n    emit sig_modifiersCleared();\n}' not in
      view.split('void DesktopView::cancelTouch()',1)[1].split('//--------------------------------------------------------------------------------------------------',1)[0],
      'Cancelled touch should not clear Ctrl/Shift before a shortcut is sent')
check('void DesktopView::sendTaskManager()' in view and
      'sendRawKey(kUsbLeftCtrl, true)' in view and 'sendRawKey(shift, true)' in view,
      'Reliable Task Manager shortcut missing')
check('sig_taskManagerRequested' in barh and 'sig_taskManagerRequested, view_, &DesktopView::sendTaskManager' in win,
      'Task Manager action not connected')
check('    const bool keyboard_visible = keyboard_inset_ > 0;' in win and
      'key_bar_->show();' in win, 'Controls must remain reachable in portrait')
check('Правая кнопка мыши' not in win, 'Duplicate right-click item left in 3-dot menu')
check('QTimer::singleShot(0, this' in app and 'relock();' in app,
      'Lock prompt must not be synchronously entered from Activity state signal')
check('QTimer::singleShot(0, view_' in win,
      'Resume should request a repaint of the native surface')
check('proto::desktop::CHANNEL_ID_LEGACY' in win,
      'Old 2.7 desktop mouse/key input routing must remain')
check('void DesktopView::onEdgePan()' in view,
      'Proven edge pan must be untouched')
check('Win+E' in bar and 'Пуск' in bar,
      'Both Win chord and direct Start button must be accessible')
print('PASS: Mobile 6 IME overlay, vertical-left controls, LMB press/release, shortcuts, resume and legacy protocol guards')
