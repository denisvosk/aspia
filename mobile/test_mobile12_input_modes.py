#!/usr/bin/env python3
"""Mobile12 source-level release gates. Real Samsung and nested-session tests remain required."""
from pathlib import Path
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
check('void CompactKeyboard::showPunctuationPopup()' in kb and
      'punctuation_timer_->setInterval(460);' in kb and
      'punctuation_popup_->setAttribute(Qt::WA_TransparentForMouseEvents)' in kb and
      'dot_key_->installEventFilter(this)' in kb and
      'punctuation_moved_' in kb and
      'const QString chosen = punctuation_choices_.at(punctuation_index_);' in kb,
      'long-hold popup and sliding symbol selection are missing')
check('QStringLiteral(",")' in kb and 'QStringLiteral("?")' in kb and
      'QStringLiteral("!")' in kb,
      'popup must contain frequent punctuation including comma')
check('configureAlternate(letters_[0][4]' in kb and
      'configureAlternate(letters_[2][6]' in kb and
      'timer->setInterval(500)' in kb,
      'long-hold Russian Yo and hard sign must remain')
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
check('QGuiApplication::clipboard()->setText(' not in w and
      'QTimer::singleShot(500' not in w and
      'sendCtrlV()' not in w,
      'must not secretly overwrite local clipboard or automatically paste before remote sync')
check('QStringLiteral("ЛКМ")' in bar and
      'QStringLiteral("Клав.")' in bar and
      'QStringLiteral("Вставить")' in bar,
      'keep established LMB, keyboard and Android clipboard paste')
print('PASS: Mobile12 3-mode key, punctuation slide, RU HID usages, safe BUF draft, Mobile11 HID/Shift preserved')
