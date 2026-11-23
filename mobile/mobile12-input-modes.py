#!/usr/bin/env python3
"""Mobile12: three explicit keyboard transports plus punctuation long-press.

Works after Mobile11, preserving its HID timing/Shift, without altering
Windows Host, Router, Relay or the Desktop Protocol.
"""
from pathlib import Path
import sys


def once(path: Path, old: str, new: str):
    s = path.read_text(encoding='utf-8')
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f'{path}: expected one anchor, found {n}: {old[:110]!r}')
    path.write_text(s.replace(old, new, 1), encoding='utf-8')


def apply(root: Path):
    android = root / 'source/client/android'
    h = android / 'compact_keyboard.h'
    cc = android / 'compact_keyboard.cc'
    view = android / 'desktop_view.cc'
    window = android / 'desktop_window.cc'

    # The key captions are tiny and don't depend on changing language.
    once(h, '    void setLandscapeMode(bool enabled);', '''    void setLandscapeMode(bool enabled);

    enum class InputMode { HID, TXT, BUF };
    InputMode inputMode() const { return input_mode_; }
    void appendDraft(const QString& text);
    void editDraft(quint32 usb_keycode);
    void discardDraft();''')
    once(h, '    void sig_key(quint32 usb_keycode);', '''    void sig_key(quint32 usb_keycode);
    void sig_draftRequested(const QString& text);''')
    once(h, '    void changeLanguage();', '''    void changeLanguage();
    void showPunctuationPopup();
    void selectPunctuation(const QPoint& location);
    void updateModeCaption();''')
    once(h, '    QPushButton* space_key_ = nullptr;', '''    QPushButton* mode_key_ = nullptr;
    QPushButton* dot_key_ = nullptr;
    QWidget* punctuation_popup_ = nullptr;
    QList<QLabel*> punctuation_labels_;
    QTimer* punctuation_timer_ = nullptr;
    QStringList punctuation_choices_;
    QString draft_;
    InputMode input_mode_ = InputMode::HID;
    int punctuation_index_ = 0;
    bool punctuation_active_ = false;
    bool punctuation_moved_ = false;
    QPoint punctuation_press_;
    QPushButton* space_key_ = nullptr;''')
    once(h, 'class QHBoxLayout;', 'class QHBoxLayout;\nclass QTimer;')
    once(h, '#include <QPointF>\n', '#include <QPointF>\n#include <QStringList>\n')

    # A single small button takes the place of the unpopular comma key.
    # It does not shorten the Samsung spacebar or change the row's alignment.
    once(cc, '''    QPushButton* comma = newKey(QStringLiteral(","));
    footer->addWidget(comma, 2);
    connect(comma, &QPushButton::clicked, this,
            [this]() { emit sig_text(QStringLiteral(","), ru_); });''',
    '''    mode_key_ = newKey(QStringLiteral("HID"));
    setUtilityStyle(mode_key_);
    QFont mode_face = mode_key_->font();
    mode_face.setPixelSize(12);
    mode_key_->setFont(mode_face);
    footer->addWidget(mode_key_, 2);
    connect(mode_key_, &QPushButton::clicked, this, [this]()
    {
        if (input_mode_ == InputMode::BUF && !draft_.isEmpty())
        {
            emit sig_draftRequested(draft_);
            return;
        }
        input_mode_ = (input_mode_ == InputMode::HID) ? InputMode::TXT :
                      (input_mode_ == InputMode::TXT) ? InputMode::BUF : InputMode::HID;
        updateModeCaption();
    });''')

    once(cc, '''    QPushButton* dot = newKey(QStringLiteral("."));
    footer->addWidget(dot, 2);
    connect(dot, &QPushButton::clicked, this, [this]()
    {
        emit sig_text(QStringLiteral("."), ru_);
        markSentenceStart();
    });''',
    '''    dot_key_ = newKey(QStringLiteral("."));
    footer->addWidget(dot_key_, 2);
    dot_key_->installEventFilter(this);
    punctuation_choices_ = { QStringLiteral(","), QStringLiteral("?"),
        QStringLiteral("!"), QStringLiteral("@"), QStringLiteral("#"),
        QStringLiteral("%"), QStringLiteral("$"), QStringLiteral("'") };
    punctuation_timer_ = new QTimer(this);
    punctuation_timer_->setSingleShot(true);
    punctuation_timer_->setInterval(460);
    connect(dot_key_, &QPushButton::pressed, this, [this]()
    {
        punctuation_active_ = false;
        punctuation_moved_ = false;
        punctuation_timer_->start();
    });
    connect(dot_key_, &QPushButton::released, punctuation_timer_, &QTimer::stop);
    connect(punctuation_timer_, &QTimer::timeout,
            this, &CompactKeyboard::showPunctuationPopup);
    connect(dot_key_, &QPushButton::clicked, this, [this]()
    {
        if (punctuation_active_)
        {
            punctuation_active_ = false; // suppress ordinary period after a hold
            return;
        }
        emit sig_text(QStringLiteral("."), ru_);
        markSentenceStart();
    });''')

    # Touch delivery: the dot button keeps mouse-grab throughout the hold;
    # a child QWidget instead of QMenu avoids losing mouse-release events.
    # The popup ignores pointer events, so the dot still receives the drag.
    once(cc, '    if (watched == space_key_)\n', '''    if (watched == dot_key_)
    {
        if (event->type() == QEvent::MouseButtonPress)
        {
            const auto* mouse = static_cast<QMouseEvent*>(event);
            punctuation_press_ = dot_key_->mapTo(this, mouse->position().toPoint());
        }
        else if (event->type() == QEvent::MouseMove && punctuation_active_)
        {
            const auto* mouse = static_cast<QMouseEvent*>(event);
            const QPoint location = dot_key_->mapTo(this, mouse->position().toPoint());
            if ((location - punctuation_press_).manhattanLength() > 10)
            {
                punctuation_moved_ = true;
                selectPunctuation(location);
            }
        }
        else if (event->type() == QEvent::MouseButtonRelease)
        {
            punctuation_timer_->stop();
            if (punctuation_active_ && punctuation_popup_)
            {
                const auto* mouse = static_cast<QMouseEvent*>(event);
                if (punctuation_moved_)
                    selectPunctuation(dot_key_->mapTo(this, mouse->position().toPoint()));
                const QString chosen = punctuation_choices_.at(punctuation_index_);
                punctuation_popup_->hide();
                emit sig_text(chosen, ru_);
                if (chosen == QStringLiteral("?") || chosen == QStringLiteral("!"))
                    markSentenceStart();
                // Let QPushButton process the release; the clicked handler
                // checks punctuation_active_ to suppress a second character.
            }
        }
    }
    if (watched == space_key_)
''')

    once(cc, 'void CompactKeyboard::changeLanguage()\n{', '''void CompactKeyboard::showPunctuationPopup()
{
    if (!dot_key_ || !dot_key_->isDown())
        return;
    punctuation_active_ = true;
    punctuation_index_ = 0; // holding dot and releasing selects comma by default
    if (!punctuation_popup_)
    {
        punctuation_popup_ = new QWidget(this);
        punctuation_popup_->setFocusPolicy(Qt::NoFocus);
        punctuation_popup_->setAttribute(Qt::WA_TransparentForMouseEvents);
        punctuation_popup_->setStyleSheet(dark_theme_ ?
            QStringLiteral("background:#222226;border-radius:9px;") :
            QStringLiteral("background:#d8d8dc;border-radius:9px;"));
        auto* choices = new QHBoxLayout(punctuation_popup_);
        choices->setContentsMargins(3, 3, 3, 3);
        choices->setSpacing(1);
        for (const QString& sign : punctuation_choices_)
        {
            auto* label = new QLabel(sign, punctuation_popup_);
            label->setAttribute(Qt::WA_TransparentForMouseEvents);
            label->setAlignment(Qt::AlignCenter);
            QFont font = label->font();
            font.setPixelSize(21);
            label->setFont(font);
            choices->addWidget(label, 1);
            punctuation_labels_.append(label);
        }
    }
    const int target_width = qMin(qMax(180, width() * 3 / 4), width() - 12);
    const QPoint dot = dot_key_->mapTo(this, QPoint(0, 0));
    const int left = qBound(6, dot.x() + dot_key_->width() / 2 - target_width / 2,
                            qMax(6, width() - target_width - 6));
    punctuation_popup_->setGeometry(left, qMax(0, dot.y() - 56), target_width, 50);
    punctuation_popup_->raise();
    punctuation_popup_->show();
    selectPunctuation(QPoint(left + 8, punctuation_popup_->y() + 20));
}

void CompactKeyboard::selectPunctuation(const QPoint& point)
{
    if (!punctuation_popup_ || punctuation_choices_.isEmpty())
        return;
    // Once the popup is showing, the finger can slide over adjacent signs.
    const int relative_x = point.x() - punctuation_popup_->x();
    punctuation_index_ = qBound(0,
        (relative_x * punctuation_choices_.size()) / qMax(1, punctuation_popup_->width()),
        punctuation_choices_.size() - 1);
    for (int i = 0; i < punctuation_labels_.size(); ++i)
    {
        const bool selected = i == punctuation_index_;
        punctuation_labels_[i]->setStyleSheet(selected ?
            QStringLiteral("background:#398bf3;color:white;border-radius:7px;") :
            (dark_theme_ ? QStringLiteral("background:transparent;color:#ffffff;") :
                           QStringLiteral("background:transparent;color:#181818;")));
    }
}

void CompactKeyboard::updateModeCaption()
{
    if (!mode_key_) return;
    if (input_mode_ == InputMode::HID) mode_key_->setText(QStringLiteral("HID"));
    else if (input_mode_ == InputMode::TXT) mode_key_->setText(QStringLiteral("TXT"));
    else mode_key_->setText(draft_.isEmpty() ? QStringLiteral("BUF") :
        QStringLiteral("BUF·%1").arg(qMin(draft_.size(), 99)));
}

void CompactKeyboard::appendDraft(const QString& text)
{
    if (input_mode_ != InputMode::BUF || text.isEmpty()) return;
    constexpr int kMaxDraft = 4096;
    if (draft_.size() + text.size() <= kMaxDraft)
        draft_.append(text);
    updateModeCaption();
}

void CompactKeyboard::editDraft(quint32 usb_keycode)
{
    if (input_mode_ != InputMode::BUF) return;
    if (usb_keycode == kUsbBackspace && !draft_.isEmpty()) draft_.chop(1);
    else if (usb_keycode == kUsbEnter && draft_.size() < 4096)
        draft_ += QLatin1Char('\\n');
    updateModeCaption();
}

void CompactKeyboard::discardDraft()
{
    draft_.clear();
    input_mode_ = InputMode::HID;
    updateModeCaption();
}

void CompactKeyboard::changeLanguage()
{''')

    # Explicit HID usages from USB HID Usage Tables, Keyboard/Keypad page 0x07.
    # 0x35 = grave/tilde (RU Ё), 0x30 = right bracket (RU Ъ).
    once(view, '''    const quint32 usb = KeycodeConverter::qtKeycodeToUsbKeycode(
        key.toUpper().unicode());''',
    '''    const quint32 usb = (key == QChar(0x60)) ? 0x070035 :
                        (key == QChar(']')) ? 0x070030 :
                        KeycodeConverter::qtKeycodeToUsbKeycode(key.toUpper().unicode());''')

    # The three visible modes use only existing outgoing input/clipboard paths.
    # BUF is never sent on each key, and does not silently paste or restore.
    once(window, '#include <QInputMethod>\n',
         '#include <QInputMethod>\n#include <QMessageBox>\n')
    once(window, '''connect(compact_keyboard_, &CompactKeyboard::sig_text, view_, &DesktopView::onVirtualKeyboardText);''',
    '''connect(compact_keyboard_, &CompactKeyboard::sig_text, this,
        [this](const QString& text, bool russian_layout)
        {
            if (!connected_ || !view_ || !compact_keyboard_) return;
            switch (compact_keyboard_->inputMode())
            {
                case CompactKeyboard::InputMode::HID:
                    view_->onVirtualKeyboardText(text, russian_layout);
                    break;
                case CompactKeyboard::InputMode::TXT:
                    view_->onVirtualText(text);
                    break;
                case CompactKeyboard::InputMode::BUF:
                    compact_keyboard_->appendDraft(text);
                    break;
            }
        });''')
    once(window, '''connect(compact_keyboard_, &CompactKeyboard::sig_key, view_, &DesktopView::onSpecialKey);''',
    '''connect(compact_keyboard_, &CompactKeyboard::sig_key, this,
        [this](quint32 key)
        {
            if (!connected_ || !view_ || !compact_keyboard_) return;
            if (compact_keyboard_->inputMode() == CompactKeyboard::InputMode::BUF &&
                (key == 0x07002a || key == 0x070028))
                compact_keyboard_->editDraft(key);
            else
                view_->onSpecialKey(key);
        });
    connect(compact_keyboard_, &CompactKeyboard::sig_draftRequested, this,
        [this](const QString& draft)
        {
            if (!connected_ || !compact_keyboard_ || draft.isEmpty()) return;
            if (!desktop_config_.clipboard())
            {
                QMessageBox::information(this, QStringLiteral("BUF"),
                    QStringLiteral("Буфер удалённой системы запрещён в настройках сеанса."));
                return;
            }
            QMessageBox question(QMessageBox::Warning, QStringLiteral("Режим BUF"),
                QStringLiteral("Текст будет записан в удалённый буфер обмена. "
                               "Ранее скопированные данные могут быть заменены, "
                               "в том числе на телефоне при синхронизации. "
                               "Для вставки потом используйте Ctrl+V. "
                               "Вложенные терминалы не гарантируют доставку."),
                QMessageBox::NoButton, this);
            QPushButton* send = question.addButton(QStringLiteral("Передать в буфер"),
                QMessageBox::AcceptRole);
            QPushButton* discard = question.addButton(QStringLiteral("Удалить черновик"),
                QMessageBox::DestructiveRole);
            question.addButton(QStringLiteral("Продолжить набор"),
                QMessageBox::RejectRole);
            question.exec();
            if (question.clickedButton() == discard)
            {
                compact_keyboard_->discardDraft();
                return;
            }
            if (question.clickedButton() != send) return;
            proto::clipboard::Event event;
            Clipboard::addFormat(&event, Clipboard::kMimeTypeTextUtf8, draft.toUtf8());
            onClipboardEvent(event); // existing legacy or modern clipboard channel
            compact_keyboard_->discardDraft();
            QMessageBox::information(this, QStringLiteral("BUF"),
                QStringLiteral("Команда отправки текста в удалённый буфер передана. "
                               "Подождите синхронизации и нажмите Ctrl+V на конечном "
                               "компьютере. Доставка не подтверждена."));
        });''')

    once(root / 'CMakePresets.json',
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.11",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702011"',
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.12",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702012"')
    cmake = root / 'source/client/CMakeLists.txt'
    once(cmake, 'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.11" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.12" CACHE STRING')
    once(cmake, 'set(ASPIA_MOBILE_VERSION_CODE "20702011" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_CODE "20702012" CACHE STRING')
    print('PASS: Mobile12 punctuation hold + HID/TXT/explicit BUF, Russian HID Yo and hard sign')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: mobile12-input-modes.py <prepared-Mobile11-tree>')
    apply(Path(sys.argv[1]).resolve())
