#!/usr/bin/env python3
"""Mobile9 source gates; must not substitute for a live two-Aspia Windows test."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
android = root / "source/client/android"

def read(path):
    return path.read_text(encoding="utf-8")

def check(ok, why):
    if not ok:
        raise AssertionError(why)

h = read(android / 'compact_keyboard.h')
kb = read(android / 'compact_keyboard.cc')
barh = read(android / 'key_bar.h')
bar = read(android / 'key_bar.cc')
vh = read(android / 'desktop_view.h')
view = read(android / 'desktop_view.cc')
window = read(android / 'desktop_window.cc')
clip = read(root / 'source/common/clipboard_android.cc')

check('void sig_text(const QString& text, bool russian_layout)' in h,
      'Keyboard must transmit selected layout to physical key mapper')
check('connect(compact_keyboard_, &CompactKeyboard::sig_text, view_, &DesktopView::onVirtualKeyboardText)' in window,
      'Physical touch key event path is not connected')
check('void DesktopView::onVirtualKeyboardText(const QString& text, bool russian_layout)' in view,
      'Separate physical key route is missing')
check('sendKeyWithModifiers(usb)' in view.split('void DesktopView::onVirtualKeyboardText', 1)[1].split('void DesktopView::onVirtualText', 1)[0],
      'Typed keys must transmit real USB events to nested Aspia')
check('const QString ru = QStringLiteral("йцукенгшщзхъфывапролджэячсмитьбю")' in view,
      'Physical Russian layout translation missing')
check('key = QChar(0x60)' in view and 'key = QChar(\'/\')' in view,
      'Russian hard/yo and punctuation scan code cases missing')
check('void DesktopView::onVirtualText(const QString& text)' in view and
      'QGuiApplication::clipboard()->text()' in window and
      'view_->onVirtualText(text)' in window and
      'refreshFromSystem()' in clip,
      'Unicode text paste must remain separate and unmodified')
check('QColor("#080808")' in kb and 'keys_panel_->setPalette(pal)' in kb,
      'Near-black gutters must be visible between dark key caps')
check('column->setStretch(0, 4)' in kb and
      'column->setStretch(r, 5)' in kb and
      'digit_font.setPixelSize(15)' in kb,
      'Samsung smaller number row must remain')
check('QIcon backspaceIcon(bool dark)' in kb and
      'backspace->setIcon(backspaceIcon(dark_theme_))' in kb and
      'newKey(QStringLiteral("⌫"))' not in kb,
      'Backspace needs own vector icon, no unsupported font glyph')
check('int barThickness() const { return 33; }' in barh and
      'constexpr int kKeyHeight = 28;' in bar,
      'Bar should be 25 percent shorter')
check('QStringLiteral("ЛКМ")' in bar and
      'QStringLiteral("Клав.")' in bar and
      'QStringLiteral("Вставить")' in bar and
      'QStringLiteral("Впис.")' not in bar and
      'QStringLiteral("Повор.")' not in bar,
      'Do not change LMB, Keyboard, Paste, or resurrect Fit/Rotate')
check('key_bar_->setVerticalMode(false)' in window and
      'view_->setOcclusionHeight(covered)' in window,
      'Do not regress keyboard overlay and pan')
check('for (int i = 1; i <= 10; ++i)' in kb and
      'QStringLiteral("йцукенгшщзх")' in kb and
      'width() * 75 / 100' in kb,
      'Samsung numeric row, letters and reduced centered landscape width required')
print('PASS: Mobile9 layout, nested-Aspia hardware keys, Unicode paste and thin strip')
