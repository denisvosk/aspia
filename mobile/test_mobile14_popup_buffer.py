#!/usr/bin/env python3
"""Mobile14 source-level regression gates. Actual Android and remote clipboard tests remain required."""
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
check(not re.search(r'\binput_mode_\s*=(?!=)', mode_click),
      'short tap must not cycle transport')
check('modeAt(mode_key_->mapTo(this, mouse->position().toPoint()))' in kb and
      'mode_buttons_[i]->geometry().contains(local)' in kb and
      'highlightMode(modeAt(' in kb and
      'index = static_cast<int>(input_mode_)' in kb and
      'mode_key_->setDown(false);' in kb,
      'mode choices use actual geometry, blue drag feedback and current mode highlight')
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
check('symbol_popup_->mapFromGlobal(mapToGlobal(point))' in kb and
      'symbol_buttons_[i]->geometry().contains(local)' in kb and
      'return -1; // the middle spacer' in kb and
      'key->setDown(false);' in kb and 'event->accept();\n        return true;' in kb,
      'select by both axes and suppress ordinary key release after hold')
check('void CompactKeyboard::hideEvent(QHideEvent* event)' in kb and
      'cancelSymbolPopup();\n    dismissModePopup();\n    QWidget::resizeEvent(event);' in kb and
      'suppressed_release_' in h and 'setFocusPolicy(Qt::NoFocus)' in popup,
      'popup dismissal, rotation, and no-focus policy must remain')
check('QWidget* surface = dot || !parentWidget() ? this : parentWidget();' in popup and
      'qMax(58, symbol_anchor_->width() + 16)' in popup and
      'qMax(56, symbol_anchor_->height() + 16)' in popup and
      'symbol_popup_->setParent(surface)' in popup and
      'symbol_popup_->setParent(this);' in kb and
      'symbol_buttons_[0]->setStyleSheet(index == 0 ?' in kb and
      'manhattanLength() <= 20)' in kb,
      'letter popups must be full-sized, visible above keyboard, highlighted and tolerant of drift')
check('key == QChar(0x60)) ? 0x070035' in v and
      "key == QChar(']')) ? 0x070030" in v,
      'HID Yo and hard sign must use exact USB keyboard usages')
check('case CompactKeyboard::InputMode::HID:' in w and
      'view_->onVirtualKeyboardText(text, russian_layout);' in w and
      'case CompactKeyboard::InputMode::TXT:' in w and
      'view_->onVirtualText(text);' in w and
      'case CompactKeyboard::InputMode::BUF:' in w and
      'view_->queueBufferPaste(text)' in w,
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
check('appendDraft' not in h and 'sig_draftRequested' not in w and
      'QMessageBox::warning(this, QStringLiteral("Экспериментальный режим BUF")' in kb and
      'QMessageBox::Yes | QMessageBox::Cancel' in kb,
      'live clipboard typing replaces hidden draft, requires explicit consent')
check('Clipboard::addFormat(&event, Clipboard::kMimeTypeTextUtf8, text.toUtf8());' in w and
      'onClipboardEvent(event);' in w and 'desktop_config_.clipboard()' in w,
      'send real clipboard event, respect configured permission')
check('stroke.usb_keycode = 0x070019' in v and
      'stroke.modifiers = { 0x0700e0 }' in v and
      v.index('!buffer_sender_(stroke.clipboard_text)') <
      v.index('QTimer::singleShot(650, this') and
      'epoch != buffer_epoch_' in v and 'QTimer::singleShot(250, this, next)' in v,
      'clipboard must precede paced Ctrl+V, with cancellation and settle interval')
check('view_->hasCommandModifier()' in w and
      '&DesktopView::onSpecialKey);' in w and
      'last.clipboard_text += text;' in v,
      'special keys and sticky shortcuts remain physical; consecutive text may coalesce')
check('++buffer_epoch_;' in v and
      'cancelBufferInput();' in v and
      w.count('view_->cancelBufferInput();') >= 4 and
      '&DesktopView::cancelBufferInput);' in w,
      'pending clipboard input must not cross mode or session changes')
check('void DesktopWindow::pastePhoneText()' in w and
      'else view_->onVirtualText(text);' in w,
      'BUF toolbar paste uses same queue; other modes retain Unicode path')
check('QStringLiteral("ЛКМ")' in bar and
      'QStringLiteral("Клав.")' in bar and
      'QStringLiteral("Вставить")' in bar,
      'keep established LMB, keyboard and Android clipboard paste')
print('PASS: Mobile14 full-sized alternatives, mode hover, opt-in ordered BUF and retained controls')
