#!/usr/bin/env python3
"""Mobile10 regression assertions for Samsung layout + existing nested Aspia input."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
android = root / 'source/client/android'


def source(name):
    return (android / name).read_text(encoding='utf-8')


def require(ok, detail):
    if not ok:
        raise AssertionError(detail)


header = source('compact_keyboard.h')
kb = source('compact_keyboard.cc')
view = source('desktop_view.cc')
window = source('desktop_window.cc')
barh = source('key_bar.h')
bar = source('key_bar.cc')

require('width() * 75 / 100' in kb and
        'QStringLiteral("йцукенгшщзх")' in kb and
        'QStringLiteral("qwertyuiop")' in kb,
        'Preserve reduced landscape size and RU/EN letter row layout')
require('digit_font.setPixelSize(19)' in kb and
        'column->setStretch(0, 4)' in kb and
        'column->setStretch(r, 5)' in kb,
        'Number row must be shorter than letters, digits more readable')
require('column->setContentsMargins(6, 3, 6, 12)' in kb and
        'QColor("#080808")' in kb,
        'Keyboard needs dark gutters and bottom gap above the auxiliary strip')
require('setUtilityStyle(symbols_key_)' in kb and
        'setUtilityStyle(enter)' in kb and
        'setUtilityStyle(shift_key_)' in kb and
        'setUtilityStyle(backspace)' in kb and
        'background:#171717' in kb,
        'Samsung-style dark corner keys missing')
require('space_key_->installEventFilter(this)' in kb and
        'changeLanguage();' in kb and
        'qAbs(movement.x()) > threshold' in kb and
        'qAbs(movement.x()) > qAbs(movement.y()) * 1.4' in kb and
        'return true; // suppress the space-click' in kb and
        'language_label_->setText(' in kb and
        'previous_language' not in kb and
        'next_language' not in kb,
        'Spacebar must switch language on horizontal swipe, not by separate arrow keys')
require('footer->addWidget(space_key_, 11)' in kb and
        'footer->addWidget(symbols_key_, 3)' in kb and
        'footer->addWidget(enter, 3)' in kb and
        'QIcon enterIcon(bool dark)' in kb and
        'QIcon backspaceIcon(bool dark)' in kb,
        'Samsung bottom row proportions/icons missing')
require('ShiftState { Off, Once, CapsLock }' in header and
        'case ShiftState::Off: shift_state_ = ShiftState::Once;' in kb and
        'case ShiftState::Once: shift_state_ = ShiftState::CapsLock;' in kb and
        'case ShiftState::CapsLock: shift_state_ = ShiftState::Off;' in kb and
        'QIcon shiftIcon(bool dark, bool oneShot, bool capsLock)' in kb and
        'QColor("#4a9dff")' in kb and
        'shift_state_ == ShiftState::Once' in kb and
        '⇧●' not in kb and
        'setIconSize(QSize(31, 30))' in kb,
        'Shift must have fixed-width icon and three distinct Samsung-like states')
require('QSizePolicy::Ignored, QSizePolicy::Expanding' in kb and
        'letter_rows_[1]->setContentsMargins(home_indent, 0, home_indent, 0)' in kb and
        'bottom->setStretch(0, english ? 4 : 1)' in kb and
        'bottom->setStretch(10, english ? 4 : 1)' in kb,
        'Letter rows must not jump on Shift; English home/bottom row needs insets')
require('configureAlternate(letters_[0][4]' in kb and
        'configureAlternate(letters_[2][6]' in kb and
        'timer->setInterval(500)' in kb,
        'Long-press Ё/Ъ must remain')
require('void sig_text(const QString& text, bool russian_layout);' in header and
        '&DesktopView::onVirtualKeyboardText' in window and
        'sendKeyWithModifiers(usb)' in view and
        'const QString ru = QStringLiteral(' in view,
        'Physical key event delivery to nested Aspia must not regress')
require('QGuiApplication::clipboard()->text()' in window and
        'view_->onVirtualText(text)' in window,
        'Exact Unicode clipboard paste must remain')
require('int barThickness() const { return 30; }' in barh and
        'constexpr int kKeyHeight = 26;' in bar and
        'panel_layout_->setContentsMargins(2, 0, 2, 0)' in bar and
        'Qt::AlignVCenter' in bar and
        'QScrollerProperties::VerticalOvershootPolicy' in bar and
        'scroll_->verticalScrollBar()->setValue(0)' in bar,
        'Auxiliary rail must be short, centered, and never vertically scroll')
require('QStringLiteral("ЛКМ")' in bar and
        'QStringLiteral("Клав.")' in bar and
        'QStringLiteral("Вставить")' in bar and
        'QStringLiteral("Впис.")' not in bar,
        'LMB, keyboard and paste actions must be preserved')
require('compact_keyboard_visible_ && view_' in window and
        'QGuiApplication::inputMethod()->hide()' in window and
        'layoutControls();' in window,
        'Keep app-local keyboard on Activity foreground resume')
print('PASS: Mobile10 Samsung geometry, language swipe, three-state Shift, compact fixed-height rail, nested physical keys')
