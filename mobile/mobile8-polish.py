#!/usr/bin/env python3
"""Mobile 8: Samsung-sized in-app keyboard and restrained KeyBar polish.

Runs only after the pinned Mobile 7 overlay. Preserves remote input events,
clipboard, gestures, connection, Host/Router compatibility and local books.
"""
from __future__ import annotations

from pathlib import Path
import sys


def once(path: Path, old: str, new: str) -> None:
    data = path.read_text(encoding="utf-8")
    count = data.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: required anchor occurs {count} times: {old[:100]!r}")
    path.write_text(data.replace(old, new, 1), encoding="utf-8")


KEYBOARD_H = r'''// Aspia+ Mobile 8: Samsung-like compact, app-local remote keyboard.
#ifndef CLIENT_ANDROID_COMPACT_KEYBOARD_H
#define CLIENT_ANDROID_COMPACT_KEYBOARD_H

#include <QList>
#include <QString>
#include <QWidget>

class QPushButton;
class QResizeEvent;

class CompactKeyboard final : public QWidget
{
    Q_OBJECT

public:
    explicit CompactKeyboard(QWidget* parent = nullptr);
    ~CompactKeyboard() final = default;
    void setLandscapeMode(bool enabled);

signals:
    void sig_text(const QString& text);
    void sig_key(quint32 usb_keycode);

protected:
    void resizeEvent(QResizeEvent* event) final;

private:
    QPushButton* newKey(const QString& title);
    void updateLabels();
    void writeLetter(int row, int index);
    void updatePanelWidth();
    void configureAlternate(QPushButton* key, const QString& lower, const QString& upper);

    QWidget* keys_panel_ = nullptr;
    QList<QList<QPushButton*>> letters_;
    QPushButton* shift_key_ = nullptr;
    QPushButton* space_key_ = nullptr;
    QPushButton* symbols_key_ = nullptr;
    bool landscape_ = false;
    bool ru_ = true;
    bool shifted_ = false;
    bool symbols_ = false;
};

#endif // CLIENT_ANDROID_COMPACT_KEYBOARD_H
'''

KEYBOARD_CC = r'''// Aspia+ Mobile 8: reduced Samsung layout, no system IME toolbar.
// Uses the same legacy-compatible TextEvent and USB KeyEvent paths as Mobile 7.
#include "client/android/compact_keyboard.h"

#include <QFont>
#include <QHBoxLayout>
#include <QPalette>
#include <QPushButton>
#include <QResizeEvent>
#include <QSizePolicy>
#include <QStringList>
#include <QTimer>
#include <QVariant>
#include <QVBoxLayout>

#include "common/android/controls.h"

namespace {
constexpr quint32 kUsbEnter = 0x070028;
constexpr quint32 kUsbBackspace = 0x07002a;

const QStringList kRussian = {
    QStringLiteral("йцукенгшщзх"),
    QStringLiteral("фывапролджэ"),
    QStringLiteral("ячсмитьбю")
};
const QStringList kEnglish = {
    QStringLiteral("qwertyuiop"),
    QStringLiteral("asdfghjkl"),
    QStringLiteral("zxcvbnm")
};
const QStringList kSymbols = {
    QStringLiteral("!@#$%^&*()"),
    QStringLiteral("-_=+[]{};:"),
    QStringLiteral("'\"/\\<>?|~")
};
}

CompactKeyboard::CompactKeyboard(QWidget* parent) : QWidget(parent)
{
    setAutoFillBackground(true);
    setFocusPolicy(Qt::NoFocus);
    QPalette pal = palette();
    pal.setColor(QPalette::Window, Controls::surfaceColor());
    setPalette(pal);

    // The entire full-width widget consumes touches, while only the centered
    // 75% is used for the actual keyboard in landscape.
    auto* shell = new QVBoxLayout(this);
    shell->setContentsMargins(0, 0, 0, 0);
    shell->setSpacing(0);
    keys_panel_ = new QWidget(this);
    keys_panel_->setFocusPolicy(Qt::NoFocus);
    keys_panel_->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Expanding);
    shell->addWidget(keys_panel_, 1, Qt::AlignHCenter);

    auto* column = new QVBoxLayout(keys_panel_);
    column->setContentsMargins(4, 4, 4, 5);
    column->setSpacing(5);

    auto makeRow = [column]() -> QHBoxLayout*
    {
        auto* row = new QHBoxLayout();
        row->setContentsMargins(0, 0, 0, 0);
        row->setSpacing(5);
        column->addLayout(row, 1);
        return row;
    };

    // Only 1..0 here: the Russian letters Ё and Ъ use long-presses.
    QHBoxLayout* numbers = makeRow();
    for (int i = 1; i <= 10; ++i)
    {
        const QString digit = QString::number(i % 10);
        QPushButton* key = newKey(digit);
        numbers->addWidget(key, 1);
        connect(key, &QPushButton::clicked, this,
                [this, digit]() { emit sig_text(digit); });
    }

    for (int r = 0; r < 3; ++r)
    {
        QHBoxLayout* row = makeRow();
        if (r == 2)
        {
            shift_key_ = newKey(QStringLiteral("⇧"));
            row->addWidget(shift_key_, 1);
            connect(shift_key_, &QPushButton::clicked, this, [this]()
            {
                shifted_ = !shifted_;
                updateLabels();
            });
        }

        QList<QPushButton*> keys;
        const int key_count = (r == 2) ? 9 : 11;
        for (int c = 0; c < key_count; ++c)
        {
            QPushButton* key = newKey(QString());
            row->addWidget(key, 1);
            keys.append(key);
            connect(key, &QPushButton::clicked, this,
                    [this, r, c]() { writeLetter(r, c); });
        }
        letters_.append(keys);

        if (r == 2)
        {
            QPushButton* backspace = newKey(QStringLiteral("⌫"));
            row->addWidget(backspace, 1);
            connect(backspace, &QPushButton::clicked, this,
                    [this]() { emit sig_key(kUsbBackspace); });
        }
    }

    // Samsung uses long-press E -> Ё and soft sign -> hard sign.
    configureAlternate(letters_[0][4], QStringLiteral("ё"), QStringLiteral("Ё"));
    configureAlternate(letters_[2][6], QStringLiteral("ъ"), QStringLiteral("Ъ"));

    QHBoxLayout* footer = makeRow();
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
            [this]() { emit sig_text(QStringLiteral(",")); });

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
            [this]() { emit sig_text(QStringLiteral(" ")); });

    QPushButton* next_language = newKey(QStringLiteral(">"));
    footer->addWidget(next_language, 1);
    connect(next_language, &QPushButton::clicked, this, changeLanguage);

    QPushButton* dot = newKey(QStringLiteral("."));
    footer->addWidget(dot, 1);
    connect(dot, &QPushButton::clicked, this,
            [this]() { emit sig_text(QStringLiteral(".")); });

    // Text instead of a missing Unicode arrow glyph on some Samsung fonts.
    QPushButton* enter = newKey(QStringLiteral("Enter"));
    footer->addWidget(enter, 2);
    connect(enter, &QPushButton::clicked, this,
            [this]() { emit sig_key(kUsbEnter); });

    updatePanelWidth();
    updateLabels();
}

void CompactKeyboard::setLandscapeMode(bool enabled)
{
    if (landscape_ == enabled)
        return;
    landscape_ = enabled;
    updatePanelWidth();
}

void CompactKeyboard::resizeEvent(QResizeEvent* event)
{
    QWidget::resizeEvent(event);
    updatePanelWidth();
}

void CompactKeyboard::updatePanelWidth()
{
    // Match the reduced Samsung landscape reference, not the phone's full width.
    const int target = landscape_ ? qMax(1, width() * 75 / 100) : qMax(1, width());
    if (keys_panel_->width() != target || keys_panel_->minimumWidth() != target)
        keys_panel_->setFixedWidth(target);
}

QPushButton* CompactKeyboard::newKey(const QString& title)
{
    QPushButton* key = new QPushButton(title, keys_panel_);
    key->setFocusPolicy(Qt::NoFocus);
    key->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    key->setMinimumSize(0, 0);
    QFont font = key->font();
    font.setPixelSize(17);
    key->setFont(font);
    const bool dark = palette().color(QPalette::Window).lightness() < 128;
    key->setStyleSheet(dark ? QStringLiteral(
        "QPushButton{background:#303033;color:#f5f5f5;border:0;"
        "border-radius:6px;padding:0px;}"
        "QPushButton:pressed{background:#60646b;color:white;}")
        : QStringLiteral(
        "QPushButton{background:#d4d4d6;color:#171717;border:0;"
        "border-radius:6px;padding:0px;}"
        "QPushButton:pressed{background:#a8acb2;color:black;}"));
    return key;
}

void CompactKeyboard::updateLabels()
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
}

void CompactKeyboard::writeLetter(int row, int index)
{
    if (row < 0 || row >= letters_.size() || index < 0 ||
        index >= letters_[row].size())
        return;

    QPushButton* key = letters_[row][index];
    // Do not emit Е/Ь after a 500 ms Ё/Ъ long-press on the same key.
    if (key->property("alternateConsumed").toBool())
    {
        key->setProperty("alternateConsumed", false);
        return;
    }

    const QStringList& rows = symbols_ ? kSymbols : (ru_ ? kRussian : kEnglish);
    if (index >= rows[row].size())
        return;
    QString letter = rows[row].mid(index, 1);
    if (shifted_ && !symbols_)
        letter = letter.toUpper();
    emit sig_text(letter);
    if (shifted_)
    {
        shifted_ = false;
        updateLabels();
    }
}

void CompactKeyboard::configureAlternate(
    QPushButton* key, const QString& lower, const QString& upper)
{
    auto* timer = new QTimer(key);
    timer->setSingleShot(true);
    timer->setInterval(500);
    connect(key, &QPushButton::pressed, this, [this, key, timer]()
    {
        key->setProperty("alternateConsumed", false);
        if (ru_ && !symbols_)
            timer->start();
    });
    connect(key, &QPushButton::released, this, [timer]() { timer->stop(); });
    connect(timer, &QTimer::timeout, this, [this, key, lower, upper]()
    {
        key->setProperty("alternateConsumed", true);
        emit sig_text(shifted_ ? upper : lower);
        if (shifted_)
        {
            shifted_ = false;
            updateLabels();
        }
    });
}
'''


def apply(root: Path) -> None:
    android = root / "source/client/android"
    kb_h = android / "compact_keyboard.h"
    kb_cc = android / "compact_keyboard.cc"
    header = kb_h.read_text(encoding="utf-8")
    source = kb_cc.read_text(encoding="utf-8")
    if ("class CompactKeyboard final : public QWidget" not in header or
        "QStringLiteral(\"йцукенгшщзхъ\")" not in source or
        "landscape_keys_" not in source):
        raise RuntimeError("Expected Mobile 7 keyboard layout is missing")
    kb_h.write_text(KEYBOARD_H, encoding="utf-8")
    kb_cc.write_text(KEYBOARD_CC, encoding="utf-8")

    keybar = android / "key_bar.cc"
    # Preserve LMB and 'Клав.' exactly as they are, including button behavior.
    once(keybar,
         '    addAction(controls_layout_, QStringLiteral("Впис."), &KeyBar::sig_fitRequested);\n',
         "")
    # The controls use the device's foreground color: white on dark themes,
    # dark on light. Active/held buttons keep their existing filled state.
    once(keybar,
         '    panel_layout_->addWidget(more_button_);\n    setFixedHeight(barThickness());',
         '    panel_layout_->addWidget(more_button_);\n'
         '    for (Button* button : findChildren<Button*>())\n'
         '        button->setAccentColor(palette().color(QPalette::WindowText));\n'
         '    setFixedHeight(barThickness());')

    window = android / "desktop_window.cc"
    # Keep the established pan/zoom geometry. Portrait height stays unchanged;
    # landscape typing rows gain modest vertical room, like reduced Samsung.
    once(window,
         '    const int keyboard_height = compact_keyboard_visible_ ?\n'
         '        qMin(height() * 38 / 100, 226) : 0;',
         '    const bool landscape = width() > height();\n'
         '    const int keyboard_height = compact_keyboard_visible_ ?\n'
         '        (landscape ? qMin(height() * 44 / 100, 210)\n'
         '                   : qMin(height() * 38 / 100, 226)) : 0;')

    once(root / "CMakePresets.json",
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.7",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702007"',
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.8",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702008"')
    cmake = root / "source/client/CMakeLists.txt"
    once(cmake,
         'set(ASPIA_MOBILE_VERSION_CODE "20702007" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_CODE "20702008" CACHE STRING')
    once(cmake,
         'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.7" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.8" CACHE STRING')
    print("PASS: Mobile8 reduced Samsung keys; fixed LMB/Klav, no Fit; themed KeyBar")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: mobile8-polish.py <prepared-mobile7-tree>")
    apply(Path(sys.argv[1]).resolve())
