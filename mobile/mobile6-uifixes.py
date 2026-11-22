#!/usr/bin/env python3
"""Aspia+ Mobile 6 UX fixes on top of hash-pinned mobile.5 + finite edge-pan.

Limited to Android Client UI, AndroidManifest and lifecycle recovery; does not
alter router/relay/host, keys, books or network protocols. Exact anchors fail
closed on an unknown source state. All files remain GPL-3.0-or-later.
"""
from __future__ import annotations
from pathlib import Path
import sys


def once(path: Path, old: str, new: str) -> None:
    s = path.read_text(encoding='utf-8')
    count = s.count(old)
    if count != 1:
        raise ValueError(f'Expected exactly one matching anchor in {path}, found {count}: {old[:140]!r}')
    path.write_text(s.replace(old, new, 1), encoding='utf-8')


def apply(root: Path) -> None:
    android = root / 'source/client/android'
    # The native keyboard overlays the desktop; Android must not resize/reposition it.
    manifest = android / 'packaging/AndroidManifest.xml'
    once(manifest, 'android:windowSoftInputMode="adjustResize"',
         'android:windowSoftInputMode="adjustNothing"')

    # Keep existing renderer, pointer-to-frame transform and finite follow logic intact.
    view_h = android / 'desktop_view.h'
    once(view_h, '    void onSpecialKey(quint32 usb_keycode);',
         '    void onSpecialKey(quint32 usb_keycode);\n'
         '    void onLeftButtonHeld(bool held);\n'
         '    void sendTaskManager();')
    once(view_h, '    void sig_modifiersCleared();',
         '    void sig_modifiersCleared();\n'
         '    void sig_leftHoldCanceled();')
    once(view_h, '    bool long_pressed_ = false;',
         '    bool long_pressed_ = false;\n'
         '    bool left_button_held_ = false;')

    view_cc = android / 'desktop_view.cc'
    once(view_cc,
         'void DesktopView::showSoftwareKeyboard()\n{\n'
         '    setFocus();\n    QGuiApplication::inputMethod()->show();\n}',
         'void DesktopView::showSoftwareKeyboard()\n{\n'
         '    QInputMethod* method = QGuiApplication::inputMethod();\n'
         '    if (method->isVisible())\n    {\n'
         '        method->hide();\n        return;\n    }\n'
         '    setFocus();\n    method->show();\n}')

    # Sticky modifiers must NOT vanish every time the view is resized, a touch
    # is cancelled or the user presses Fit; that caused inconsistent chords.
    once(view_cc,
         '    sticky_modifiers_.clear();\n    emit sig_modifiersCleared();\n}\n\n'
         '//--------------------------------------------------------------------------------------------------\n'
         'void DesktopView::onModifierToggled',
         '    if (left_button_held_)\n    {\n'
         '        left_button_held_ = false;\n'
         '        emit sig_leftHoldCanceled();\n    }\n}\n\n'
         '//--------------------------------------------------------------------------------------------------\n'
         'void DesktopView::onModifierToggled')
    once(view_cc,
         'void DesktopView::onSpecialKey(quint32 usb_keycode)\n{\n'
         '    sendKeyWithModifiers(usb_keycode);\n}',
         'void DesktopView::onSpecialKey(quint32 usb_keycode)\n{\n'
         '    sendKeyWithModifiers(usb_keycode);\n}\n\n'
         '// The panel receives its own touch stream, separate from the remote\n'
         '// surface. One finger holds LMB; another moves the remote pointer.\n'
         'void DesktopView::onLeftButtonHeld(bool held)\n{\n'
         '    if (held == left_button_held_)\n        return;\n'
         '    left_button_held_ = held;\n'
         '    if (long_press_timer_)\n        long_press_timer_->stop();\n'
         '    button_mask_ = held ? proto::input::MouseEvent::LEFT_BUTTON : 0;\n'
         '    if (!held)\n        dragging_ = false;\n'
         '    sendMouse(button_mask_);\n}\n\n'
         '// One reliable atomic shortcut, independent of soft-keyboard timing.\n'
         'void DesktopView::sendTaskManager()\n{\n'
         '    const quint32 shift = 0x0700e1;\n'
         '    const quint32 esc = 0x070029;\n'
         '    sticky_modifiers_.clear();\n    emit sig_modifiersCleared();\n'
         '    sendRawKey(kUsbLeftCtrl, true);\n'
         '    sendRawKey(shift, true);\n'
         '    sendRawKey(esc, true);\n    sendRawKey(esc, false);\n'
         '    sendRawKey(shift, false);\n'
         '    sendRawKey(kUsbLeftCtrl, false);\n}')
    once(view_cc,
         '        case QEvent::WindowDeactivate:\n'
         '        case QEvent::Hide:\n'
         '            cancelTouch();\n'
         '            return QWidget::event(event);',
         '        case QEvent::WindowDeactivate:\n'
         '        case QEvent::Hide:\n'
         '            cancelTouch();\n'
         '            sticky_modifiers_.clear();\n'
         '            emit sig_modifiersCleared();\n'
         '            return QWidget::event(event);')
    once(view_cc,
         '        case QEvent::EnabledChange:\n'
         '            if (!isEnabled())\n'
         '                cancelTouch();\n'
         '            return QWidget::event(event);',
         '        case QEvent::EnabledChange:\n'
         '            if (!isEnabled())\n'
         '            {\n'
         '                cancelTouch();\n'
         '                sticky_modifiers_.clear();\n'
         '                emit sig_modifiersCleared();\n'
         '            }\n'
         '            return QWidget::event(event);')
    once(view_cc,
         '    if (gesture_ != Gesture::ONE_FINGER || moved_ || dragging_)\n'
         '        return;',
         '    if (gesture_ != Gesture::ONE_FINGER || moved_ || dragging_ || left_button_held_)\n'
         '        return;')
    once(view_cc, '        button_mask_ = 0;\n\n'
         '        // Holding the finger still also starts a drag.',
         '        button_mask_ = left_button_held_ ? proto::input::MouseEvent::LEFT_BUTTON : 0;\n\n'
         '        // Holding the finger still also starts a drag.')
    once(view_cc,
         '        if (!dragging_ && !moved_ && !long_pressed_)',
         '        if (!dragging_ && !moved_ && !long_pressed_ && !left_button_held_)')
    once(view_cc,
         '    if (count == 0 && button_mask_ != 0)',
         '    if (count == 0 && button_mask_ != 0 && !left_button_held_)')
    # Accidental pinch from panel holding is not possible: the panel is a distinct QWidget,
    # and events seen by the remote view contain only fingers on that view.

    # Keyboard rectangle remains a notification for panel placement; it does NOT
    # alter the remote frame, its zoom or top-left. adjustNothing keeps geometry.
    once(view_cc,
         '    // Re-fit and bring the remote cursor above the keyboard.\n'
         '    clampContentPos();\n    ensureCursorVisible();\n    update();',
         '    // Keyboard is a transparent overlay for geometry purposes. Do not\n'
         '    // change zoom, frame offset or cursor focus on its appearance.')
    once(view_cc,
         '    return qMax<qreal>(1.0, height() - keyboard_inset_ - key_bar_height_);',
         '    // The IME covers the frame, but may not re-fit or re-center it.\n'
         '    return qMax<qreal>(1.0, height() - key_bar_height_);')

    # KeyBar becomes a real horizontal finger-scrollable rail with a dedicated
    # LMB outside the scroll viewport. With IME open it is a narrow left rail,
    # never a second horizontal strip above the Samsung keyboard.
    key_h = android / 'key_bar.h'
    once(key_h, 'class QHBoxLayout;',
         'class QHBoxLayout;\nclass QBoxLayout;\nclass QScrollArea;')
    once(key_h,
         '    ~KeyBar() final;\n',
         '    ~KeyBar() final;\n\n'
         '    void setVerticalMode(bool enabled);\n'
         '    int barThickness() const { return 44; }\n'
         '    int railThickness() const { return 70; }\n')
    once(key_h, '    void clearModifiers();',
         '    void clearModifiers();\n'
         '    void resetLeftButton();')
    once(key_h, '    void sig_rotateRequested();',
         '    void sig_rotateRequested();\n'
         '    void sig_leftButtonHeld(bool held);\n'
         '    void sig_taskManagerRequested();')
    once(key_h, '    QList<Button*> modifier_buttons_;',
         '    QList<Button*> modifier_buttons_;\n'
         '    Button* left_button_ = nullptr;\n'
         '    Button* more_button_ = nullptr;\n'
         '    QBoxLayout* panel_layout_ = nullptr;\n'
         '    QBoxLayout* controls_layout_ = nullptr;\n'
         '    QWidget* controls_ = nullptr;\n'
         '    QScrollArea* scroll_ = nullptr;\n'
         '    bool vertical_ = false;')

    # The control layout can be horizontal or vertical, so helper signatures
    # must accept the QBoxLayout base class rather than QHBoxLayout.
    once(key_h, 'void addAction(QHBoxLayout*', 'void addAction(QBoxLayout*')
    once(key_h, 'void addModifier(QHBoxLayout*', 'void addModifier(QBoxLayout*')
    once(key_h, 'void addSpecialKey(QHBoxLayout*', 'void addSpecialKey(QBoxLayout*')

    key_cc = android / 'key_bar.cc'
    once(key_cc,
         '#include <QHBoxLayout>\n#include <QPalette>',
         '#include <QBoxLayout>\n#include <QHBoxLayout>\n#include <QPalette>\n'
         '#include <QScrollArea>\n#include <QScrollBar>\n#include <QScroller>\n'
         '#include <QPushButton>')
    once(key_cc, '#include "common/android/scroll_area.h"\n', '')
    once(key_cc, 'void KeyBar::addAction(QHBoxLayout*', 'void KeyBar::addAction(QBoxLayout*')
    once(key_cc, 'void KeyBar::addModifier(QHBoxLayout*', 'void KeyBar::addModifier(QBoxLayout*')
    once(key_cc, 'void KeyBar::addSpecialKey(QHBoxLayout*', 'void KeyBar::addSpecialKey(QBoxLayout*')
    s = key_cc.read_text(encoding='utf-8')
    start_marker = 'KeyBar::KeyBar(QWidget* parent)\n'
    end_marker = '//--------------------------------------------------------------------------------------------------\nKeyBar::~KeyBar()'
    start = s.find(start_marker)
    end = s.find(end_marker, start)
    if start < 0 or end < 0 or s.count(start_marker) != 1 or s.count(end_marker) != 1:
        raise ValueError('Unknown KeyBar constructor')
    ctor = '''KeyBar::KeyBar(QWidget* parent)
    : QWidget(parent)
{
    setFocusPolicy(Qt::NoFocus);
    setAutoFillBackground(true);
    QPalette pal = palette();
    pal.setColor(QPalette::Window, Controls::surfaceColor());
    setPalette(pal);

    panel_layout_ = new QBoxLayout(QBoxLayout::LeftToRight, this);
    panel_layout_->setContentsMargins(2, 2, 2, 2);
    panel_layout_->setSpacing(3);

    // LMB lives outside the scrolling surface. A stationary finger can hold
    // it while another finger moves the pointer on the remote desktop.
    left_button_ = new Button(QStringLiteral("ЛКМ"), Button::Role::TEXT, this);
    left_button_->setFocusPolicy(Qt::NoFocus);
    left_button_->setFixedHeight(kKeyHeight);
    connect(left_button_, &QPushButton::pressed, this, [this]()
    {
        left_button_->setRole(Button::Role::FILLED);
        emit sig_leftButtonHeld(true);
    });
    connect(left_button_, &QPushButton::released, this, [this]()
    {
        left_button_->setRole(Button::Role::TEXT);
        emit sig_leftButtonHeld(false);
    });
    panel_layout_->addWidget(left_button_, 0);

    scroll_ = new QScrollArea(this);
    scroll_->setFocusPolicy(Qt::NoFocus);
    scroll_->setFrameShape(QFrame::NoFrame);
    scroll_->setWidgetResizable(false);
    scroll_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scroll_->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    QScroller::grabGesture(scroll_->viewport(), QScroller::TouchGesture);

    controls_ = new QWidget(scroll_);
    controls_->setFocusPolicy(Qt::NoFocus);
    controls_layout_ = new QBoxLayout(QBoxLayout::LeftToRight, controls_);
    controls_layout_->setContentsMargins(3, 2, 3, 2);
    controls_layout_->setSpacing(3);
    controls_layout_->setSizeConstraint(QLayout::SetFixedSize);

    // Short captions remain horizontal in portrait and landscape.
    addAction(controls_layout_, QStringLiteral("Клав."), &KeyBar::sig_keyboardRequested);
    addModifier(controls_layout_, "Ctrl", kUsbLeftCtrl);
    addModifier(controls_layout_, "Alt", kUsbLeftAlt);
    addModifier(controls_layout_, "Shift", kUsbLeftShift);
    addSpecialKey(controls_layout_, "Пуск", kUsbLeftMeta);
    addModifier(controls_layout_, "Win", kUsbLeftMeta); // Win+E etc.
    addAction(controls_layout_, QStringLiteral("Впис."), &KeyBar::sig_fitRequested);
    addAction(controls_layout_, QStringLiteral("Повор."), &KeyBar::sig_rotateRequested);
    addSpecialKey(controls_layout_, "Esc", kUsbEscape);
    addSpecialKey(controls_layout_, "Tab", kUsbTab);
    addSpecialKey(controls_layout_, "F2", 0x07003b);
    addAction(controls_layout_, QStringLiteral("Задачи"), &KeyBar::sig_taskManagerRequested);
    addSpecialKey(controls_layout_, "Del", kUsbDelete);
    addSpecialKey(controls_layout_, "Home", kUsbHome);
    addSpecialKey(controls_layout_, "End", kUsbEnd);
    addSpecialKey(controls_layout_, "PgUp", kUsbPageUp);
    addSpecialKey(controls_layout_, "PgDn", kUsbPageDown);
    addSpecialKey(controls_layout_, "Left", kUsbLeft);
    addSpecialKey(controls_layout_, "Up", kUsbUp);
    addSpecialKey(controls_layout_, "Down", kUsbDown);
    addSpecialKey(controls_layout_, "Right", kUsbRight);
    scroll_->setWidget(controls_);
    panel_layout_->addWidget(scroll_, 1);

    // Fallback for Android variants where swipe-to-scroll is intercepted by
    // a keyboard gesture or a manufacturer's touch navigation.
    more_button_ = new Button(QStringLiteral("›"), Button::Role::TEXT, this);
    more_button_->setFocusPolicy(Qt::NoFocus);
    more_button_->setFixedWidth(35);
    more_button_->setFixedHeight(kKeyHeight);
    connect(more_button_, &QPushButton::clicked, this, [this]()
    {
        QScrollBar* bar = vertical_ ? scroll_->verticalScrollBar() : scroll_->horizontalScrollBar();
        const int stride = vertical_ ? qMax(40, scroll_->height() / 2) : qMax(80, scroll_->width() / 2);
        bar->setValue(bar->value() + stride > bar->maximum() ? bar->minimum() : bar->value() + stride);
    });
    panel_layout_->addWidget(more_button_);
    setFixedHeight(barThickness());
}

//--------------------------------------------------------------------------------------------------
'''
    key_cc.write_text(s[:start] + ctor + s[end:], encoding='utf-8')
    # Add the orientation switcher and LMB visual cancel to existing functions.
    once(key_cc,
         'KeyBar::~KeyBar() = default;\n',
         'KeyBar::~KeyBar() = default;\n\n'
         '// Always keep LMB visible; only the auxiliary keys change orientation.\n'
         'void KeyBar::setVerticalMode(bool enabled)\n'
         '{\n'
         '    if (vertical_ == enabled)\n        return;\n'
         '    vertical_ = enabled;\n'
         '    panel_layout_->setDirection(enabled ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);\n'
         '    controls_layout_->setDirection(enabled ? QBoxLayout::TopToBottom : QBoxLayout::LeftToRight);\n'
         '    controls_layout_->invalidate();\n'
         '    controls_->setFixedSize(controls_layout_->sizeHint());\n'
         '    more_button_->setText(enabled ? QStringLiteral("↓") : QStringLiteral("›"));\n'
         '    if (enabled)\n'
         '    {\n'
         '        setMinimumHeight(0);\n        setMaximumHeight(QWIDGETSIZE_MAX);\n'
         '        setFixedWidth(railThickness());\n'
         '    }\n'
         '    else\n'
         '    {\n'
         '        setMinimumWidth(0);\n        setMaximumWidth(QWIDGETSIZE_MAX);\n'
         '        setFixedHeight(barThickness());\n'
         '    }\n'
         '    scroll_->horizontalScrollBar()->setValue(0);\n'
         '    scroll_->verticalScrollBar()->setValue(0);\n'
         '    updateGeometry();\n'
         '}\n\n'
         'void KeyBar::resetLeftButton()\n'
         '{\n'
         '    if (left_button_)\n        left_button_->setRole(Button::Role::TEXT);\n'
         '}\n')

    window_h = android / 'desktop_window.h'
    once(window_h, '    void showSessionActions();',
         '    void showSessionActions();\n    void layoutControls();')
    window_cc = android / 'desktop_window.cc'
    once(window_cc,
         '    view_->setKeyBarHeight(key_bar_->height());',
         '    view_->setKeyBarHeight(key_bar_->barThickness());')
    once(window_cc,
         '    connect(key_bar_, &KeyBar::sig_rotateRequested, this, &DesktopWindow::rotateInterface);',
         '    connect(key_bar_, &KeyBar::sig_rotateRequested, this, &DesktopWindow::rotateInterface);\n'
         '    connect(key_bar_, &KeyBar::sig_leftButtonHeld, view_, &DesktopView::onLeftButtonHeld);\n'
         '    connect(view_, &DesktopView::sig_leftHoldCanceled, key_bar_, &KeyBar::resetLeftButton);\n'
         '    connect(key_bar_, &KeyBar::sig_taskManagerRequested, view_, &DesktopView::sendTaskManager);')
    # Use the same positioning on resize and keyboard changes.
    sz_start='    const int bar_height = key_bar_ ? key_bar_->height() : 0;\n'
    sz_end='        key_bar_->raise();\n    }'
    src=window_cc.read_text(encoding='utf-8')
    st=src.find(sz_start, src.index('void DesktopWindow::resizeEvent'))
    en=src.find(sz_end,st)
    if st<0 or en<0:
        raise ValueError('Mobile5 DesktopWindow resize positioning not found')
    src=src[:st]+ '    layoutControls();' + src[en+len(sz_end):]
    window_cc.write_text(src,encoding='utf-8')
    once(window_cc,
         'void DesktopWindow::onKeyboardInsetChanged(int inset)\n{\n'
         '    keyboard_inset_ = qMax(0, inset);\n'
         '    const int bar_height = key_bar_->height();\n'
         '    const int bottom = qMax(0, height() - keyboard_inset_ - bar_height);\n'
         '    key_bar_->setGeometry(0, bottom, width(), bar_height);\n'
         '    key_bar_->raise();\n    key_bar_->show();\n'
         '    if (fab_)\n'
         '        fab_->move(width() - fab_->width() - kFabMargin,\n'
         '                   qMax(0, bottom - fab_->height() - kFabMargin));\n}',
         'void DesktopWindow::onKeyboardInsetChanged(int inset)\n{\n'
         '    keyboard_inset_ = qMax(0, inset);\n'
         '    layoutControls();\n}\n\n'
         '// The Samsung IME stays at the bottom. The shortcut strip switches\n'
         '// into a thin left rail while the keyboard is visible.\n'
         'void DesktopWindow::layoutControls()\n{\n'
         '    if (!key_bar_)\n        return;\n'
         '    const bool keyboard_visible = keyboard_inset_ > 0;\n'
         '    key_bar_->setVerticalMode(keyboard_visible);\n'
         '    if (keyboard_visible)\n'
         '        key_bar_->setGeometry(0, 0, key_bar_->railThickness(),\n'
         '                              qMax(44, height() - keyboard_inset_));\n'
         '    else\n'
         '        key_bar_->setGeometry(0, qMax(0, height() - key_bar_->barThickness()),\n'
         '                              width(), key_bar_->barThickness());\n'
         '    key_bar_->show();\n    key_bar_->raise();\n'
         '    if (fab_)\n'
         '    {\n'
         '        const int usable_bottom = keyboard_visible ? qMax(0, height() - keyboard_inset_) :\n'
         '                                                qMax(0, height() - key_bar_->barThickness());\n'
         '        fab_->move(width() - fab_->width() - kFabMargin,\n'
         '                   qMax(0, usable_bottom - fab_->height() - kFabMargin));\n'
         '    }\n}')
    # Duplicate right-click entry in the 3-dot menu adds no value: a long
    # press on the desktop already provides right click.
    once(window_cc, '    int right_index = -1;\n', '')
    once(window_cc,
         '        right_index = next_index++;\n'
         '        action_sheet_->addItem(QStringLiteral("Правая кнопка мыши"), ":/img/material/monitor.svg");\n', '')
    once(window_cc,
         '[this, power_index, keyboard_index, fit_index, right_index, rotate_index,',
         '[this, power_index, keyboard_index, fit_index, rotate_index,')
    once(window_cc,
         '        else if (index == right_index)\n            view_->sendRightClick();\n', '')
    # The screen survives an Activity pause. Restore painting after resume.
    once(window_cc,
         '    if (state == Qt::ApplicationActive && was_connected_ && !connected_)\n'
         '        reconnect();',
         '    if (state != Qt::ApplicationActive)\n        return;\n'
         '    if (connected_)\n'
         '    {\n'
         '        // A restored Android surface may have lost its update request.\n'
         '        QTimer::singleShot(0, view_, [this]() { view_->update(); });\n'
         '    }\n'
         '    else if (was_connected_)\n'
         '        reconnect();')

    # Avoid opening the nested biometric/pin dialog directly from a Qt app
    # state-change signal. Queue it after Android's foreground transition.
    main = android / 'main_window.cc'
    once(main, '#include <QStackedWidget>\n', '#include <QStackedWidget>\n#include <QTimer>\n')
    once(main,
         '        if (Clock::now() - since >= kLockTimeout)\n            relock();',
         '        if (Clock::now() - since >= kLockTimeout)\n'
         '            QTimer::singleShot(0, this, [this]()\n'
         '            {\n'
         '                if (!relocking_ && QGuiApplication::applicationState() == Qt::ApplicationActive)\n'
         '                    relock();\n'
         '            });')
    # Version must advance for Android's in-place install while retaining the
    # exact application ID and same signing certificate.
    presets = root / 'CMakePresets.json'
    once(presets,
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.5",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702005"',
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.6",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702006"')
    cmake = root / 'source/client/CMakeLists.txt'
    once(cmake, 'set(ASPIA_MOBILE_VERSION_CODE "20702005" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_CODE "20702006" CACHE STRING')
    once(cmake, 'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.5" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.6" CACHE STRING')

    print('PASS: mobile6 LMB, keyboard left rail, stable IME overlay, modifiers and deferred resume')

if __name__ == '__main__':
    if len(sys.argv)!=2:
        raise SystemExit('Usage: mobile6-uifixes.py <complete-mobile5-source-tree>')
    apply(Path(sys.argv[1]).resolve())
