#!/usr/bin/env python3
"""Mobile 7 source-level release gates; Android touch/IME still need Samsung validation."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
android = root / 'source/client/android'

def read(name):
    return (android / name).read_text(encoding='utf-8')

def check(condition, reason):
    if not condition:
        raise AssertionError(reason)

kb = read('compact_keyboard.cc')
kbh = read('compact_keyboard.h')
bar = read('key_bar.cc')
barh = read('key_bar.h')
window = read('desktop_window.cc')
view = read('desktop_view.cc')
viewh = read('desktop_view.h')
clip = (root / 'source/common/clipboard_android.cc').read_text(encoding='utf-8')
manifest = read('packaging/AndroidManifest.xml')
java = read('packaging/src/org/aspia/client/ClientActivity.java')

check('class CompactKeyboard final : public QWidget' in kbh,
      'Compact keyboard must be an app-local Qt Widgets module')
check('QStringLiteral("йцукенгшщзхъ")' in kb and 'QStringLiteral("qwertyuiop")' in kb,
      'Russian/English layout data missing')
check('QStringLiteral("ё")' in kb and 'QStringLiteral("Ё")' in kb,
      'Russian yo/Yo must remain accessible')
check('emit sig_text' in kb and 'emit sig_key' in kb,
      'Keyboard not wired to Unicode and physical key paths')
check('setLandscapeMode(bool enabled)' in kb and '0x070050' in kb,
      'Landscape keyboard must contain navigation arrows')
check('addAction(controls_layout_, QStringLiteral("Повор.")' not in bar,
      'Rotation must only be in the three-dot menu')
check('action_sheet_->addItem(QStringLiteral("Повернуть экран")' in window,
      '3-dot rotation must remain available')
check('sig_pastePhoneText' in barh and 'pastePhoneText()' in window,
      'Direct Android paste action not wired')
check('QGuiApplication::clipboard()->text()' in window and
      'view_->onVirtualText(text)' in window,
      'Paste must transmit phone text to remote Windows without intermediary cloud')
check('refreshFromSystem()' in clip and 'clipboard_->refreshFromSystem()' in window,
      'Foreground clipboard refresh missing')
check('view_->setAttribute(Qt::WA_InputMethodEnabled, false)' in window,
      'Android Samsung/GBoard system keyboard must not open for remote typing')
check('compact_keyboard_visible_ = !compact_keyboard_visible_' in window,
      'App keyboard show/hide action missing')
check('key_bar_->setVerticalMode(false);' in window,
      'Function bar must remain horizontal')
check('const int bar_y = qMax(0, height() - bar_height);' in window and
      'compact_keyboard_->setGeometry(0, qMax(0, bar_y - keyboard_height)' in window,
      'Fixed bottom bar and overlay keyboard above it missing')
check('view_->setOcclusionHeight(covered)' in window and
      'occlusion_follow_armed_ = false;' in view and
      'visibleBottom()' in view and
      'void DesktopView::onEdgePan()' in view,
      'Keyboard must not alter scale; mouse follow uses visible-region geometry')
check('keyboard_inset_ - key_bar_height_' not in view,
      'Keyboard must not force an IME zoom refit')
check('allowAction() const' in bar and 'scroll_cooldown_.elapsed() > 220' in bar,
      'Scroll-to-click guard missing')
check('sig_leftButtonHeld' in barh and 'onLeftButtonHeld' in view,
      'Holdable LMB missing')
check('proto::desktop::CHANNEL_ID_LEGACY' in window,
      'Legacy 2.7 input routing missing')
check('QTimer::singleShot(0, view_' in window,
      'Resume repaint from Mobile6 must remain')
check('FLAG_SECURE' not in java and 'adjustNothing' in manifest,
      'Android screenshots and no-resize soft input must remain')
print('PASS: Mobile7 fixed bottom KeyBar, compact app-only RU/EN keyboard, safe scroll, viewport pan and Android clipboard')
