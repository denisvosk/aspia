#!/usr/bin/env python3
"""Mobile13: Samsung-style punctuation and explicit Russian alternatives.
Applies after pinned Mobile12. Changes only CompactKeyboard and APK version.
"""
from pathlib import Path
import sys


def once(path, old, new):
    s = path.read_text(encoding='utf-8')
    if s.count(old) != 1:
        raise RuntimeError(f'{path}: expected one anchor: {old[:110]!r}')
    path.write_text(s.replace(old, new, 1), encoding='utf-8')


def region(path, begin, end, replacement):
    s = path.read_text(encoding='utf-8')
    if s.count(begin) != 1:
        raise RuntimeError(f'{path}: missing or ambiguous region {begin!r}')
    i = s.index(begin)
    j = s.index(end, i + len(begin))
    path.write_text(s[:i] + replacement + s[j:], encoding='utf-8')


def apply(root):
    a = root / 'source/client/android'
    h = a / 'compact_keyboard.h'
    cc = a / 'compact_keyboard.cc'
    once(h, 'class QTimer;', 'class QTimer;\nclass QHideEvent;')
    once(h, '    void resizeEvent(QResizeEvent* event) final;',
         '    void resizeEvent(QResizeEvent* event) final;\n'
         '    void hideEvent(QHideEvent* event) final;')
    once(h, '    void showPunctuationPopup();\n    void selectPunctuation(const QPoint& location);',
         '''    void showSymbolPopup();
    void cancelSymbolPopup();
    void chooseSymbol(int index);
    void highlightSymbol(int index);
    int symbolAt(const QPoint& location) const;
    bool symbolEvent(QObject* watched, QEvent* event);''')
    region(h, '    QWidget* punctuation_popup_ = nullptr;',
           '    QPushButton* space_key_ = nullptr;',
           '''    QWidget* symbol_popup_ = nullptr;
    QList<QPushButton*> symbol_buttons_;
    QTimer* symbol_timer_ = nullptr;
    QPushButton* symbol_anchor_ = nullptr;
    QPushButton* suppressed_release_ = nullptr;
    QStringList symbol_choices_;
    QPoint symbol_press_;
    bool symbol_holding_ = false;
    bool symbol_moved_ = false;
    QString draft_;
    InputMode input_mode_ = InputMode::HID;
''')
    once(cc, '#include <QFont>\n', '#include <QFont>\n#include <QHideEvent>\n')
    # No popup takes focus. Any other keyboard key dismisses a pending menu.
    once(cc, '    key->setFocusPolicy(Qt::NoFocus);\n    key->setSizePolicy',
         '    key->setFocusPolicy(Qt::NoFocus);\n'
         '    key->installEventFilter(this);\n    key->setSizePolicy')
    region(cc, '    dot_key_ = newKey(QStringLiteral("."));',
           '\n    QPushButton* enter =',
           '''    dot_key_ = newKey(QStringLiteral("."));
    footer->addWidget(dot_key_, 2);
    connect(dot_key_, &QPushButton::clicked, this, [this]()
    {
        emit sig_text(QStringLiteral("."), ru_);
        markSentenceStart();
    });
''')
    # Leave mode selection and the swipeable spacebar in their existing paths.
    region(cc, '    if (watched == dot_key_)\n', '    if (watched == space_key_)\n', '')
    once(cc, 'bool CompactKeyboard::eventFilter(QObject* watched, QEvent* event)\n{',
         '''bool CompactKeyboard::eventFilter(QObject* watched, QEvent* event)
{
    if (symbolEvent(watched, event))
        return true;''')
    once(cc, '''    QPushButton* key = letters_[row][index];
    // Do not emit Е/Ь after a 500 ms Ё/Ъ long-press on the same key.
    if (key->property("alternateConsumed").toBool())
    {
        key->setProperty("alternateConsumed", false);
        return;
    }

''', '')
    old_alt = '''void CompactKeyboard::configureAlternate(
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
        emit sig_text(shift_state_ != ShiftState::Off ? upper : lower, ru_);
        if (shift_state_ == ShiftState::Once)
        {
            shift_state_ = ShiftState::Off;
            updateLabels();
        }
    });
}'''
    once(cc, old_alt, '''void CompactKeyboard::configureAlternate(
    QPushButton* key, const QString& lower, const QString& upper)
{
    key->setProperty("alternateLower", lower);
    key->setProperty("alternateUpper", upper);
}''')
    region(cc, 'void CompactKeyboard::showPunctuationPopup()\n',
           'void CompactKeyboard::updateModeCaption()\n', r'''bool CompactKeyboard::symbolEvent(QObject* watched, QEvent* event)
{
    auto* key = qobject_cast<QPushButton*>(watched);
    if (!key)
        return false;

    if (event->type() == QEvent::MouseButtonPress)
    {
        const auto* mouse = static_cast<QMouseEvent*>(event);
        if (mouse->button() != Qt::LeftButton)
            return false;
        cancelSymbolPopup();
        if (suppressed_release_ == key)
            suppressed_release_ = nullptr;
        const bool is_letter = ru_ && !symbols_ &&
            key->property("alternateLower").isValid();
        if (key == dot_key_ || is_letter)
        {
            if (!symbol_timer_)
            {
                symbol_timer_ = new QTimer(this);
                symbol_timer_->setSingleShot(true);
                connect(symbol_timer_, &QTimer::timeout,
                        this, &CompactKeyboard::showSymbolPopup);
            }
            symbol_anchor_ = key;
            symbol_press_ = key->mapTo(this, mouse->position().toPoint());
            symbol_moved_ = false;
            symbol_timer_->start(key == dot_key_ ? 460 : 500);
        }
        return false; // ordinary QPushButton press and mouse grab
    }

    if (event->type() == QEvent::MouseButtonRelease && key == suppressed_release_)
    {
        suppressed_release_ = nullptr;
        key->setDown(false);
        event->accept();
        return true;
    }

    if (key != symbol_anchor_)
        return false;

    if (event->type() == QEvent::MouseMove && symbol_holding_)
    {
        const auto* mouse = static_cast<QMouseEvent*>(event);
        const QPoint point = key->mapTo(this, mouse->position().toPoint());
        if ((point - symbol_press_).manhattanLength() > 5)
            symbol_moved_ = true;
        highlightSymbol(symbolAt(point));
        return true;
    }

    if (event->type() == QEvent::MouseButtonRelease)
    {
        if (symbol_timer_)
            symbol_timer_->stop();
        if (!symbol_holding_)
        {
            cancelSymbolPopup();
            return false; // short tap: original key emits its normal character
        }
        const auto* mouse = static_cast<QMouseEvent*>(event);
        const QPoint point = key->mapTo(this, mouse->position().toPoint());
        const bool on_key = key->rect().contains(mouse->position().toPoint());
        const bool moved = symbol_moved_ ||
            (point - symbol_press_).manhattanLength() > 5;
        const int index = symbolAt(point);
        symbol_holding_ = false;
        key->setDown(false);
        // Never let the ordinary click fire after a long press.
        // Keep the convenient stationary comma shortcut from Mobile12.
        if (index >= 0)
            chooseSymbol(index);
        else if (key == dot_key_ && !moved && on_key)
            chooseSymbol(9);
        else if (on_key)
            highlightSymbol(-1); // explicit tap on the still-visible option
        else
            cancelSymbolPopup();
        event->accept();
        return true;
    }

    return false;
}

void CompactKeyboard::showSymbolPopup()
{
    if (!symbol_anchor_ || !symbol_anchor_->isDown() || !isVisible())
    {
        cancelSymbolPopup();
        return;
    }
    const bool dot = symbol_anchor_ == dot_key_;
    if (!dot && (!ru_ || symbols_))
    {
        cancelSymbolPopup();
        return;
    }

    if (mode_popup_)
        mode_popup_->hide();
    if (dot)
    {
        // Samsung reference: five columns extending left of the period.
        // ':' replaces the Samsung customization/pencil icon.
        symbol_choices_ = { QStringLiteral(":"), QStringLiteral("^"),
            QStringLiteral("%"), QStringLiteral("$"), QStringLiteral("#"),
            QStringLiteral("@"), QStringLiteral("'"), QStringLiteral("!"),
            QStringLiteral("?"), QStringLiteral(",") };
    }
    else
    {
        symbol_choices_ = { symbol_anchor_->property(
            shift_state_ == ShiftState::Off ? "alternateLower" :
                                             "alternateUpper").toString() };
    }

    if (!symbol_popup_)
    {
        symbol_popup_ = new QWidget(this);
        symbol_popup_->setObjectName(QStringLiteral("symbolPopup"));
        symbol_popup_->setFocusPolicy(Qt::NoFocus);
        symbol_popup_->setAttribute(Qt::WA_StyledBackground, true);
        for (int i = 0; i < 10; ++i)
        {
            auto* button = new QPushButton(symbol_popup_);
            button->setFocusPolicy(Qt::NoFocus);
            QFont font = button->font();
            font.setPixelSize(21);
            button->setFont(font);
            symbol_buttons_.append(button);
            connect(button, &QPushButton::clicked, this, [this, i]()
            {
                if (!symbol_holding_ && symbol_popup_->isVisible())
                    chooseSymbol(i);
            });
        }
    }
    symbol_popup_->setStyleSheet(dark_theme_ ?
        QStringLiteral("QWidget#symbolPopup{background:#222222;border-radius:9px;}") :
        QStringLiteral("QWidget#symbolPopup{background:#e2e2e5;border-radius:9px;}"));

    const QPoint origin = symbol_anchor_->mapTo(this, QPoint(0, 0));
    const int center = origin.x() + symbol_anchor_->width() / 2;
    const int columns = dot ? 5 : 1;
    const int gap = 2;
    // Last column is centered directly above the period, in both orientations.
    int cell_w = dot ? letters_[0][0]->width() + letter_rows_[0]->spacing() :
                      symbol_anchor_->width();
    cell_w = qMax(1, qMin(cell_w, qMin(
        center * 2 / (columns * 2 - 1), (width() - center) * 2)));
    const int pitch = dot ? qMax(symbol_anchor_->height(),
        origin.y() - letters_[2][0]->mapTo(this, QPoint(0, 0)).y()) :
        symbol_anchor_->height();
    const int rows = dot ? 3 : 1;
    const int available = qMax(1, origin.y() - gap);
    const int cell_h = qMax(1, qMin(pitch, available / rows));
    const int popup_h = rows * cell_h;
    const int left = center - (columns - 1) * cell_w - cell_w / 2;
    symbol_popup_->setGeometry(left, qMax(0, origin.y() - popup_h - gap),
                               columns * cell_w, popup_h);
    for (int i = 0; i < symbol_buttons_.size(); ++i)
    {
        auto* button = symbol_buttons_[i];
        if (i >= symbol_choices_.size())
        {
            button->hide();
            continue;
        }
        button->setText(symbol_choices_[i]);
        // Two selectable rows, with an empty middle row of equal height.
        const int y = dot ? (i / 5) * 2 * cell_h : 0;
        const int x = (i % columns) * cell_w;
        button->setGeometry(x, y, cell_w, cell_h);
        button->show();
    }
    symbol_holding_ = true;
    symbol_popup_->raise();
    symbol_popup_->show();
    highlightSymbol(dot ? 9 : -1);
}

int CompactKeyboard::symbolAt(const QPoint& point) const
{
    if (!symbol_popup_ || !symbol_popup_->isVisible() ||
        !symbol_popup_->geometry().contains(point))
        return -1;
    const QPoint local = symbol_popup_->mapFrom(this, point);
    for (int i = 0; i < symbol_choices_.size(); ++i)
    {
        if (symbol_buttons_[i]->geometry().contains(local))
            return i;
    }
    return -1; // the middle spacer is not a selectable character
}

void CompactKeyboard::highlightSymbol(int index)
{
    for (int i = 0; i < symbol_choices_.size(); ++i)
    {
        symbol_buttons_[i]->setStyleSheet(i == index ?
            QStringLiteral("QPushButton{background:#398bf3;color:white;border:0;border-radius:8px;}") :
            (dark_theme_ ? QStringLiteral("QPushButton{background:transparent;color:white;border:0;}"
                                          "QPushButton:pressed{background:#398bf3;border-radius:8px;}") :
                           QStringLiteral("QPushButton{background:transparent;color:#181818;border:0;}"
                                          "QPushButton:pressed{background:#398bf3;color:white;border-radius:8px;}")));
    }
}

void CompactKeyboard::chooseSymbol(int index)
{
    if (index < 0 || index >= symbol_choices_.size())
        return;
    const QString text = symbol_choices_[index];
    const bool letter = symbol_anchor_ != dot_key_;
    cancelSymbolPopup();
    emit sig_text(text, ru_); // identical HID/TXT/BUF path to ordinary keys
    if (letter && shift_state_ == ShiftState::Once)
    {
        shift_state_ = ShiftState::Off;
        updateLabels();
    }
    else if (!letter && (text == QStringLiteral("!") || text == QStringLiteral("?")))
        markSentenceStart();
}

void CompactKeyboard::cancelSymbolPopup()
{
    if (symbol_timer_)
        symbol_timer_->stop();
    if (symbol_holding_ && symbol_anchor_)
    {
        suppressed_release_ = symbol_anchor_;
        symbol_anchor_->setDown(false);
    }
    if (symbol_popup_)
        symbol_popup_->hide();
    symbol_holding_ = false;
    symbol_anchor_ = nullptr;
    symbol_choices_.clear();
}

void CompactKeyboard::hideEvent(QHideEvent* event)
{
    cancelSymbolPopup();
    QWidget::hideEvent(event);
}

''')
    once(cc, '''void CompactKeyboard::resizeEvent(QResizeEvent* event)
{
    QWidget::resizeEvent(event);''',
         '''void CompactKeyboard::resizeEvent(QResizeEvent* event)
{
    cancelSymbolPopup();
    QWidget::resizeEvent(event);''')
    once(cc, '''void CompactKeyboard::changeLanguage()
{
    ru_ = !ru_;''',
         '''void CompactKeyboard::changeLanguage()
{
    cancelSymbolPopup();
    ru_ = !ru_;''')
    # Distinct installable version; do not reuse Mobile12's version code.
    once(root / 'CMakePresets.json',
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.12",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702012"',
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.13",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702013"')
    cmake = root / 'source/client/CMakeLists.txt'
    once(cmake, 'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.12" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.13" CACHE STRING')
    once(cmake, 'set(ASPIA_MOBILE_VERSION_CODE "20702012" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_CODE "20702013" CACHE STRING')
    print('PASS: Mobile13 Samsung punctuation grid and explicit Russian alternative popup')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: mobile13-key-popups.py <prepared-Mobile12-tree>')
    apply(Path(sys.argv[1]).resolve())
