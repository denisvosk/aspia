#!/usr/bin/env python3
"""Mobile9: Samsung-style key geometry and physical events for nested Aspia.

Applies after Mobile8 on the same pinned source, without altering Host,
Router, Relay, clipboard paste or desktop gesture processing.
"""
from pathlib import Path
import sys


def once(path: Path, old: str, new: str):
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"{path}: expected a single anchor, found {text.count(old)}: {old[:95]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def apply(root: Path):
    android = root / 'source/client/android'
    h = android / 'compact_keyboard.h'
    cc = android / 'compact_keyboard.cc'
    view_h = android / 'desktop_view.h'
    view_cc = android / 'desktop_view.cc'
    window = android / 'desktop_window.cc'
    bar_h = android / 'key_bar.h'
    bar_cc = android / 'key_bar.cc'

    once(h, '    bool landscape_ = false;',
         '    bool dark_theme_ = true;\n    bool landscape_ = false;')
    once(h, '    void sig_text(const QString& text);',
         '    void sig_text(const QString& text, bool russian_layout);')
    once(cc, '#include <QFont>\n',
         '#include <QFont>\n#include <QIcon>\n#include <QPainter>\n'
         '#include <QPainterPath>\n#include <QPixmap>\n')
    once(cc, 'constexpr quint32 kUsbBackspace = 0x07002a;\n', '''constexpr quint32 kUsbBackspace = 0x07002a;

// A real vector backspace instead of a font glyph unsupported by Samsung/Qt.
QIcon backspaceIcon(bool dark)
{
    QPixmap pixmap(48, 36);
    pixmap.fill(Qt::transparent);
    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing);
    QPen pen(dark ? QColor("#f5f5f5") : QColor("#202020"), 2.3,
             Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin);
    painter.setPen(pen);
    painter.setBrush(Qt::NoBrush);
    QPainterPath outline;
    outline.moveTo(17, 5);
    outline.lineTo(43, 5);
    outline.quadTo(46, 5, 46, 9);
    outline.lineTo(46, 27);
    outline.quadTo(46, 31, 42, 31);
    outline.lineTo(17, 31);
    outline.lineTo(4, 18);
    outline.closeSubpath();
    painter.drawPath(outline);
    painter.drawLine(25, 12, 36, 24);
    painter.drawLine(36, 12, 25, 24);
    return QIcon(pixmap);
}
''')
    once(cc, '''    QPalette pal = palette();
    pal.setColor(QPalette::Window, Controls::surfaceColor());
    setPalette(pal);''',
    '''    // Reduced Samsung keyboard: almost black gutters between grey keys.
    dark_theme_ = palette().color(QPalette::Window).lightness() < 128;
    QPalette pal = palette();
    pal.setColor(QPalette::Window,
                 dark_theme_ ? QColor("#080808") : QColor("#f1f1f3"));
    setPalette(pal);''')
    once(cc, '''    keys_panel_ = new QWidget(this);
    keys_panel_->setFocusPolicy(Qt::NoFocus);''',
    '''    keys_panel_ = new QWidget(this);
    keys_panel_->setFocusPolicy(Qt::NoFocus);
    keys_panel_->setAutoFillBackground(true);
    keys_panel_->setPalette(pal);''')
    once(cc, '''    column->setContentsMargins(4, 4, 4, 5);
    column->setSpacing(5);''',
    '''    column->setContentsMargins(6, 3, 6, 5);
    column->setSpacing(8);''')
    once(cc, '        row->setSpacing(5);', '        row->setSpacing(7);')
    once(cc, '''        QPushButton* key = newKey(digit);
        numbers->addWidget(key, 1);''',
    '''        QPushButton* key = newKey(digit);
        QFont digit_font = key->font();
        digit_font.setPixelSize(15);
        key->setFont(digit_font);
        numbers->addWidget(key, 1);''')
    once(cc, '            QPushButton* backspace = newKey(QStringLiteral("⌫"));\n',
    '''            QPushButton* backspace = newKey(QString());
            backspace->setIcon(backspaceIcon(dark_theme_));
            backspace->setIconSize(QSize(32, 25));
''')
    once(cc, '''    updatePanelWidth();
    updateLabels();
}''',
    '''    // Samsung digits are about 80% of the height of letter keys.
    column->setStretch(0, 4);
    for (int r = 1; r < 5; ++r)
        column->setStretch(r, 5);
    updatePanelWidth();
    updateLabels();
}''')
    once(cc, '    const bool dark = palette().color(QPalette::Window).lightness() < 128;',
         '    const bool dark = dark_theme_;')

    # Pass the selected virtual-keyboard layout along with each local key.
    # Clipboard paste continues to use the complete Unicode TextEvent path.
    for old, new in [
        ('emit sig_text(digit);', 'emit sig_text(digit, ru_);'),
        ('emit sig_text(QStringLiteral(","));', 'emit sig_text(QStringLiteral(","), ru_);'),
        ('emit sig_text(QStringLiteral(" "));', 'emit sig_text(QStringLiteral(" "), ru_);'),
        ('emit sig_text(QStringLiteral("."));', 'emit sig_text(QStringLiteral("."), ru_);'),
        ('emit sig_text(letter);', 'emit sig_text(letter, ru_);'),
        ('emit sig_text(shifted_ ? upper : lower);',
         'emit sig_text(shifted_ ? upper : lower, ru_);'),
    ]:
        once(cc, old, new)

    once(view_h, '    void onVirtualText(const QString& text);',
         '    void onVirtualText(const QString& text);\n'
         '    void onVirtualKeyboardText(const QString& text, bool russian_layout);')
    once(view_cc,
         '// Unicode goes as TextEvent; Ctrl/Alt/Win chords become physical USB keystrokes.',
         '''// Touch keys use physical USB scan codes, not KEYEVENTF_UNICODE.
// Windows delivers Unicode as VK_PACKET; nested Qt/Aspia clients may ignore
// this event because the hardware scan code is empty. Normal text via
// Android Clipboard retains the original Unicode path below.
void DesktopView::onVirtualKeyboardText(const QString& text, bool russian_layout)
{
    if (text.size() != 1)
    {
        onVirtualText(text);
        return;
    }

    QChar character = text.at(0);
    bool shift_needed = character.isUpper();
    QChar key = character.toLower();

    // RU uses the same physical positions as an ordinary Russian PC keyboard.
    // The selected keyboard language must match the active Windows layout.
    const QString ru = QStringLiteral("йцукенгшщзхъфывапролджэячсмитьбю");
    const QString en = QStringLiteral("qwertyuiop[]asdfghjkl;'zxcvbnm,.");
    const int index = ru.indexOf(key);
    if (index >= 0)
        key = en.at(index);
    else if (key == QChar(0x0451))  // Ё
        key = QChar(0x60);          // grave key
    else if (russian_layout && key == QChar('.'))
        key = QChar('/');           // Russian period
    else if (russian_layout && key == QChar(','))
    {
        key = QChar('/');           // Russian comma is Shift+slash
        shift_needed = true;
    }

    // Common US shifted symbol keycaps (1..0, - = and punctuation).
    const QString shifted = QStringLiteral("!@#$%^&*()_+{}|:\"<>?");
    const QString plain = QStringLiteral("1234567890-=[]\\;',./");
    const int special = shifted.indexOf(character);
    if (!russian_layout && special >= 0 && special < plain.size())
    {
        key = plain.at(special);
        shift_needed = true;
    }

    const quint32 usb = KeycodeConverter::qtKeycodeToUsbKeycode(
        key.toUpper().unicode());
    if (usb == KeycodeConverter::invalidUsbKeycode())
    {
        onVirtualText(text);  // Fallback for uncommon Unicode symbols.
        return;
    }

    constexpr quint32 kShift = 0x0700e1;
    const bool local_shift = shift_needed && !sticky_modifiers_.contains(kShift);
    if (local_shift)
        sendRawKey(kShift, true);
    sendKeyWithModifiers(usb);
    if (local_shift)
        sendRawKey(kShift, false);
}

// Unicode remains available for long texts, including Android paste.
// Unicode goes as TextEvent; Ctrl/Alt/Win chords become physical USB keystrokes.''')
    once(window,
         'connect(compact_keyboard_, &CompactKeyboard::sig_text, view_, &DesktopView::onVirtualText);',
         'connect(compact_keyboard_, &CompactKeyboard::sig_text, view_, &DesktopView::onVirtualKeyboardText);')

    # Keep the exact LMB/Klav and their behavior; trim only strip height.
    once(bar_h, '    int barThickness() const { return 44; }',
         '    int barThickness() const { return 33; }')
    once(bar_cc, 'constexpr int kKeyHeight = 32;',
         'constexpr int kKeyHeight = 28;')
    once(bar_cc, '    panel_layout_->setContentsMargins(2, 2, 2, 2);',
         '    panel_layout_->setContentsMargins(2, 3, 2, 0);')
    once(bar_cc, '    controls_layout_->setContentsMargins(3, 2, 3, 2);',
         '    controls_layout_->setContentsMargins(3, 3, 3, 0);')

    once(root / 'CMakePresets.json',
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.8",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702008"',
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.9",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702009"')
    cmake = root / 'source/client/CMakeLists.txt'
    once(cmake, 'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.8" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.9" CACHE STRING')
    once(cmake, 'set(ASPIA_MOBILE_VERSION_CODE "20702008" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_CODE "20702009" CACHE STRING')
    print('PASS: Mobile9 Samsung visual geometry and nested Aspia scancode typing')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: mobile9-fixes.py <prepared-mobile8-tree>')
    apply(Path(sys.argv[1]).resolve())