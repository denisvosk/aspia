#!/usr/bin/env python3
"""Mobile14: full-sized Russian alternative popups, highlighted mode choices,
and explicitly opted-in, ordered clipboard typing. Android only.
"""
from pathlib import Path
import sys


def once(path, old, new):
    s = path.read_text(encoding='utf-8')
    if s.count(old) != 1:
        raise RuntimeError(f'{path}: expected one anchor: {old[:120]!r}')
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
    vh = a / 'desktop_view.h'
    v = a / 'desktop_view.cc'
    w = a / 'desktop_window.cc'

    # Dot layout and gesture are preserved; the letter popup uses the
    # surrounding surface so it cannot be clipped by the keyboard top.
    once(h, '#include <QStringList>\n',
         '#include <QStringList>\n#include <QPointer>\n#include <functional>\n#include <utility>\n')
    once(h, '    ~CompactKeyboard() final = default;',
         '    ~CompactKeyboard() final;')
    once(h, '    QWidget* symbol_popup_ = nullptr;',
         '    QPointer<QWidget> symbol_popup_;')
    once(h, '    QWidget* mode_popup_ = nullptr;',
         '    QWidget* mode_popup_ = nullptr;\n    QList<QPushButton*> mode_buttons_;')
    once(h, '    void showModePopup();',
         '    void showModePopup();\n    void highlightMode(int index);\n'
         '    int modeAt(const QPoint& point) const;\n    void dismissModePopup();')
    once(cc, '#include <QHideEvent>\n', '#include <QHideEvent>\n#include <QMessageBox>\n')
    once(cc, 'void CompactKeyboard::resizeEvent(QResizeEvent* event)\n',
         '''CompactKeyboard::~CompactKeyboard()
{
    if (symbol_popup_ && symbol_popup_->parentWidget() != this)
        delete symbol_popup_.data();
}

void CompactKeyboard::resizeEvent(QResizeEvent* event)
''')
    once(cc, '    cancelSymbolPopup();\n    QWidget::resizeEvent(event);',
         '    cancelSymbolPopup();\n    dismissModePopup();\n    QWidget::resizeEvent(event);')
    once(cc, '    cancelSymbolPopup();\n    QWidget::hideEvent(event);',
         '    cancelSymbolPopup();\n    dismissModePopup();\n    QWidget::hideEvent(event);')
    once(cc, '''        cancelSymbolPopup();
        if (suppressed_release_ == key)''',
         '''        cancelSymbolPopup();
        if (key != mode_key_)
            dismissModePopup();
        if (suppressed_release_ == key)''')
    once(cc, '    if (event->type() == QEvent::MouseMove && symbol_holding_)\n',
         '''    // Tolerate small touch drift during a pending Ё/Ъ hold.
    if (event->type() == QEvent::MouseMove && key != dot_key_ &&
        !symbol_holding_ && symbol_timer_ && symbol_timer_->isActive())
    {
        const auto* mouse = static_cast<QMouseEvent*>(event);
        const QPoint point = key->mapTo(this, mouse->position().toPoint());
        if ((point - symbol_press_).manhattanLength() <= 20)
            return true;
        cancelSymbolPopup();
        return false;
    }

    if (event->type() == QEvent::MouseMove && symbol_holding_)
''')
    once(cc, '''    symbol_popup_->setStyleSheet(dark_theme_ ?
        QStringLiteral("QWidget#symbolPopup{background:#222222;border-radius:9px;}") :
        QStringLiteral("QWidget#symbolPopup{background:#e2e2e5;border-radius:9px;}"));''',
         '''    QWidget* surface = dot || !parentWidget() ? this : parentWidget();
    if (symbol_popup_->parentWidget() != surface)
        symbol_popup_->setParent(surface);
    symbol_popup_->setFocusPolicy(Qt::NoFocus);
    if (dot)
        symbol_popup_->setStyleSheet(dark_theme_ ?
            QStringLiteral("QWidget#symbolPopup{background:#222222;border-radius:9px;}") :
            QStringLiteral("QWidget#symbolPopup{background:#e2e2e5;border-radius:9px;}"));
    else
        symbol_popup_->setStyleSheet(dark_theme_ ?
            QStringLiteral("QWidget#symbolPopup{background:#202025;border:1px solid #888;"
                           "border-radius:10px;}") :
            QStringLiteral("QWidget#symbolPopup{background:#eeeeef;border:1px solid #777;"
                           "border-radius:10px;}"));''')
    once(cc, '''    symbol_popup_->setGeometry(left, qMax(0, origin.y() - popup_h - gap),
                               columns * cell_w, popup_h);''',
         '''    if (dot)
    {
        symbol_popup_->setGeometry(left, qMax(0, origin.y() - popup_h - gap),
                                   columns * cell_w, popup_h);
    }
    else
    {
        const QPoint key_pos = surface->mapFromGlobal(
            symbol_anchor_->mapToGlobal(QPoint(0, 0)));
        const int full_w = qMax(1, qMin(surface->width(),
            qMax(58, symbol_anchor_->width() + 16)));
        const int full_h = qMax(1, qMin(surface->height(),
            qMax(56, symbol_anchor_->height() + 16)));
        const int x = qBound(0, key_pos.x() + symbol_anchor_->width() / 2 - full_w / 2,
                            qMax(0, surface->width() - full_w));
        const int y = qBound(0, key_pos.y() - full_h - 4,
                            qMax(0, surface->height() - full_h));
        symbol_popup_->setGeometry(x, y, full_w, full_h);
    }''')
    once(cc, '''        button->setGeometry(x, y, cell_w, cell_h);
        button->show();''',
         '''        if (dot)
            button->setGeometry(x, y, cell_w, cell_h);
        else
            button->setGeometry(3, 3, qMax(1, symbol_popup_->width() - 6),
                                qMax(1, symbol_popup_->height() - 6));
        button->show();''')
    once(cc, '''    if (!symbol_popup_ || !symbol_popup_->isVisible() ||
        !symbol_popup_->geometry().contains(point))
        return -1;
    const QPoint local = symbol_popup_->mapFrom(this, point);''',
         '''    if (!symbol_popup_ || !symbol_popup_->isVisible())
        return -1;
    const QPoint local = symbol_popup_->mapFromGlobal(mapToGlobal(point));
    if (!symbol_popup_->rect().contains(local))
        return -1;''')
    once(cc, '''void CompactKeyboard::highlightSymbol(int index)
{
    for (int i = 0; i < symbol_choices_.size(); ++i)''',
         '''void CompactKeyboard::highlightSymbol(int index)
{
    if (symbol_popup_ && symbol_popup_->isVisible())
        symbol_popup_->raise();
    if (symbol_anchor_ && symbol_anchor_ != dot_key_ && !symbol_choices_.isEmpty())
    {
        symbol_buttons_[0]->setStyleSheet(index == 0 ?
            QStringLiteral("QPushButton{background:#398bf3;color:white;border:0;"
                           "border-radius:8px;font-size:25px;}") :
            (dark_theme_ ?
                QStringLiteral("QPushButton{background:#3d3d43;color:white;border:0;"
                               "border-radius:8px;font-size:25px;}"
                               "QPushButton:pressed{background:#398bf3;}") :
                QStringLiteral("QPushButton{background:#d6d6dc;color:#181818;border:0;"
                               "border-radius:8px;font-size:25px;}"
                               "QPushButton:pressed{background:#398bf3;color:white;}")));
        return;
    }
    for (int i = 0; i < symbol_choices_.size(); ++i)''')
    once(cc, '''    if (symbol_popup_)
        symbol_popup_->hide();
    symbol_holding_ = false;''',
         '''    if (symbol_popup_)
    {
        symbol_popup_->hide();
        if (symbol_popup_->parentWidget() != this)
            symbol_popup_->setParent(this);
    }
    symbol_holding_ = false;''')

    # Real hit boxes and blue feedback while dragging HID/TXT/BUF.
    region(cc, '    if (watched == mode_key_ && event->type() == QEvent::MouseButtonRelease',
           '    if (watched == space_key_)\n', r'''    if (watched == mode_key_ && mode_hold_fired_)
    {
        if (event->type() == QEvent::MouseMove &&
            mode_popup_ && mode_popup_->isVisible())
        {
            const auto* mouse = static_cast<QMouseEvent*>(event);
            highlightMode(modeAt(mode_key_->mapTo(this, mouse->position().toPoint())));
            return true;
        }
        if (event->type() == QEvent::MouseButtonRelease)
        {
            const auto* mouse = static_cast<QMouseEvent*>(event);
            const int index = modeAt(mode_key_->mapTo(this, mouse->position().toPoint()));
            mode_hold_timer_->stop();
            mode_key_->setDown(false);
            mode_hold_fired_ = false;
            if (index >= 0)
            {
                mode_popup_->hide();
                selectInputMode(index == 0 ? InputMode::HID :
                                index == 1 ? InputMode::TXT : InputMode::BUF);
            }
            else if (!mode_key_->rect().contains(mouse->position().toPoint()))
                dismissModePopup();
            else if (mode_popup_ && mode_popup_->isVisible())
                highlightMode(-1);
            event->accept();
            return true;
        }
    }
''')
    once(cc, '''            choices->addWidget(key, 1);
            connect(key, &QPushButton::clicked, this, [this, selected = option.first]()''',
         '''            choices->addWidget(key, 1);
            mode_buttons_.append(key);
            connect(key, &QPushButton::clicked, this, [this, selected = option.first]()''')
    once(cc, '''    mode_popup_->raise();
    mode_popup_->show();
}

void CompactKeyboard::selectInputMode''',
         '''    mode_popup_->raise();
    mode_popup_->show();
    mode_popup_->layout()->activate();
    highlightMode(-1);
}

int CompactKeyboard::modeAt(const QPoint& point) const
{
    if (!mode_popup_ || !mode_popup_->isVisible())
        return -1;
    const QPoint local = mode_popup_->mapFromGlobal(mapToGlobal(point));
    for (int i = 0; i < mode_buttons_.size(); ++i)
        if (mode_buttons_[i]->geometry().contains(local))
            return i;
    return -1;
}

void CompactKeyboard::highlightMode(int index)
{
    if (index < 0)
        index = static_cast<int>(input_mode_);
    for (int i = 0; i < mode_buttons_.size(); ++i)
    {
        mode_buttons_[i]->setStyleSheet(i == index ?
            QStringLiteral("QPushButton{background:#398bf3;color:white;border:0;"
                           "border-radius:6px;font-size:15px;}") :
            (dark_theme_ ?
                QStringLiteral("QPushButton{background:#343438;color:#f7f7f7;border:0;"
                               "border-radius:6px;font-size:15px;}"
                               "QPushButton:pressed{background:#398bf3;color:white;}") :
                QStringLiteral("QPushButton{background:#cbcbcf;color:#171717;border:0;"
                               "border-radius:6px;font-size:15px;}"
                               "QPushButton:pressed{background:#398bf3;color:white;}")));
    }
}

void CompactKeyboard::dismissModePopup()
{
    if (mode_hold_timer_)
        mode_hold_timer_->stop();
    if (mode_popup_)
        mode_popup_->hide();
    if (mode_hold_fired_ && mode_key_)
        mode_key_->setDown(false);
}

void CompactKeyboard::selectInputMode''')

    # User explicitly selects live BUF. Legacy 2.7 has no delivery ACK,
    # so warn before enabling automatic paste.
    once(h, '''    void appendDraft(const QString& text);
    void editDraft(quint32 usb_keycode);
    void discardDraft();''',
         '''    void setBufferAllowed(std::function<bool()> allowed)
    { buffer_allowed_ = std::move(allowed); }''')
    once(h, '    void sig_draftRequested(const QString& text);',
         '    void sig_inputModeChanged();')
    once(h, '    QString draft_;', '    std::function<bool()> buffer_allowed_;')
    once(cc, '''        // A quick tap in BUF can submit a pending draft for confirmation,
        // but does not ever switch the input method.
        if (input_mode_ == InputMode::BUF && !draft_.isEmpty())
            emit sig_draftRequested(draft_);''',
         '        // A quick tap never changes the input method.')
    once(cc, '''    if (input_mode_ == InputMode::BUF && !draft_.isEmpty())
    {
        // Cannot silently throw away typed BUF content on mode switch.
        emit sig_draftRequested(draft_);
        return;
    }
    input_mode_ = mode;
    updateModeCaption();''',
         '''    if (mode == InputMode::BUF)
    {
        if (!buffer_allowed_ || !buffer_allowed_())
        {
            QMessageBox::information(this, QStringLiteral("BUF"),
                QStringLiteral("Буфер обмена отключён или нет активного подключения."));
            return;
        }
        if (QMessageBox::warning(this, QStringLiteral("Экспериментальный режим BUF"),
            QStringLiteral("Текст передаётся в удалённый буфер, затем выполняется Ctrl+V. "
                           "Прежний буфер заменяется. Старый Host не подтверждает получение: "
                           "возможна вставка старого содержимого. Не используйте режим "
                           "для паролей или команд. Продолжить?"),
            QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel)
                != QMessageBox::Yes)
            return;
    }
    input_mode_ = mode;
    updateModeCaption();
    emit sig_inputModeChanged();''')
    region(cc, 'void CompactKeyboard::updateModeCaption()\n',
           'void CompactKeyboard::changeLanguage()\n', r'''void CompactKeyboard::updateModeCaption()
{
    if (!mode_key_) return;
    if (input_mode_ == InputMode::HID) mode_key_->setText(QStringLiteral("HID"));
    else if (input_mode_ == InputMode::TXT) mode_key_->setText(QStringLiteral("TXT"));
    else mode_key_->setText(QStringLiteral("BUF"));
}

''')

    # Serialize clipboard changes and physical paste strokes in the existing
    # queue. Do not log or persist clipboard contents.
    once(vh, '#include <memory>\n',
         '#include <memory>\n#include <functional>\n#include <QString>\n#include <utility>\n')
    once(vh, '    void onSpecialKey(quint32 usb_keycode);',
         '''    void onSpecialKey(quint32 usb_keycode);
    bool queueBufferPaste(const QString& text);
    void cancelBufferInput();
    bool hasCommandModifier() const;
    void setBufferHandlers(std::function<bool()> allowed,
                           std::function<bool(const QString&)> sender)
    {
        buffer_allowed_ = std::move(allowed);
        buffer_sender_ = std::move(sender);
    }''')
    once(vh, '''        QList<quint32> modifiers;
    };''',
         '''        QList<quint32> modifiers;
        QString clipboard_text;
    };
    std::function<bool()> buffer_allowed_;
    std::function<bool(const QString&)> buffer_sender_;
    quint64 buffer_epoch_ = 0;''')
    once(v, 'void DesktopView::drainKeyboardStrokeQueue()\n{',
         r'''bool DesktopView::hasCommandModifier() const
{
    return sticky_modifiers_.contains(0x0700e0) || sticky_modifiers_.contains(0x0700e4) ||
           sticky_modifiers_.contains(0x0700e2) || sticky_modifiers_.contains(0x0700e6) ||
           sticky_modifiers_.contains(0x0700e3) || sticky_modifiers_.contains(0x0700e7);
}

bool DesktopView::queueBufferPaste(const QString& text)
{
    if (text.isEmpty() || text.size() > 4096 ||
        !buffer_allowed_ || !buffer_allowed_())
        return false;
    if (!timed_keyboard_strokes_.isEmpty())
    {
        auto& last = timed_keyboard_strokes_.back();
        if (!last.clipboard_text.isEmpty() &&
            last.clipboard_text.size() + text.size() <= 4096)
        {
            last.clipboard_text += text;
            return true;
        }
    }
    if (timed_keyboard_strokes_.size() >= 128)
        return false;
    TimedKeyboardStroke stroke;
    stroke.usb_keycode = 0x070019;
    stroke.modifiers = { 0x0700e0 };
    stroke.clipboard_text = text;
    if (!sticky_modifiers_.isEmpty())
    {
        sticky_modifiers_.clear();
        emit sig_modifiersCleared();
    }
    timed_keyboard_strokes_.append(stroke);
    drainKeyboardStrokeQueue();
    return true;
}

void DesktopView::cancelBufferInput()
{
    ++buffer_epoch_;
    for (qsizetype i = timed_keyboard_strokes_.size(); i > 0; --i)
        if (!timed_keyboard_strokes_.at(i - 1).clipboard_text.isEmpty())
            timed_keyboard_strokes_.removeAt(i - 1);
}

void DesktopView::drainKeyboardStrokeQueue()
{''')
    region(v, '    const TimedKeyboardStroke stroke = timed_keyboard_strokes_.takeFirst();',
           '//--------------------------------------------------------------------------------------------------\nvoid DesktopView::sendRawKey(', r'''    const TimedKeyboardStroke stroke = timed_keyboard_strokes_.takeFirst();
    const auto sendStroke = [this, stroke]()
    {
        for (quint32 modifier : stroke.modifiers)
            sendRawKey(modifier, true);
        sendRawKey(stroke.usb_keycode, true);

        QTimer::singleShot(32, this, [this, stroke]()
        {
            sendRawKey(stroke.usb_keycode, false);
            for (auto it = stroke.modifiers.crbegin();
                 it != stroke.modifiers.crend(); ++it)
                sendRawKey(*it, false);
            QTimer::singleShot(6, this, [this, stroke]()
            {
                const auto next = [this]()
                {
                    timed_keyboard_stroke_active_ = false;
                    drainKeyboardStrokeQueue();
                };
                if (stroke.clipboard_text.isEmpty())
                    next();
                else
                    QTimer::singleShot(250, this, next);
            });
        });
    };

    if (stroke.clipboard_text.isEmpty())
    {
        sendStroke();
        return;
    }
    const quint64 epoch = buffer_epoch_;
    if (!buffer_allowed_ || !buffer_allowed_() || !buffer_sender_ ||
        !buffer_sender_(stroke.clipboard_text))
    {
        timed_keyboard_stroke_active_ = false;
        QTimer::singleShot(0, this, [this]() { drainKeyboardStrokeQueue(); });
        return;
    }
    // Legacy 2.7 has no clipboard ACK. This delay is only a best effort.
    QTimer::singleShot(650, this, [this, epoch, sendStroke]()
    {
        if (epoch != buffer_epoch_ || !buffer_allowed_ || !buffer_allowed_())
        {
            timed_keyboard_stroke_active_ = false;
            drainKeyboardStrokeQueue();
            return;
        }
        sendStroke();
    });
}

''')
    once(v, 'void DesktopView::handleTouch(QTouchEvent* event)\n{',
         '''void DesktopView::handleTouch(QTouchEvent* event)
{
    if (event->type() == QEvent::TouchBegin)
        cancelBufferInput();''')

    once(w, 'connect(compact_keyboard_, &CompactKeyboard::sig_text, this,\n',
         '''const auto bufferAllowed = [this]()
    {
        return connected_ && network_worker_ && desktop_config_.clipboard() &&
            QGuiApplication::applicationState() == Qt::ApplicationActive;
    };
    compact_keyboard_->setBufferAllowed(bufferAllowed);
    view_->setBufferHandlers(bufferAllowed,
        [this, bufferAllowed](const QString& text)
        {
            if (!bufferAllowed() || !compact_keyboard_ ||
                compact_keyboard_->inputMode() != CompactKeyboard::InputMode::BUF)
                return false;
            proto::clipboard::Event event;
            Clipboard::addFormat(&event, Clipboard::kMimeTypeTextUtf8, text.toUtf8());
            onClipboardEvent(event);
            return true; // queued locally; no receiver ACK
        });
    connect(compact_keyboard_, &CompactKeyboard::sig_inputModeChanged, view_,
            &DesktopView::cancelBufferInput);
    connect(compact_keyboard_, &CompactKeyboard::sig_text, this,
''')
    once(w, '''                case CompactKeyboard::InputMode::BUF:
                    compact_keyboard_->appendDraft(text);
                    break;''',
         '''                case CompactKeyboard::InputMode::BUF:
                    if (view_->hasCommandModifier())
                        view_->onVirtualKeyboardText(text, russian_layout);
                    else if (!view_->queueBufferPaste(text))
                        QMessageBox::information(this, QStringLiteral("BUF"),
                            QStringLiteral("Буфер недоступен или очередь заполнена."));
                    break;''')
    source = w.read_text(encoding='utf-8')
    start = 'connect(compact_keyboard_, &CompactKeyboard::sig_key, this,\n'
    tail = '''                               "компьютере. Доставка не подтверждена."));
        });'''
    if source.count(start) != 1 or source.count(tail) != 1:
        raise RuntimeError('Expected the Mobile13 draft callback')
    i = source.index(start)
    j = source.index(tail, i) + len(tail)
    w.write_text(source[:i] + '''connect(compact_keyboard_, &CompactKeyboard::sig_key, view_,
            &DesktopView::onSpecialKey);''' + source[j:], encoding='utf-8')
    once(w, '''    const QString text = QGuiApplication::clipboard()->text();
    if (!text.isEmpty()) view_->onVirtualText(text);''',
         '''    const QString text = QGuiApplication::clipboard()->text();
    if (text.isEmpty()) return;
    if (compact_keyboard_ &&
        compact_keyboard_->inputMode() == CompactKeyboard::InputMode::BUF)
    {
        if (!view_->queueBufferPaste(text))
            QMessageBox::information(this, QStringLiteral("BUF"),
                QStringLiteral("Буфер недоступен, текст слишком длинный или очередь заполнена."));
    }
    else view_->onVirtualText(text);''')
    once(w, '''    compact_keyboard_visible_ = !compact_keyboard_visible_;
    layoutControls();''',
         '''    compact_keyboard_visible_ = !compact_keyboard_visible_;
    if (!compact_keyboard_visible_)
        view_->cancelBufferInput();
    layoutControls();''')
    once(w, 'void DesktopWindow::startNewSession()\n{',
         'void DesktopWindow::startNewSession()\n{\n    view_->cancelBufferInput();')
    once(w, 'void DesktopWindow::onApplicationStateChanged(Qt::ApplicationState state)\n{',
         '''void DesktopWindow::onApplicationStateChanged(Qt::ApplicationState state)
{
    if (state != Qt::ApplicationActive)
        view_->cancelBufferInput();''')
    once(w, '        case NetworkWorker::Status::HOST_DISCONNECTED:\n        {',
         '        case NetworkWorker::Status::HOST_DISCONNECTED:\n        {\n            view_->cancelBufferInput();')

    once(root / 'CMakePresets.json',
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.13",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702013"',
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.14",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702014"')
    cmake = root / 'source/client/CMakeLists.txt'
    once(cmake, 'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.13" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.14" CACHE STRING')
    once(cmake, 'set(ASPIA_MOBILE_VERSION_CODE "20702013" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_CODE "20702014" CACHE STRING')
    print('PASS: Mobile14 letter popup geometry, mode highlighting and opt-in paced BUF')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: mobile14-popup-buffer.py <prepared-Mobile13-tree>')
    apply(Path(sys.argv[1]).resolve())
