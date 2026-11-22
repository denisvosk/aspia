#!/usr/bin/env python3
"""Aspia+ Mobile 7: compact in-app RU/EN keyboard, deterministic IME geometry, clipboard.

Applies ONLY after hash-locked Mobile 6 source overlays. No old Host/Router/Relay,
keys, AAB, protocols, or signing material is changed. Fails on unknown anchors.
"""
from __future__ import annotations
from pathlib import Path
import sys


def once(path: Path, before: str, after: str) -> None:
    s = path.read_text(encoding='utf-8')
    n = s.count(before)
    if n != 1:
        raise RuntimeError(f'{path}: expected one anchor, got {n}: {before[:110]!r}')
    path.write_text(s.replace(before, after, 1), encoding='utf-8')


def replace_method(path: Path, method: str, replacement: str, required: str) -> None:
    s = path.read_text(encoding='utf-8')
    anchor = method + '\n{\n'
    if s.count(anchor) != 1:
        raise RuntimeError(f'{path}: method {method} not uniquely found')
    first = s.index(anchor)
    last = s.find('\n}\n', first)
    if last == -1 or required not in s[first:last]:
        raise RuntimeError(f'{path}: wrong source of {method}')
    path.write_text(s[:first] + replacement.strip('\n') + s[last+3:], encoding='utf-8')


KEYBOARD_H = r'''// Aspia+ Mobile 7. In-app compact remote keyboard; no Android-wide IME changes.
#ifndef CLIENT_ANDROID_COMPACT_KEYBOARD_H
#define CLIENT_ANDROID_COMPACT_KEYBOARD_H

#include <QList>
#include <QString>
#include <QWidget>

class QPushButton;

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

private:
    QPushButton* newKey(const QString& title);
    void updateLabels();
    void writeLetter(int row, int index);

    QList<QList<QPushButton*>> letters_;
    QPushButton* shift_key_ = nullptr;
    QPushButton* yo_key_ = nullptr;
    QList<QPushButton*> landscape_keys_;
    QPushButton* language_key_ = nullptr;
    QPushButton* symbols_key_ = nullptr;
    bool ru_ = true;
    bool shifted_ = false;
    bool symbols_ = false;
};

#endif // CLIENT_ANDROID_COMPACT_KEYBOARD_H
'''

KEYBOARD_CC = r'''// Aspia+ Mobile 7. All keys generate local in-process signals to the existing
// desktop TextEvent/KeyEvent implementation; no text is stored or logged.
#include "client/android/compact_keyboard.h"

#include <QFont>
#include <QHBoxLayout>
#include <QPalette>
#include <QPushButton>
#include <QSizePolicy>
#include <QStringList>
#include <QVBoxLayout>

#include <utility>

#include "common/android/controls.h"

namespace {
constexpr quint32 kUsbEnter = 0x070028;
constexpr quint32 kUsbBackspace = 0x07002a;

const QStringList kRussian = {
    QStringLiteral("йцукенгшщзхъ"),
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

    auto* column = new QVBoxLayout(this);
    column->setContentsMargins(3, 2, 3, 4);
    column->setSpacing(2);

    auto makeRow = [column]() -> QHBoxLayout*
    {
        auto* row = new QHBoxLayout();
        row->setContentsMargins(0, 0, 0, 0);
        row->setSpacing(2);
        column->addLayout(row, 1);
        return row;
    };

    // A number row is always available, even while typing a password.
    QHBoxLayout* numbers = makeRow();
    yo_key_ = newKey(QStringLiteral("ё"));
    numbers->addWidget(yo_key_, 1);
    connect(yo_key_, &QPushButton::clicked, this, [this]()
    {
        emit sig_text(ru_ ? QString(shifted_ ? QStringLiteral("Ё") : QStringLiteral("ё")) :
                            QStringLiteral("`"));
        if (shifted_)
        {
            shifted_ = false;
            updateLabels();
        }
    });
    for (int i = 1; i <= 10; ++i)
    {
        QString digit = QString::number(i % 10);
        QPushButton* key = newKey(digit);
        numbers->addWidget(key, 1);
        connect(key, &QPushButton::clicked, this, [this, digit]() { emit sig_text(digit); });
    }

    for (int r = 0; r < 3; ++r)
    {
        QHBoxLayout* row = makeRow();
        if (r == 2)
        {
            shift_key_ = newKey(QStringLiteral("⇧"));
            row->addWidget(shift_key_, 2);
            connect(shift_key_, &QPushButton::clicked, this, [this]()
            {
                shifted_ = !shifted_;
                updateLabels();
            });
        }

        QList<QPushButton*> keys;
        for (int c = 0; c < 12; ++c)
        {
            QPushButton* key = newKey(QString());
            row->addWidget(key, 1);
            keys.push_back(key);
            connect(key, &QPushButton::clicked, this, [this, r, c]() { writeLetter(r, c); });
        }
        letters_.append(keys);

        if (r == 2)
        {
            QPushButton* backspace = newKey(QStringLiteral("⌫"));
            row->addWidget(backspace, 2);
            connect(backspace, &QPushButton::clicked, this,
                [this]() { emit sig_key(kUsbBackspace); });
        }
    }

    QHBoxLayout* footer = makeRow();
    symbols_key_ = newKey(QStringLiteral("?123"));
    footer->addWidget(symbols_key_, 2);
    connect(symbols_key_, &QPushButton::clicked, this, [this]()
    {
        symbols_ = !symbols_;
        shifted_ = false;
        updateLabels();
    });

    language_key_ = newKey(QStringLiteral("RU"));
    footer->addWidget(language_key_, 2);
    connect(language_key_, &QPushButton::clicked, this, [this]()
    {
        ru_ = !ru_;
        symbols_ = false;
        shifted_ = false;
        updateLabels();
    });

    for (const QString& sign : {QStringLiteral(","), QStringLiteral(".")})
    {
        QPushButton* key = newKey(sign);
        footer->addWidget(key, 1);
        connect(key, &QPushButton::clicked, this, [this, sign]() { emit sig_text(sign); });
    }

    QPushButton* space = newKey(QStringLiteral("Пробел"));
    footer->addWidget(space, 6);
    connect(space, &QPushButton::clicked, this,
        [this]() { emit sig_text(QStringLiteral(" ")); });

    QPushButton* enter = newKey(QStringLiteral("↵"));
    footer->addWidget(enter, 2);
    connect(enter, &QPushButton::clicked, this, [this]() { emit sig_key(kUsbEnter); });

    // Landscape gets computer navigation keys inside the keyboard itself;
    // the number row remains ordinary digits, not a bulky numpad.
    const QStringList extras = {
        QStringLiteral("Esc"), QStringLiteral("Tab"),
        QStringLiteral("←"), QStringLiteral("↑"),
        QStringLiteral("↓"), QStringLiteral("→")
    };
    const quint32 usages[] = { 0x070029, 0x07002b, 0x070050, 0x070052, 0x070051, 0x07004f };
    for (int i = 0; i < extras.size(); ++i)
    {
        QPushButton* key = newKey(extras.at(i));
        key->hide();
        footer->addWidget(key, 1);
        const quint32 usage = usages[i];
        connect(key, &QPushButton::clicked, this, [this, usage]() { emit sig_key(usage); });
        landscape_keys_.append(key);
    }

    updateLabels();
}

void CompactKeyboard::setLandscapeMode(bool enabled)
{
    for (QPushButton* key : std::as_const(landscape_keys_))
        key->setVisible(enabled);
}

QPushButton* CompactKeyboard::newKey(const QString& title)
{
    QPushButton* key = new QPushButton(title, this);
    key->setFocusPolicy(Qt::NoFocus);
    key->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    key->setMinimumSize(0, 0);
    QFont font = key->font();
    font.setPixelSize(15);
    key->setFont(font);
    key->setStyleSheet(QStringLiteral(
        "QPushButton{background:#34373b;color:#f4f5f6;border-radius:5px;padding:0px;}"
        "QPushButton:pressed{background:#68727d;color:white;}"));
    return key;
}

void CompactKeyboard::updateLabels()
{
    const QStringList& rows = symbols_ ? kSymbols : (ru_ ? kRussian : kEnglish);
    for (int r = 0; r < letters_.size(); ++r)
    {
        for (int c = 0; c < letters_[r].size(); ++c)
        {
            const bool available = c < rows[r].size();
            QPushButton* key = letters_[r][c];
            key->setVisible(available);
            if (available)
            {
                QString text = rows[r].mid(c, 1);
                key->setText((shifted_ && !symbols_) ? text.toUpper() : text);
            }
        }
    }
    shift_key_->setText(shifted_ ? QStringLiteral("⇧●") : QStringLiteral("⇧"));
    yo_key_->setText(ru_ ? (shifted_ ? QStringLiteral("Ё") : QStringLiteral("ё")) :
                          QStringLiteral("`"));
    language_key_->setText(ru_ ? QStringLiteral("RU") : QStringLiteral("EN"));
    symbols_key_->setText(symbols_ ? QStringLiteral("АБВ") : QStringLiteral("?123"));
}

void CompactKeyboard::writeLetter(int row, int index)
{
    const QStringList& rows = symbols_ ? kSymbols : (ru_ ? kRussian : kEnglish);
    if (row >= rows.size() || index >= rows[row].size())
        return;
    QString text = rows[row].mid(index, 1);
    if (shifted_ && !symbols_)
        text = text.toUpper();
    emit sig_text(text);
    if (shifted_)
    {
        shifted_ = false;
        updateLabels();
    }
}
'''


def apply(root: Path) -> None:
    android = root / 'source/client/android'
    (android / 'compact_keyboard.h').write_text(KEYBOARD_H, encoding='utf-8')
    (android / 'compact_keyboard.cc').write_text(KEYBOARD_CC, encoding='utf-8')
    once(android / 'sources.cmake',
         '    credential_selection_list.h\n',
         '    credential_selection_list.h\n    compact_keyboard.cc\n    compact_keyboard.h\n')

    key_h = android / 'key_bar.h'
    # A short cooldown after actual finger-scroll movement prevents accidental
    # hotkey taps; holdable LMB lives outside that scrolling area.
    once(key_h, '#include <QList>\n', '#include <QElapsedTimer>\n#include <QList>\n')
    once(key_h, '    QList<Button*> modifier_buttons_;',
         '    QList<Button*> modifier_buttons_;\n'
         '    QElapsedTimer scroll_cooldown_;')
    once(key_h, '    void addAction(QBoxLayout*',
         '    bool allowAction() const;\n    void addAction(QBoxLayout*')
    once(key_h, '    void sig_taskManagerRequested();',
         '    void sig_taskManagerRequested();\n    void sig_pastePhoneText();')
    key_cc = android / 'key_bar.cc'
    once(key_cc,
         '    connect(button, &QPushButton::clicked, this, signal);',
         '    connect(button, &QPushButton::clicked, this, [this, signal]()\n'
         '    {\n        if (allowAction()) (this->*signal)();\n    });')
    once(key_cc,
         '    connect(button, &QPushButton::clicked, this, [this, button, usb_keycode]()\n    {',
         '    connect(button, &QPushButton::clicked, this, [this, button, usb_keycode]()\n'
         '    {\n        if (!allowAction()) return;')
    once(key_cc,
         '    connect(button, &QPushButton::clicked, this, [this, usb_keycode]()\n    {',
         '    connect(button, &QPushButton::clicked, this, [this, usb_keycode]()\n'
         '    {\n        if (!allowAction()) return;')
    once(key_cc,
         '    QScroller::grabGesture(scroll_->viewport(), QScroller::TouchGesture);',
         '    QScroller::grabGesture(scroll_->viewport(), QScroller::TouchGesture);\n'
         '    connect(scroll_->horizontalScrollBar(), &QScrollBar::valueChanged,\n'
         '            this, [this]() { scroll_cooldown_.restart(); });')
    once(key_cc,
         'KeyBar::~KeyBar() = default;',
         'KeyBar::~KeyBar() = default;\n\n'
         'bool KeyBar::allowAction() const\n'
         '{\n'
         '    if (QScroller::scroller(scroll_->viewport())->state() != QScroller::Inactive)\n'
         '        return false;\n'
         '    return !scroll_cooldown_.isValid() || scroll_cooldown_.elapsed() > 220;\n'
         '}')
    once(key_cc,
         '    addAction(controls_layout_, QStringLiteral("Клав."), &KeyBar::sig_keyboardRequested);',
         '    addAction(controls_layout_, QStringLiteral("Клав."), &KeyBar::sig_keyboardRequested);\n'
         '    addAction(controls_layout_, QStringLiteral("Вставить"), &KeyBar::sig_pastePhoneText);')
    # Dangerous rotation must only be in the 3-dot menu.
    once(key_cc,
         '    addAction(controls_layout_, QStringLiteral("Повор."), &KeyBar::sig_rotateRequested);\n', '')

    view_h = android / 'desktop_view.h'
    once(view_h, '    void sendTaskManager();',
         '    void sendTaskManager();\n'
         '    void onVirtualText(const QString& text);\n'
         '    void setOcclusionHeight(int height);')
    once(view_h, '    int key_bar_height_ = 0;',
         '    int key_bar_height_ = 0;\n'
         '    int extra_occlusion_height_ = 0;\n'
         '    bool occlusion_follow_armed_ = true;')
    once(view_h, '    qreal viewportHeight() const;',
         '    qreal viewportHeight() const;\n    qreal visibleBottom() const;')

    view_cc = android / 'desktop_view.cc'
    # Remote text uses the original Aspia Unicode/USB event paths, not local IME.
    once(view_cc,
         'void DesktopView::onModifierToggled(quint32 usb_keycode, bool active)',
         r"""// The compact keyboard overlays the remote image instead of resizing it.
void DesktopView::setOcclusionHeight(int height)
{
    const int next = qMax(0, height);
    if (extra_occlusion_height_ == next)
        return;
    extra_occlusion_height_ = next;
    occlusion_follow_armed_ = false;
    if (edge_pan_timer_)
        edge_pan_timer_->stop();
    edge_pan_target_ = content_pos_;
    update();
}

// Unicode goes as TextEvent; Ctrl/Alt/Win chords become physical USB keystrokes.
void DesktopView::onVirtualText(const QString& text)
{
    if (text.isEmpty())
        return;

    if (text.size() == 1 && !sticky_modifiers_.isEmpty())
    {
        const quint32 shift = 0x0700e1;
        if (sticky_modifiers_.size() == 1 && sticky_modifiers_.front() == shift)
        {
            sticky_modifiers_.clear();
            emit sig_modifiersCleared();
            onVirtualText(text.toUpper());
            return;
        }

        const QChar character = text.at(0).toLower();
        quint32 usb = KeycodeConverter::qtKeycodeToUsbKeycode(character.toUpper().unicode());
        // When RU is selected, Ctrl+A / Ctrl+C still refer to physical keys.
        const QString ru = QStringLiteral("йцукенгшщзхъфывапролджэячсмитьбю");
        const QString en = QStringLiteral("qwertyuiop[]asdfghjkl;'zxcvbnm,.");
        const int at = ru.indexOf(character);
        if (at >= 0)
            usb = KeycodeConverter::qtKeycodeToUsbKeycode(en.at(at).toUpper().unicode());
        if (usb != KeycodeConverter::invalidUsbKeycode())
        {
            sendKeyWithModifiers(usb);
            return;
        }
    }
    if (!sticky_modifiers_.isEmpty())
    {
        sticky_modifiers_.clear();
        emit sig_modifiersCleared();
    }

    // Keep UTF-8 chunks below the legacy message limit, never cut a codepoint.
    const QByteArray utf = text.toUtf8();
    int start = 0;
    while (start < utf.size())
    {
        int end = qMin(start + 8192, int(utf.size()));
        while (end < utf.size() && (quint8(utf.at(end)) & 0xc0) == 0x80)
            --end;
        proto::input::TextEvent event;
        event.set_text(std::string(utf.constData() + start, size_t(end - start)));
        emit sig_textEvent(event);
        start = end;
    }
}

//--------------------------------------------------------------------------------------------------
void DesktopView::onModifierToggled(quint32 usb_keycode, bool active)""")

    once(view_cc,
         'qreal DesktopView::viewportHeight() const\n{',
         '''qreal DesktopView::visibleBottom() const
{
    return qMax(qreal(1), viewportHeight() -
        qMax(keyboard_inset_, extra_occlusion_height_));
}

//--------------------------------------------------------------------------------------------------
qreal DesktopView::viewportHeight() const
{''')
    # Arm edge following only when the operator actually moves the touch pointer.
    once(view_cc,
         'void DesktopView::moveCursorBy(const QPointF& widget_delta)\n{',
         'void DesktopView::moveCursorBy(const QPointF& widget_delta)\n{\n'
         '    if (!widget_delta.isNull()) occlusion_follow_armed_ = true;')

    # Native IME is disabled for the in-app keyboard, but if explicitly opened
    # later, its pixel inset is handled by the same viewport model.
    replace_method(view_cc, 'void DesktopView::clampContentPos()', '''void DesktopView::clampContentPos()
{
    const QSizeF content = fittedSize() * zoom_;
    if (content.width() <= width())
        content_pos_.setX((width() - content.width()) / 2.0);
    else
        content_pos_.setX(qBound(width() - content.width(), content_pos_.x(), qreal(0)));

    // Never jump immediately when the keyboard is shown. Only pointer motion
    // may request the new bounded region above the compact keyboard.
    if (extra_occlusion_height_ > 0 && !occlusion_follow_armed_)
        return;
    const qreal fitted = viewportHeight();
    const qreal available = visibleBottom();
    if (available < fitted - 1.0)
    {
        const qreal maximum = content.height() <= fitted ?
            qMax(qreal(0), (fitted - content.height()) / 2.0) : qreal(0);
        const qreal minimum = qMin(maximum,
            available - content.height() - qreal(24));
        content_pos_.setY(qBound(minimum, content_pos_.y(), maximum));
    }
    else if (content.height() <= fitted)
        content_pos_.setY((fitted - content.height()) / 2.0);
    else
        content_pos_.setY(qBound(fitted - content.height(), content_pos_.y(), qreal(0)));
}
''', 'const QSizeF content = fittedSize() * zoom_')

    replace_method(view_cc, 'void DesktopView::ensureCursorVisible()', '''void DesktopView::ensureCursorVisible()
{
    if (image_.isNull()) return;
    const qreal bottom = qMax(qreal(1), visibleBottom() -
        ((visibleBottom() < viewportHeight()) ? qreal(28) : qreal(0)));
    // Opening the overlay does not jump the desktop. Only a subsequent real
    // pointer movement starts finite follow over the newly visible region.
    if (visibleBottom() < viewportHeight() && !occlusion_follow_armed_)
        return;
    const QPointF pos = frameToWidget(cursor_pos_);
    if (zoom_ <= 1.01)
    {
        edge_pan_timer_->stop();
        edge_pan_target_ = content_pos_;
        qreal dx = 0.0, dy = 0.0;
        if (pos.x() < 0) dx = -pos.x();
        else if (pos.x() > width()) dx = width() - pos.x();
        if (pos.y() < 0) dy = -pos.y();
        else if (pos.y() > bottom) dy = bottom - pos.y();
        content_pos_ += QPointF(dx, dy);
        clampContentPos();
        return;
    }
    const QSizeF scaled = fittedSize() * zoom_;
    QPointF target = edge_pan_timer_->isActive() ? edge_pan_target_ : content_pos_;
    const qreal view_width = qreal(width());
    const qreal trigger_x = view_width * 0.12, comfort_x = view_width * 0.24;
    const qreal trigger_y = bottom * 0.12, comfort_y = bottom * 0.24;
    if (scaled.width() > view_width + 1.0)
    {
        if (pos.x() < trigger_x) target.rx() = content_pos_.x() + comfort_x - pos.x();
        else if (pos.x() > view_width-trigger_x)
            target.rx() = content_pos_.x() + view_width-comfort_x-pos.x();
        else if (pos.x() >= comfort_x && pos.x() <= view_width-comfort_x)
            target.rx() = content_pos_.x();
        target.rx() = qBound(view_width-scaled.width(), target.x(), qreal(0));
    }
    else target.rx() = content_pos_.x();

    const qreal available = visibleBottom();
    if (scaled.height() > available + 1.0)
    {
        if (pos.y() < trigger_y) target.ry() = content_pos_.y() + comfort_y-pos.y();
        else if (pos.y() > bottom-trigger_y)
            target.ry() = content_pos_.y() + bottom-comfort_y-pos.y();
        else if (pos.y() >= comfort_y && pos.y() <= bottom-comfort_y)
            target.ry() = content_pos_.y();
        target.ry() = qBound(available-scaled.height()-qreal(24),
                             target.y(), qreal(0));
    }
    else target.ry() = content_pos_.y();
    edge_pan_target_ = target;
    if (QLineF(content_pos_, target).length() > 0.75)
    {
        if (!edge_pan_timer_->isActive()) edge_pan_timer_->start();
    }
    else edge_pan_timer_->stop();
}
''', 'edge_pan_timer_')

    window_h = android / 'desktop_window.h'
    once(window_h, 'class DesktopView;', 'class DesktopView;\nclass CompactKeyboard;')
    once(window_h, '    void layoutControls();',
         '    void layoutControls();\n    void toggleCompactKeyboard();\n    void pastePhoneText();')
    once(window_h, '    KeyBar* key_bar_ = nullptr;',
         '    KeyBar* key_bar_ = nullptr;\n'
         '    CompactKeyboard* compact_keyboard_ = nullptr;\n'
         '    bool compact_keyboard_visible_ = false;')

    window_cc = android / 'desktop_window.cc'
    once(window_cc, '#include <QGridLayout>\n',
         '#include <QGridLayout>\n#include <QClipboard>\n#include <QGuiApplication>\n#include <QInputMethod>\n')
    once(window_cc, '#include "client/android/desktop_view.h"',
         '#include "client/android/desktop_view.h"\n'
         '#include "client/android/compact_keyboard.h"')
    once(window_cc,
         '    connect(key_bar_, &KeyBar::sig_taskManagerRequested, view_, &DesktopView::sendTaskManager);',
         '    connect(key_bar_, &KeyBar::sig_taskManagerRequested, view_, &DesktopView::sendTaskManager);\n'
         '    // The in-app keyboard never becomes the input focus: remote Windows does.\n'
         '    compact_keyboard_ = new CompactKeyboard(this);\n'
         '    compact_keyboard_->hide();\n'
         '    view_->setAttribute(Qt::WA_InputMethodEnabled, false);\n'
         '    connect(key_bar_, &KeyBar::sig_keyboardRequested, this, &DesktopWindow::toggleCompactKeyboard);\n'
         '    connect(key_bar_, &KeyBar::sig_pastePhoneText, this, &DesktopWindow::pastePhoneText);\n'
         '    connect(compact_keyboard_, &CompactKeyboard::sig_text, view_, &DesktopView::onVirtualText);\n'
         '    connect(compact_keyboard_, &CompactKeyboard::sig_key, view_, &DesktopView::onSpecialKey);')
    # Do not call the system keyboard from the KeyBar anymore.
    once(window_cc,
         '    connect(key_bar_, &KeyBar::sig_keyboardRequested, view_, &DesktopView::showSoftwareKeyboard);\n', '')
    # The action sheet keyboard opens our in-app keyboard as well.
    once(window_cc,
         '        else if (index == keyboard_index)\n            view_->showSoftwareKeyboard();',
         '        else if (index == keyboard_index)\n            toggleCompactKeyboard();')
    replace_method(window_cc, 'void DesktopWindow::layoutControls()', '''void DesktopWindow::layoutControls()
{
    if (!key_bar_) return;
    // In portrait or landscape, the single horizontal control strip always
    // sits on top of our own typing surface, never on the left side.
    key_bar_->setVerticalMode(false);
    const int native = qMax(0, keyboard_inset_);
    const int keyboard_height = compact_keyboard_visible_ ?
        qMin(height() * 38 / 100, 226) : 0;
    const int covered = qMax(native, keyboard_height);
    const int bar_height = key_bar_->barThickness();
    // Keep this control strip fixed on the absolute bottom edge.
    const int bar_y = qMax(0, height() - bar_height);
    key_bar_->setGeometry(0, bar_y, width(), bar_height);
    key_bar_->show();
    key_bar_->raise();

    if (compact_keyboard_)
    {
        if (compact_keyboard_visible_)
        {
            compact_keyboard_->setLandscapeMode(width() > height());
            compact_keyboard_->setGeometry(0, qMax(0, bar_y - keyboard_height),
                                          width(), keyboard_height);
            compact_keyboard_->show();
            compact_keyboard_->raise();
        }
        else compact_keyboard_->hide();
    }
    if (view_)
        view_->setOcclusionHeight(covered);
    if (fab_)
        fab_->move(width() - fab_->width() - kFabMargin,
                   qMax(0, bar_y - keyboard_height - fab_->height() - kFabMargin));
}

//--------------------------------------------------------------------------------------------------
void DesktopWindow::toggleCompactKeyboard()
{
    if (!connected_) return;
    // Do not let Samsung IME steal the viewport or display its own toolbar.
    QGuiApplication::inputMethod()->hide();
    view_->setAttribute(Qt::WA_InputMethodEnabled, false);
    compact_keyboard_visible_ = !compact_keyboard_visible_;
    layoutControls();
    view_->setFocus(Qt::OtherFocusReason);
}

//--------------------------------------------------------------------------------------------------
void DesktopWindow::pastePhoneText()
{
    if (!connected_) return;
    // Android permits clipboard reading while this app is foregrounded.
    // Unicode is sent directly, avoiding a race between clipboard sync and Ctrl+V.
    const QString text = QGuiApplication::clipboard()->text();
    if (!text.isEmpty()) view_->onVirtualText(text);
}
''', 'key_bar_->setVerticalMode')

    # For Android 12+, clipboard state may change while the app is backgrounded.
    # Qt's clipboard dataChanged signal alone is insufficient. Refresh after
    # foreground return, avoiding repeated background clipboard reads.
    clip_h = root / 'source/common/clipboard.h'
    once(clip_h, '    void clearClipboard();',
         '    void clearClipboard();\n    virtual void refreshFromSystem() {}')
    clip_android_h = root / 'source/common/clipboard_android.h'
    once(clip_android_h, '    ~ClipboardAndroid() final = default;',
         '    ~ClipboardAndroid() final = default;\n    void refreshFromSystem() final;')
    clip_android_cc = root / 'source/common/clipboard_android.cc'
    once(clip_android_cc, '#include <QMimeData>\n', '#include <QMimeData>\n#include <QTimer>\n')
    once(clip_android_cc, 'void ClipboardAndroid::onDataChanged()\n{',
         'void ClipboardAndroid::refreshFromSystem()\n{\n    onDataChanged();\n}\n\n'
         '//--------------------------------------------------------------------------------------------------\n'
         'void ClipboardAndroid::onDataChanged()\n{')
    once(window_cc,
         '        QTimer::singleShot(0, view_, [this]() { view_->update(); });',
         '        QTimer::singleShot(0, view_, [this]() { view_->update(); });\n'
         '        // Read external Android clipboard only once this activity is active.\n'
         '        QTimer::singleShot(150, this, [this]()\n'
         '        {\n'
         '            if (clipboard_ && connected_) clipboard_->refreshFromSystem();\n'
         '        });')
    # Also perform initial sync after the legacy session is established.
    once(window_cc, '    emit sig_sessionReady();\n    sendCapabilities();',
         '    emit sig_sessionReady();\n    sendCapabilities();\n'
         '    QTimer::singleShot(500, this, [this]()\n'
         '    {\n'
         '        if (clipboard_ && connected_) clipboard_->refreshFromSystem();\n'
         '    });')

    # New version; original repo's application ID and signer are preserved.
    once(root / 'CMakePresets.json',
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.6",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702006"',
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.7",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702007"')
    cmake = root / 'source/client/CMakeLists.txt'
    once(cmake, 'set(ASPIA_MOBILE_VERSION_CODE "20702006" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_CODE "20702007" CACHE STRING')
    once(cmake, 'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.6" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.7" CACHE STRING')
    print('PASS: Mobile 7 in-app RU/EN keyboard, horizontal KeyBar, bounded frame pan, paste, clipboard foreground refresh')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: mobile7-keyboard.py <prepared-mobile6-tree>')
    apply(Path(sys.argv[1]).resolve())
