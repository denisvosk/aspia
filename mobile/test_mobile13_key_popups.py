#!/usr/bin/env python3
"""Mobile13 source-level regression gates. Real Samsung interaction testing is required."""
from pathlib import Path
import re
import sys

root = Path(sys.argv[1]).resolve()
a = root / 'source/client/android'
h = (a/'compact_keyboard.h').read_text(encoding='utf-8')
kb = (a/'compact_keyboard.cc').read_text(encoding='utf-8')
w = (a/'desktop_window.cc').read_text(encoding='utf-8')
v = (a/'desktop_view.cc').read_text(encoding='utf-8')
bar = (a/'key_bar.cc').read_text(encoding='utf-8')

def check(ok, msg):
    if not ok:
        raise AssertionError(msg)

check('enum class InputMode { HID, TXT, BUF };' in h, 'three input modes are missing')
check('InputMode input_mode_ = InputMode::HID' in h, 'new sessions must start in HID')
check('QStringLiteral("HID")' in kb and 'QStringLiteral("TXT")' in kb and
      'QStringLiteral("BUF")' in kb, 'legible mode labels are missing')
check('footer->addWidget(mode_key_, 2)' in kb and
      'footer->addWidget(space_key_, 11)' in kb and
      'footer->addWidget(dot_key_, 2)' in kb,
      'mode key must replace comma to LEFT of full Samsung spacebar')
# A short accidental tap must NEVER change the input transport.
check('mode_hold_timer_->setInterval(500);' in kb and
      'connect(mode_key_, &QPushButton::pressed' in kb and
      'connect(mode_hold_timer_, &QTimer::timeout, this, &CompactKeyboard::showModePopup);' in kb and
      'connect(mode_key_, &QPushButton::clicked' in kb and
      'mode_hold_fired_' in h,
      'mode change requires a 500ms hold rather than a quick tap')
check('void CompactKeyboard::showModePopup()' in kb and
      'mode_popup_->setFocusPolicy(Qt::NoFocus);' in kb and
      'const QList<QPair<InputMode, QString>> options' in kb and
      'void CompactKeyboard::selectInputMode(InputMode mode)' in kb and
      'selectInputMode(selected);' in kb,
      'long press must expose explicit HID/TXT/BUF menu choices')
mode_click = kb.split('connect(mode_key_, &QPushButton::clicked, this, [this]()', 1)[1].split('dot_key_ = newKey', 1)[0]
check(not re.search(r'\binput_mode_\s*=(?!=)', mode_click) and
      'emit sig_draftRequested(draft_)' in mode_click,
      'short tap must not cycle transport; BUF draft confirmation remains accessible')
check('if (mode_hold_fired_)' in mode_click and
      'mode_hold_fired_ = false' in mode_click and
      'mode_key_->setDown(false);' in kb,
      'releasing a held mode key must not trigger a second action')
check('mode_popup_->geometry().contains(release_pos)' in kb and
      'selectInputMode(column == 0 ? InputMode::HID' in kb and
      'if (input_mode_ == InputMode::BUF && !draft_.isEmpty())' in kb,
      'hold-slide-release selection and buffered draft protection required')
# Mobile13: punctuation geometry and explicit letter selection replace the old hold behavior.
check('void CompactKeyboard::showSymbolPopup()' in kb and
      'symbol_timer_->start(key == dot_key_ ? 460 : 500);' in kb and
      'if (symbolEvent(watched, event))' in kb,
      'all three popup keys must share the hold/slide/release path')
popup = kb.split('void CompactKeyboard::showSymbolPopup()', 1)[1].split(
    'int CompactKeyboard::symbolAt', 1)[0]
check(re.search(r'symbol_choices_ = \{\s*QStringLiteral\(":"\),\s*QStringLiteral\("\^"\),\s*'
                r'QStringLiteral\("%"\),\s*QStringLiteral\("\$"\),\s*QStringLiteral\("#"\),\s*'
                r'QStringLiteral\("@"\),\s*QStringLiteral\("\x27"\),\s*QStringLiteral\("!"\),\s*'
                r'QStringLiteral\("\?"\),\s*QStringLiteral\(","\)\s*\}', popup),
      'exact Samsung-style 2x5 character order is required')
check('const int columns = dot ? 5 : 1;' in popup and
      'const int rows = dot ? 3 : 1;' in popup and
      '(i / 5) * 2 * cell_h' in popup and
      'center - (columns - 1) * cell_w - cell_w / 2' in popup,
      'comma is centered directly over dot, with an empty middle row')
check('emit sig_text' not in popup and 'chooseSymbol' not in popup.split(
      'connect(button,', 1)[0],
      'opening popup itself must never emit a letter')
check('configureAlternate(letters_[0][4]' in kb and
      'configureAlternate(letters_[2][6]' in kb and
      'key->setProperty("alternateLower", lower);' in kb and
      'key->setProperty("alternateUpper", upper);' in kb and
      '"alternateLower" :' in popup and '"alternateUpper"' in popup,
      'Russian e/yo and soft/hard sign use the current Shift state')
check('alternateConsumed' not in kb and
      'else if (on_key)\n            highlightSymbol(-1);' in kb and
      'else if (key == dot_key_ && !moved && on_key)\n            chooseSymbol(9);' in kb,
      'stationary letter hold stays open; only dot has default comma shortcut')
check('symbol_buttons_[i]->geometry().contains(local)' in kb and
      'return -1; // the middle spacer' in kb and
      'key->setDown(false);' in kb and 'event->accept();\n        return true;' in kb,
      'select by both axes and suppress ordinary key release after hold')
check('void CompactKeyboard::hideEvent(QHideEvent* event)' in kb and
      'cancelSymbolPopup();\n    QWidget::resizeEvent(event);' in kb and
      'suppressed_release_' in h and 'setFocusPolicy(Qt::NoFocus)' in popup,
      'popup dismissal, rotation, and no-focus policy must remain')
check('key == QChar(0x60)) ? 0x070035' in v and
      "key == QChar(']')) ? 0x070030" in v,
      'HID Yo and hard sign must use exact USB keyboard usages')
check('case CompactKeyboard::InputMode::HID:' in w and
      'view_->onVirtualKeyboardText(text, russian_layout);' in w and
      'case CompactKeyboard::InputMode::TXT:' in w and
      'view_->onVirtualText(text);' in w and
      'case CompactKeyboard::InputMode::BUF:' in w and
      'compact_keyboard_->appendDraft(text);' in w,
      'exactly one transport per mode')
check('queueKeyboardStroke(usb, local_shift)' in v and
      'QTimer::singleShot(32, this' in v and
      'QTimer::singleShot(6, this' in v,
      'retain measured HID key intervals from Mobile11')
check('QColor("#4a9dff")' in kb and
      'shift_key_->setIconSize(QSize(21, 20));' in kb and
      'backspace->setIconSize(QSize(21, 17));' in kb and
      'font.setPixelSize(20);' in kb,
      'retain Shift, small arrows and 20px letter captions')
check('int barThickness() const { return 30; }' in
      (a/'key_bar.h').read_text(encoding='utf-8') and
      'constexpr int kKeyHeight = 26;' in bar,
      'retain 30px compact fixed horizontal KeyBar')
check('kMaxDraft = 4096' in kb and
      'emit sig_draftRequested(draft_);' in kb and
      'Clipboard::addFormat(&event, Clipboard::kMimeTypeTextUtf8, draft.toUtf8());' in w and
      'onClipboardEvent(event);' in w and
      'question.clickedButton() == discard' in w,
      'BUF must collect privately and ask explicitly before remote clipboard overwrite')
# Scope the negative checks to the BUF branch: the pre-existing DesktopWindow
# can independently use Qt timers and clipboard APIs for ordinary sessions.
draft_handler = w.split('connect(compact_keyboard_, &CompactKeyboard::sig_draftRequested, this,', 1)[1]
draft_handler = draft_handler.split('compact_keyboard_->discardDraft();\n            QMessageBox::information', 1)[0]
check('QGuiApplication::clipboard()->setText(' not in draft_handler and
      'QTimer::singleShot(500' not in draft_handler and
      'sendCtrlV()' not in draft_handler,
      'BUF must not silently touch phone clipboard or auto-paste')
check('QStringLiteral("ЛКМ")' in bar and
      'QStringLiteral("Клав.")' in bar and
      'QStringLiteral("Вставить")' in bar,
      'keep established LMB, keyboard and Android clipboard paste')
print('PASS: Mobile13 Samsung grid, explicit Ё/Ъ, existing HID/TXT/BUF and Mobile11 controls preserved')
