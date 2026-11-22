#!/usr/bin/env python3
"""Mobile 8 source gates for the reduced Samsung-style keyboard."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
android = root / "source/client/android"


def read(name: str) -> str:
    return (android / name).read_text(encoding="utf-8")


def check(ok: bool, reason: str) -> None:
    if not ok:
        raise AssertionError(reason)


kb = read("compact_keyboard.cc")
header = read("compact_keyboard.h")
bar = read("key_bar.cc")
window = read("desktop_window.cc")
view = read("desktop_view.cc")
manifest = read("packaging/AndroidManifest.xml")
clipboard = (root / "source/common/clipboard_android.cc").read_text(encoding="utf-8")

check("class CompactKeyboard final : public QWidget" in header,
      "Only app-local Qt Widgets keyboard must be used")
check('QStringLiteral("йцукенгшщзх")' in kb and
      'QStringLiteral("фывапролджэ")' in kb and
      'QStringLiteral("ячсмитьбю")' in kb,
      "Samsung-layout Russian rows missing")
check('QStringLiteral("qwertyuiop")' in kb and
      'QStringLiteral("asdfghjkl")' in kb,
      "English keyboard layout missing")
check("for (int i = 1; i <= 10; ++i)" in kb and
      "yo_key_" not in kb and
      'QStringLiteral("йцукенгшщзхъ")' not in kb,
      "Number row must be digits only; no PC-style Ё/Ъ keys")
check('configureAlternate(letters_[0][4]' in kb and
      'configureAlternate(letters_[2][6]' in kb,
      "Ё and Ъ must be reachable by long-press")
check('timer->setInterval(500)' in kb and
      'alternateConsumed' in kb,
      "Long press must suppress normal letter on release")
check("width() * 75 / 100" in kb and
      "void CompactKeyboard::resizeEvent" in kb,
      "Landscape keyboard must be centered and no wider than 75%")
check("landscape_keys_" not in kb and "kUsbTab" not in kb,
      "Esc/Tab/arrows must stay on KeyBar, not the typing keyboard")
check('space_key_->setText(ru_ ? QStringLiteral("Русский")' in kb and
      ('emit sig_text(QStringLiteral(" "))' in kb or
       'emit sig_text(QStringLiteral(" "), ru_)' in kb),
      "Space with language arrows missing")
check('QStringLiteral("Enter")' in kb and 'kUsbEnter' in kb,
      "Visible Enter key missing")
check("key->setFocusPolicy(Qt::NoFocus)" in kb,
      "Typing keys must not steal remote focus")
check('QStringLiteral("ЛКМ")' in bar and
      'QStringLiteral("Клав.")' in bar and
      'QStringLiteral("Вставить")' in bar,
      "LMB/Klav/Paste must remain intact")
check('QStringLiteral("Впис.")' not in bar,
      "Remove dangerous accidental Fit button from the scroll rail")
check('QStringLiteral("Повор.")' not in bar,
      "Rotate must remain in 3-dot menu only")
check("button->setAccentColor(palette().color(QPalette::WindowText))" in bar,
      "KeyBar labels must use theme foreground instead of blue accent")
check("height() * 44 / 100" in window and
      "height() * 38 / 100" in window,
      "Keyboard geometry must remain correct in both orientations")
check("view_->setOcclusionHeight(covered)" in window and
      "setOcclusionHeight(int height)" in view,
      "Do not regress viewport pan above keyboard")
check("onVirtualText(const QString& text)" in view and
      'QGuiApplication::clipboard()->text()' in window,
      "Remote Unicode clipboard paste must remain functional")
check("adjustNothing" in manifest and
      "refreshFromSystem()" in clipboard,
      "Android IME and foreground clipboard behavior must be preserved")
print("PASS: Mobile8 compact Samsung geometry, Unicode, LMB/Klav, theme and no Fit")
