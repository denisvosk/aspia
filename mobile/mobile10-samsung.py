#!/usr/bin/env python3
"""Mobile10: match Samsung reduced RU/EN keyboard from 2026-11-23 captures.

Applied after Mobile10 KeyBar patch. Only app-local Qt keyboard presentation,
spacebar swipe and shift state are changed: nested Aspia physical USB scancodes,
Unicode clipboard, Host/Router/Relay protocols, and biometric policy are preserved.
"""
from __future__ import annotations

from pathlib import Path
import sys


def once(path: Path, old: str, new: str) -> None:
    data = path.read_text(encoding='utf-8')
    count = data.count(old)
    if count != 1:
        raise RuntimeError(f'{path}: required source anchor occurs {count} times: {old[:140]!r}')
    path.write_text(data.replace(old, new, 1), encoding='utf-8')


def apply(root: Path) -> None:
    android = root / 'source/client/android'
    h = android / 'compact_keyboard.h'
    cc = android / 'compact_keyboard.cc'
    bar_h = android / 'key_bar.h'
    bar = android / 'key_bar.cc'

    # Shorter fixed rail, while leaving LMB and other controls in place.
    once(bar_h, '    int barThickness() const { return 33; }',
         '    int barThickness() const { return 30; }')
    once(bar, 'constexpr int kKeyHeight = 28;',
         'constexpr int kKeyHeight = 26;')

    # Source headers: event filter for swipe-on-space, status-aware Shift,
    # and layout pointers for non-shifting alphabet rows.
    once(h, '#include <QList>\n', '#include <QList>\n#include <QPointF>\n')
    once(h, 'class QPushButton;\n',
         'class QPushButton;\nclass QLabel;\nclass QHBoxLayout;\n')
    once(h,
         'protected:\n    void resizeEvent(QResizeEvent* event) final;',
         'protected:\n    void resizeEvent(QResizeEvent* event) final;\n'
         '    bool eventFilter(QObject* watched, QEvent* event) final;')
    once(h,
         '    void configureAlternate(QPushButton* key, const QString& lower, const QString& upper);',
         '    void configureAlternate(QPushButton* key, const QString& lower, const QString& upper);\n'
         '    void changeLanguage();\n'
         '    void markSentenceStart();\n'
         '    void setUtilityStyle(QPushButton* key);')
    once(h, '    QList<QList<QPushButton*>> letters_;',
         '    QList<QList<QPushButton*>> letters_;\n'
         '    QList<QHBoxLayout*> letter_rows_;')
    once(h, '    QPushButton* shift_key_ = nullptr;',
         '    QPushButton* shift_key_ = nullptr;\n'
         '    QPushButton* backspace_key_ = nullptr;')
    once(h, '    QPushButton* space_key_ = nullptr;',
         '    QPushButton* space_key_ = nullptr;\n'
         '    QLabel* language_label_ = nullptr;\n'
         '    QPointF space_press_;\n'
         '    bool space_tracking_ = false;')
    once(h, '    bool shifted_ = false;',
         '    enum class ShiftState { Off, Once, CapsLock };\n'
         '    ShiftState shift_state_ = ShiftState::Once;')

    # Fonts, Samsung artwork and mouse-synthesized Android space swipe.
    once(cc, '#include <QFont>\n',
         '#include <QEvent>\n#include <QFont>\n#include <QLabel>\n'
         '#include <QMouseEvent>\n')
    once(cc, '#include <QPixmap>\n',
         '#include <QPixmap>\n#include <QPen>\n')
    once(cc, 'constexpr quint32 kUsbBackspace = 0x07002a;',
         'constexpr quint32 kUsbBackspace = 0x07002a;')

    # Paint Shift as an actual stable glyph, independent of text and Qt fonts:
    # white outline = off, blue outline = next letter, filled white = CapsLock.
    once(cc,
         'QIcon backspaceIcon(bool dark)\n{',
         r'''QIcon shiftIcon(bool dark, bool oneShot, bool capsLock)
{
    QPixmap pixmap(64, 64);
    pixmap.fill(Qt::transparent);
    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing);
    const QColor ink = oneShot ? QColor("#4a9dff") :
                      (dark ? QColor("#fafafa") : QColor("#171717"));
    painter.setPen(QPen(ink, 3.8, Qt::SolidLine,
                       Qt::RoundCap, Qt::RoundJoin));
    if (capsLock)
        painter.setBrush(ink);
    else
        painter.setBrush(Qt::NoBrush);
    QPainterPath arrow;
    arrow.moveTo(32, 7);
    arrow.lineTo(7, 32);
    arrow.lineTo(18, 32);
    arrow.lineTo(18, 54);
    arrow.lineTo(46, 54);
    arrow.lineTo(46, 32);
    arrow.lineTo(57, 32);
    arrow.closeSubpath();
    painter.drawPath(arrow);
    return QIcon(pixmap);
}

QIcon enterIcon(bool dark)
{
    QPixmap pixmap(64, 64);
    pixmap.fill(Qt::transparent);
    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing);
    painter.setPen(QPen(dark ? QColor("#fafafa") : QColor("#171717"),
                        4.0, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
    QPainterPath path;
    path.moveTo(51, 10);
    path.lineTo(51, 35);
    path.quadTo(51, 43, 43, 43);
    path.lineTo(12, 43);
    painter.drawPath(path);
    painter.drawLine(24, 30, 11, 43);
    painter.drawLine(11, 43, 24, 56);
    return QIcon(pixmap);
}

QIcon backspaceIcon(bool dark)
{''')

    # Samsung landscape reference: true black gutters, dark corner keys,
    # 11 same-size Russian letter keys, smaller number-row height.
    once(cc,
         '    column->setContentsMargins(6, 3, 6, 5);',
         '    // Bottom inset protects space swipes from the auxiliary KeyBar.\n'
         '    column->setContentsMargins(6, 3, 6, 12);')
    once(cc, '        digit_font.setPixelSize(15);',
         '        digit_font.setPixelSize(19);')
    once(cc, '        QHBoxLayout* row = makeRow();\n        if (r == 2)',
         '        QHBoxLayout* row = makeRow();\n'
         '        letter_rows_.append(row);\n'
         '        if (r == 2)')

    once(cc,
         '''            shift_key_ = newKey(QStringLiteral("⇧"));
            row->addWidget(shift_key_, 1);
            connect(shift_key_, &QPushButton::clicked, this, [this]()
            {
                shifted_ = !shifted_;
                updateLabels();
            });''',
         '''            shift_key_ = newKey(QString());
            setUtilityStyle(shift_key_);
            shift_key_->setIconSize(QSize(31, 30));
            row->addWidget(shift_key_, 1);
            connect(shift_key_, &QPushButton::clicked, this, [this]()
            {
                switch (shift_state_)
                {
                    case ShiftState::Off: shift_state_ = ShiftState::Once; break;
                    case ShiftState::Once: shift_state_ = ShiftState::CapsLock; break;
                    case ShiftState::CapsLock: shift_state_ = ShiftState::Off; break;
                }
                updateLabels();
            });''')
    once(cc,
         '            backspace->setIcon(backspaceIcon(dark_theme_));',
         '            setUtilityStyle(backspace);\n'
         '            backspace_key_ = backspace;\n'
         '            backspace->setIcon(backspaceIcon(dark_theme_));')

    # Samsung has ONE big space button, with ‹ / language / › drawn inside.
    # Swiping in either direction switches languages; arrows are not buttons.
    old_footer = '''    QHBoxLayout* footer = makeRow();
    symbols_key_ = newKey(QStringLiteral("!#1"));
    footer->addWidget(symbols_key_, 2);
    connect(symbols_key_, &QPushButton::clicked, this, [this]()
    {
        symbols_ = !symbols_;
        shifted_ = false;
        updateLabels();
    });

    QPushButton* comma = newKey(QStringLiteral(","));
    footer->addWidget(comma, 1);
    connect(comma, &QPushButton::clicked, this,
            [this]() { emit sig_text(QStringLiteral(","), ru_); });

    auto changeLanguage = [this]()
    {
        ru_ = !ru_;
        symbols_ = false;
        shifted_ = false;
        updateLabels();
    };
    QPushButton* previous_language = newKey(QStringLiteral("<"));
    footer->addWidget(previous_language, 1);
    connect(previous_language, &QPushButton::clicked, this, changeLanguage);

    space_key_ = newKey(QStringLiteral("Русский"));
    footer->addWidget(space_key_, 5);
    connect(space_key_, &QPushButton::clicked, this,
            [this]() { emit sig_text(QStringLiteral(" "), ru_); });

    QPushButton* next_language = newKey(QStringLiteral(">"));
    footer->addWidget(next_language, 1);
    connect(next_language, &QPushButton::clicked, this, changeLanguage);

    QPushButton* dot = newKey(QStringLiteral("."));
    footer->addWidget(dot, 1);
    connect(dot, &QPushButton::clicked, this,
            [this]() { emit sig_text(QStringLiteral("."), ru_); });

    // Text instead of a missing Unicode arrow glyph on some Samsung fonts.
    QPushButton* enter = newKey(QStringLiteral("Enter"));
    footer->addWidget(enter, 2);
    connect(enter, &QPushButton::clicked, this,
            [this]() { emit sig_key(kUsbEnter); });'''
    new_footer = '''    QHBoxLayout* footer = makeRow();
    symbols_key_ = newKey(QStringLiteral("!#1"));
    setUtilityStyle(symbols_key_);
    footer->addWidget(symbols_key_, 3);
    connect(symbols_key_, &QPushButton::clicked, this, [this]()
    {
        symbols_ = !symbols_;
        shift_state_ = ShiftState::Off;
        updateLabels();
    });

    QPushButton* comma = newKey(QStringLiteral(","));
    footer->addWidget(comma, 2);
    connect(comma, &QPushButton::clicked, this,
            [this]() { emit sig_text(QStringLiteral(","), ru_); });

    space_key_ = newKey(QString());
    footer->addWidget(space_key_, 11);
    space_key_->installEventFilter(this);
    auto* space_contents = new QHBoxLayout(space_key_);
    space_contents->setContentsMargins(7, 0, 7, 0);
    space_contents->setSpacing(3);
    const auto addCaption = [this, space_contents](const QString& text)
    {
        auto* label = new QLabel(text, space_key_);
        label->setAlignment(Qt::AlignCenter);
        label->setAttribute(Qt::WA_TransparentForMouseEvents, true);
        QFont face = label->font();
        face.setPixelSize(14);
        label->setFont(face);
        label->setStyleSheet(dark_theme_ ? QStringLiteral("color:#fafafa;") :
                                         QStringLiteral("color:#171717;"));
        space_contents->addWidget(label);
        return label;
    };
    addCaption(QStringLiteral("<"));
    space_contents->addStretch(1);
    language_label_ = addCaption(QStringLiteral("Русский"));
    space_contents->addStretch(1);
    addCaption(QStringLiteral(">"));
    connect(space_key_, &QPushButton::clicked, this,
            [this]() { emit sig_text(QStringLiteral(" "), ru_); });

    QPushButton* dot = newKey(QStringLiteral("."));
    footer->addWidget(dot, 2);
    connect(dot, &QPushButton::clicked, this, [this]()
    {
        emit sig_text(QStringLiteral("."), ru_);
        markSentenceStart();
    });

    QPushButton* enter = newKey(QString());
    setUtilityStyle(enter);
    enter->setIcon(enterIcon(dark_theme_));
    enter->setIconSize(QSize(29, 29));
    footer->addWidget(enter, 3);
    connect(enter, &QPushButton::clicked, this, [this]()
    {
        emit sig_key(kUsbEnter);
        markSentenceStart();
    });'''
    once(cc, old_footer, new_footer)

    # Eliminate text-dependent geometry. Qt's default QPushButton sizeHint
    # changes with '⇧●' and translates the entire adjacent row.
    once(cc, '    key->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);',
         '    key->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Expanding);')
    once(cc, '    font.setPixelSize(17);', '    font.setPixelSize(18);')

    # Main keyboard dynamic states and alignment rules. English middle row is
    # indented; English bottom letter row has wider fixed-size Shift/Backspace.
    old_labels = '''void CompactKeyboard::updateLabels()
{
    const QStringList& rows = symbols_ ? kSymbols : (ru_ ? kRussian : kEnglish);
    for (int r = 0; r < letters_.size(); ++r)
    {
        for (int c = 0; c < letters_[r].size(); ++c)
        {
            QPushButton* key = letters_[r][c];
            const bool available = c < rows[r].size();
            key->setVisible(available);
            if (available)
            {
                const QString letter = rows[r].mid(c, 1);
                key->setText(shifted_ && !symbols_ ? letter.toUpper() : letter);
            }
        }
    }
    shift_key_->setText(shifted_ ? QStringLiteral("⇧●") : QStringLiteral("⇧"));
    space_key_->setText(ru_ ? QStringLiteral("Русский") : QStringLiteral("English"));
    symbols_key_->setText(symbols_ ? QStringLiteral("АБВ") : QStringLiteral("!#1"));
}'''
    new_labels = '''void CompactKeyboard::updateLabels()
{
    const QStringList& rows = symbols_ ? kSymbols : (ru_ ? kRussian : kEnglish);
    const bool upper = shift_state_ != ShiftState::Off && !symbols_;
    for (int r = 0; r < letters_.size(); ++r)
    {
        for (int c = 0; c < letters_[r].size(); ++c)
        {
            QPushButton* key = letters_[r][c];
            const bool available = c < rows[r].size();
            key->setVisible(available);
            if (available)
            {
                const QString letter = rows[r].mid(c, 1);
                key->setText(upper ? letter.toUpper() : letter);
            }
        }
    }
    const bool english = !ru_ && !symbols_;
    const int home_indent = english ? qMax(0, keys_panel_->width() / 20) : 0;
    letter_rows_[1]->setContentsMargins(home_indent, 0, home_indent, 0);
    QHBoxLayout* bottom = letter_rows_[2];
    bottom->setStretch(0, english ? 4 : 1); // Shift
    for (int c = 0; c < 9; ++c)
        bottom->setStretch(c + 1, english ? 3 : 1);
    bottom->setStretch(10, english ? 4 : 1); // Backspace

    shift_key_->setIcon(shiftIcon(dark_theme_,
        shift_state_ == ShiftState::Once,
        shift_state_ == ShiftState::CapsLock));
    language_label_->setText(ru_ ? QStringLiteral("Русский") :
                                  QStringLiteral("English (US)"));
    symbols_key_->setText(symbols_ ? QStringLiteral("АБВ") : QStringLiteral("!#1"));
}'''
    once(cc, old_labels, new_labels)

    # Do not make Shift expand or move adjacent keys. OneShot consumes one
    # letter; CapsLock persists until the user taps Shift again.
    once(cc,
         '''    if (shifted_ && !symbols_)
        letter = letter.toUpper();
    emit sig_text(letter, ru_);
    if (shifted_)
    {
        shifted_ = false;
        updateLabels();
    }''',
         '''    if (shift_state_ != ShiftState::Off && !symbols_)
        letter = letter.toUpper();
    emit sig_text(letter, ru_);
    if (shift_state_ == ShiftState::Once)
    {
        shift_state_ = ShiftState::Off;
        updateLabels();
    }''')
    once(cc,
         '''        emit sig_text(shifted_ ? upper : lower, ru_);
        if (shifted_)
        {
            shifted_ = false;
            updateLabels();
        }''',
         '''        emit sig_text(shift_state_ != ShiftState::Off ? upper : lower, ru_);
        if (shift_state_ == ShiftState::Once)
        {
            shift_state_ = ShiftState::Off;
            updateLabels();
        }''')

    # update the indent after rotation / resize, too.
    once(cc,
         '''    if (keys_panel_->width() != target || keys_panel_->minimumWidth() != target)
        keys_panel_->setFixedWidth(target);''',
         '''    if (keys_panel_->width() != target || keys_panel_->minimumWidth() != target)
    {
        keys_panel_->setFixedWidth(target);
        if (!letter_rows_.isEmpty() && language_label_)
            updateLabels();
    }''')

    # Use a small pointer-distance threshold, not a separate left/right button.
    # Leave vertical swipes to the parent; only horizontal moves switch layout.
    once(cc,
         '''void CompactKeyboard::setLandscapeMode(bool enabled)
{''',
         '''bool CompactKeyboard::eventFilter(QObject* watched, QEvent* event)
{
    if (watched == space_key_)
    {
        if (event->type() == QEvent::MouseButtonPress)
        {
            const auto* mouse = static_cast<QMouseEvent*>(event);
            if (mouse->button() == Qt::LeftButton)
            {
                space_press_ = mouse->position();
                space_tracking_ = true;
            }
        }
        else if (event->type() == QEvent::MouseButtonRelease && space_tracking_)
        {
            const auto* mouse = static_cast<QMouseEvent*>(event);
            space_tracking_ = false;
            const QPointF movement = mouse->position() - space_press_;
            const qreal threshold = qMax(24, space_key_->width() / 15);
            if (qAbs(movement.x()) > threshold &&
                qAbs(movement.x()) > qAbs(movement.y()) * 1.4)
            {
                space_key_->setDown(false);
                changeLanguage();
                event->accept();
                return true; // suppress the space-click after horizontal swipe
            }
        }
    }
    return QWidget::eventFilter(watched, event);
}

void CompactKeyboard::changeLanguage()
{
    ru_ = !ru_;
    symbols_ = false;
    shift_state_ = ShiftState::Once;
    updateLabels();
}

void CompactKeyboard::markSentenceStart()
{
    if (shift_state_ != ShiftState::CapsLock)
    {
        shift_state_ = ShiftState::Once;
        updateLabels();
    }
}

void CompactKeyboard::setUtilityStyle(QPushButton* key)
{
    const QString colors = dark_theme_ ?
        QStringLiteral("QPushButton{background:#171717;color:#fafafa;"
                       "border:0;border-radius:7px;padding:0px;}"
                       "QPushButton:pressed{background:#444444;}") :
        QStringLiteral("QPushButton{background:#bcbcc0;color:#171717;"
                       "border:0;border-radius:7px;padding:0px;}"
                       "QPushButton:pressed{background:#94969a;}");
    key->setStyleSheet(colors);
}

void CompactKeyboard::setLandscapeMode(bool enabled)
{''')
    print('PASS: Mobile10 Samsung key proportions, bottom 5-key row, swipe '
          'language, three-state illustrated Shift and centered 30px KeyBar')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: mobile10-samsung.py <prepared-mobile10-keybar-tree>')
    apply(Path(sys.argv[1]).resolve())