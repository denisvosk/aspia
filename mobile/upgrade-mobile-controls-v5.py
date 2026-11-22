#!/usr/bin/env python3
"""Aspia+ Mobile 5: usability overlay on the pinned, verified Mobile 4 sources.

Only Android remote-view UI/control files and the mobile package version change.
Keep the old Router/Host 2.7 protocol adaptation, book importer and credentials
unchanged. Every edit is anchored and refuses unknown source revisions.
"""
from __future__ import annotations

from pathlib import Path
import sys


def replace_once(path: Path, before: str, after: str) -> None:
    source = path.read_text(encoding="utf-8")
    count = source.count(before)
    if count != 1:
        raise ValueError(f"Expected one source anchor in {path}: found {count}\n{before[:120]}")
    path.write_text(source.replace(before, after, 1), encoding="utf-8")


def apply(root: Path) -> None:
    view_h = root / "source/client/android/desktop_view.h"
    replace_once(view_h,
        "    void sendCtrlAltDelete();\n    void resetZoom();\n",
        "    void sendCtrlAltDelete();\n    void resetZoom();\n"
        "    void sendRightClick();\n")
    replace_once(view_h,
        "    bool moved_ = false;\n    qreal pinch_distance_ = 0.0;",
        "    bool moved_ = false;\n    bool long_pressed_ = false;\n    qreal pinch_distance_ = 0.0;")

    view_cc = root / "source/client/android/desktop_view.cc"
    replace_once(view_cc,
        "void DesktopView::setKeyBarHeight(int height)\n{\n    key_bar_height_ = height;\n}",
        "void DesktopView::setKeyBarHeight(int height)\n{\n"
        "    key_bar_height_ = qMax(0, height);\n"
        "    clampContentPos();\n    update();\n}")
    replace_once(view_cc,
        "void DesktopView::resetZoom()\n{\n    cancelTouch();\n    zoom_ = 1.0;\n"
        "    content_pos_ = {};\n    clampContentPos();\n    update();\n}\n",
        "void DesktopView::resetZoom()\n{\n    cancelTouch();\n    zoom_ = 1.0;\n"
        "    content_pos_ = {};\n    clampContentPos();\n    update();\n}\n\n"
        "// Right click at the remote cursor. The quick button always releases an active drag first.\n"
        "void DesktopView::sendRightClick()\n{\n    cancelTouch();\n"
        "    sendClick(proto::input::MouseEvent::RIGHT_BUTTON);\n}\n")
    replace_once(view_cc,
        "    moved_ = false;\n    pinch_moved_ = false;\n    last_tap_time_ = {};",
        "    moved_ = false;\n    long_pressed_ = false;\n    pinch_moved_ = false;\n"
        "    last_tap_time_ = {};")
    replace_once(view_cc,
        "    // The finger has been held still long enough: grab the left button so the next moves drag.\n"
        "    if (gesture_ == Gesture::ONE_FINGER && !moved_ && !dragging_)\n"
        "        startDrag();",
        "    // Long press = right click; a rapid tap followed by a hold still starts a left drag.\n"
        "    if (gesture_ != Gesture::ONE_FINGER || moved_ || dragging_)\n        return;\n"
        "    if (armed_drag_)\n    {\n        startDrag();\n        return;\n    }\n"
        "    long_pressed_ = true;\n    last_tap_time_ = {};\n"
        "    sendClick(proto::input::MouseEvent::RIGHT_BUTTON);")
    replace_once(view_cc,
        "        gesture_ = Gesture::ONE_FINGER;\n        moved_ = false;\n        last_point_ = down[0];",
        "        gesture_ = Gesture::ONE_FINGER;\n        moved_ = false;\n"
        "        long_pressed_ = false;\n        last_point_ = down[0];")
    replace_once(view_cc,
        "            // Keep the cursor on screen: zoom/pan must not leave it outside the visible area.\n"
        "            ensureCursorVisible();\n            update();",
        "            // Do not pull the viewport back to the remote mouse after the user's pan.\n"
        "            update();")
    replace_once(view_cc,
        "        if (!dragging_ && !moved_)\n",
        "        if (!dragging_ && !moved_ && !long_pressed_)\n")
    replace_once(view_cc,
        "    return QSizeF(image_.size()).scaled(QSizeF(size()), Qt::KeepAspectRatio);",
        "    // Fit against the actually visible area above the persistent controls and IME.\n"
        "    return QSizeF(image_.size()).scaled(QSizeF(width(), viewportHeight()), Qt::KeepAspectRatio);")
    replace_once(view_cc,
        "    const int bar = (keyboard_inset_ > 0) ? key_bar_height_ : 0;\n"
        "    return height() - keyboard_inset_ - bar;",
        "    // The shortcut bar stays visible even with the software keyboard closed.\n"
        "    return qMax<qreal>(1.0, height() - keyboard_inset_ - key_bar_height_);")
    # When zoomed in, follow the virtual mouse if it approaches the viewport edge.
    # This is NOT a two-finger pan: two-finger movement always remains remote wheel scroll.
    replace_once(view_cc,
        "    qreal dx = 0.0;\n    qreal dy = 0.0;\n"
        "    if (pos.x() < 0.0)\n        dx = -pos.x();\n"
        "    else if (pos.x() > width())\n        dx = width() - pos.x();\n"
        "    if (pos.y() < 0.0)\n        dy = -pos.y();\n"
        "    else if (pos.y() > bottom)\n        dy = bottom - pos.y();",
        "    // Track the remote mouse with a margin at magnifications above fit.\n"
        "    // Keep room for the persistent quick bar, keyboard and the pointer hotspot.\n"
        "    const qreal edge_x = zoom_ > 1.01 ? qMin(qreal(42), width() * 0.12) : 0.0;\n"
        "    const qreal edge_y = zoom_ > 1.01 ? qMin(qreal(42), bottom * 0.12) : 0.0;\n"
        "    qreal dx = 0.0;\n    qreal dy = 0.0;\n"
        "    if (pos.x() < edge_x)\n        dx = edge_x - pos.x();\n"
        "    else if (pos.x() > width() - edge_x)\n        dx = width() - edge_x - pos.x();\n"
        "    if (pos.y() < edge_y)\n        dy = edge_y - pos.y();\n"
        "    else if (pos.y() > bottom - edge_y)\n        dy = bottom - edge_y - pos.y();")

    key_h = root / "source/client/android/key_bar.h"
    replace_once(key_h,
        "    void sig_specialKey(quint32 usb_keycode);\n",
        "    void sig_specialKey(quint32 usb_keycode);\n"
        "    void sig_keyboardRequested();\n    void sig_rightClickRequested();\n"
        "    void sig_fitRequested();\n"
        "    void sig_rotateRequested();\n")
    replace_once(key_h,
        "    void addModifier(QHBoxLayout* layout, const QString& text, quint32 usb_keycode);",
        "    void addAction(QHBoxLayout* layout, const QString& text, void (KeyBar::*signal)());\n"
        "    void addModifier(QHBoxLayout* layout, const QString& text, quint32 usb_keycode);")

    key_cc = root / "source/client/android/key_bar.cc"
    replace_once(key_cc,
        "    addSpecialKey(row, \"Esc\", kUsbEscape);\n"
        "    addSpecialKey(row, \"Tab\", kUsbTab);\n"
        "    addModifier(row, \"Ctrl\", kUsbLeftCtrl);\n"
        "    addModifier(row, \"Alt\", kUsbLeftAlt);\n"
        "    addModifier(row, \"Shift\", kUsbLeftShift);\n"
        "    addModifier(row, \"Win\", kUsbLeftMeta);",
        "    addAction(row, QStringLiteral(\"Клав.\"), &KeyBar::sig_keyboardRequested);\n"
        "    addAction(row, QStringLiteral(\"ПКМ\"), &KeyBar::sig_rightClickRequested);\n"
        "    addModifier(row, \"Ctrl\", kUsbLeftCtrl);\n"
        "    addModifier(row, \"Alt\", kUsbLeftAlt);\n"
        "    addAction(row, QStringLiteral(\"Вписать\"), &KeyBar::sig_fitRequested);\n"
        "    addAction(row, QStringLiteral(\"Поворот\"), &KeyBar::sig_rotateRequested);\n"
        "    addSpecialKey(row, \"Esc\", kUsbEscape);\n"
        "    addSpecialKey(row, \"Tab\", kUsbTab);\n"
        "    addModifier(row, \"Shift\", kUsbLeftShift);\n"
        "    addModifier(row, \"Win\", kUsbLeftMeta);")
    replace_once(key_cc,
        "//--------------------------------------------------------------------------------------------------\n"
        "void KeyBar::addModifier(QHBoxLayout* layout, const QString& text, quint32 usb_keycode)",
        "//--------------------------------------------------------------------------------------------------\n"
        "void KeyBar::addAction(QHBoxLayout* layout, const QString& text,\n"
        "                       void (KeyBar::*signal)())\n"
        "{\n    Button* button = new Button(text, Button::Role::TEXT, layout->parentWidget());\n"
        "    button->setFocusPolicy(Qt::NoFocus);\n"
        "    button->setFixedHeight(kKeyHeight);\n"
        "    connect(button, &QPushButton::clicked, this, signal);\n"
        "    layout->addWidget(button);\n}\n\n"
        "//--------------------------------------------------------------------------------------------------\n"
        "void KeyBar::addModifier(QHBoxLayout* layout, const QString& text, quint32 usb_keycode)")

    window_h = root / "source/client/android/desktop_window.h"
    replace_once(window_h,
        "    void showSessionActions();\n",
        "    void showSessionActions();\n    void rotateInterface();\n")
    replace_once(window_h,
        "    bool power_control_available_ = false;\n",
        "    bool power_control_available_ = false;\n"
        "    bool forced_orientation_ = false;\n    int keyboard_inset_ = 0;\n")

    window_cc = root / "source/client/android/desktop_window.cc"
    replace_once(window_cc,
        "#include <QGridLayout>\n",
        "#include <QGridLayout>\n"
        "#ifdef Q_OS_ANDROID\n#include <QCoreApplication>\n"
        "#include <QJniObject>\n#endif\n")
    replace_once(window_cc,
        "    key_bar_ = new KeyBar(this);\n    key_bar_->hide();\n",
        "    key_bar_ = new KeyBar(this);\n"
        "    // Keep mouse and keyboard controls available without opening the IME.\n"
        "    key_bar_->show();\n    key_bar_->raise();\n")
    replace_once(window_cc,
        "    connect(key_bar_, &KeyBar::sig_specialKey, view_, &DesktopView::onSpecialKey);\n",
        "    connect(key_bar_, &KeyBar::sig_specialKey, view_, &DesktopView::onSpecialKey);\n"
        "    connect(key_bar_, &KeyBar::sig_keyboardRequested, view_, &DesktopView::showSoftwareKeyboard);\n"
        "    connect(key_bar_, &KeyBar::sig_rightClickRequested, view_, &DesktopView::sendRightClick);\n"
        "    connect(key_bar_, &KeyBar::sig_fitRequested, view_, &DesktopView::resetZoom);\n"
        "    connect(key_bar_, &KeyBar::sig_rotateRequested, this, &DesktopWindow::rotateInterface);\n")
    replace_once(window_cc,
        "DesktopWindow::~DesktopWindow()\n{\n    if (session_keeper_)",
        "DesktopWindow::~DesktopWindow()\n{\n"
        "#ifdef Q_OS_ANDROID\n"
        "    if (forced_orientation_)\n"
        "    {\n        QNativeInterface::QAndroidApplication::runOnAndroidMainThread([]()\n"
        "        {\n            QJniObject activity = QNativeInterface::QAndroidApplication::context();\n"
        "            if (activity.isValid())\n"
        "                activity.callMethod<void>(\"setRequestedOrientation\", \"(I)V\", -1);\n"
        "        });\n    }\n#endif\n"
        "    if (session_keeper_)")
    replace_once(window_cc,
        "    int keyboard_index = -1;\n    int fit_index = -1;\n",
        "    int keyboard_index = -1;\n    int fit_index = -1;\n"
        "    int right_index = -1;\n    int rotate_index = -1;\n")
    replace_once(window_cc,
        "        fit_index = next_index++;\n"
        "        action_sheet_->addItem(QStringLiteral(\"Вписать в экран\"), \":/img/material/monitor.svg\");\n",
        "        fit_index = next_index++;\n"
        "        action_sheet_->addItem(QStringLiteral(\"Вписать в экран\"), \":/img/material/monitor.svg\");\n\n"
        "        right_index = next_index++;\n"
        "        action_sheet_->addItem(QStringLiteral(\"Правая кнопка мыши\"), \":/img/material/monitor.svg\");\n"
        "        rotate_index = next_index++;\n"
        "        action_sheet_->addItem(QStringLiteral(\"Повернуть экран\"), \":/img/material/refresh.svg\");\n"
        )
    replace_once(window_cc,
        "[this, power_index, keyboard_index, fit_index,\n"
        "             ctrl_alt_del_index, users_index, disconnect_index](int index)",
        "[this, power_index, keyboard_index, fit_index, right_index, rotate_index,\n"
        "             ctrl_alt_del_index, users_index, disconnect_index](int index)")
    replace_once(window_cc,
        "        else if (index == fit_index)\n            view_->resetZoom();\n",
        "        else if (index == fit_index)\n            view_->resetZoom();\n"
        "        else if (index == right_index)\n            view_->sendRightClick();\n"
        "        else if (index == rotate_index)\n            rotateInterface();\n")
    replace_once(window_cc,
        "    if (fab_)\n        fab_->move(width() - fab_->width() - kFabMargin, height() - fab_->height() - kFabMargin);\n\n"
        "    // Keep the key bar spanning the width; its vertical position is set when the keyboard changes.\n"
        "    if (key_bar_ && key_bar_->isVisible())\n"
        "        key_bar_->setGeometry(0, key_bar_->y(), width(), key_bar_->height());",
        "    const int bar_height = key_bar_ ? key_bar_->height() : 0;\n"
        "    const int bottom = qMax(0, height() - keyboard_inset_ - bar_height);\n"
        "    if (fab_)\n        fab_->move(width() - fab_->width() - kFabMargin,\n"
        "                   qMax(0, bottom - fab_->height() - kFabMargin));\n\n"
        "    if (key_bar_)\n    {\n"
        "        key_bar_->setGeometry(0, bottom, width(), bar_height);\n"
        "        key_bar_->raise();\n    }")
    replace_once(window_cc,
        "void DesktopWindow::onKeyboardInsetChanged(int inset)\n{\n"
        "    if (inset <= 0)\n    {\n        key_bar_->hide();\n        return;\n    }\n\n"
        "    const int bar_height = key_bar_->height();\n"
        "    key_bar_->setGeometry(0, height() - inset - bar_height, width(), bar_height);\n"
        "    key_bar_->raise();\n    key_bar_->show();\n}",
        "void DesktopWindow::onKeyboardInsetChanged(int inset)\n{\n"
        "    keyboard_inset_ = qMax(0, inset);\n"
        "    const int bar_height = key_bar_->height();\n"
        "    const int bottom = qMax(0, height() - keyboard_inset_ - bar_height);\n"
        "    key_bar_->setGeometry(0, bottom, width(), bar_height);\n"
        "    key_bar_->raise();\n    key_bar_->show();\n"
        "    if (fab_)\n        fab_->move(width() - fab_->width() - kFabMargin,\n"
        "                   qMax(0, bottom - fab_->height() - kFabMargin));\n}")
    replace_once(window_cc,
        "//--------------------------------------------------------------------------------------------------\n"
        "void DesktopWindow::showSessionActions()",
        "//--------------------------------------------------------------------------------------------------\n"
        "void DesktopWindow::rotateInterface()\n{\n"
        "    if (!connected_)\n        return;\n"
        "    view_->resetZoom();\n"
        "#ifdef Q_OS_ANDROID\n"
        "    forced_orientation_ = true;\n"
        "    const int target = width() >= height() ? 1 : 0; // portrait : landscape\n"
        "    QNativeInterface::QAndroidApplication::runOnAndroidMainThread([target]()\n"
        "    {\n        QJniObject activity = QNativeInterface::QAndroidApplication::context();\n"
        "        if (activity.isValid())\n"
        "            activity.callMethod<void>(\"setRequestedOrientation\", \"(I)V\", target);\n"
        "    });\n#endif\n}\n\n"
        "//--------------------------------------------------------------------------------------------------\n"
        "void DesktopWindow::showSessionActions()")

    java = root / "source/client/android/packaging/src/org/aspia/client/ClientActivity.java"
    replace_once(java,
        "            Os.setenv(\"QT_ANDROID_DISABLE_ACCESSIBILITY\", \"1\", true);",
        "            Os.setenv(\"QT_ANDROID_DISABLE_ACCESSIBILITY\", \"1\", true);\n"
        "            // Qt 6.11.1: prevent landscape IME extract mode (large blank input overlay).\n"
        "            Os.setenv(\"QT_ANDROID_NO_FULLSCREEN_KEYBOARD\", \"1\", true);")

    presets = root / "CMakePresets.json"
    replace_once(presets,
        '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.4",\n'
        '        "ASPIA_MOBILE_VERSION_CODE": "20702004"',
        '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.5",\n'
        '        "ASPIA_MOBILE_VERSION_CODE": "20702005"')
    cmake = root / "source/client/CMakeLists.txt"
    replace_once(cmake,
        'set(ASPIA_MOBILE_VERSION_CODE "20702004" CACHE STRING',
        'set(ASPIA_MOBILE_VERSION_CODE "20702005" CACHE STRING')
    replace_once(cmake,
        'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.4" CACHE STRING',
        'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.5" CACHE STRING')

    print("Aspia+ Mobile v5 controls: persistent shortcuts, right click, wheel scroll, mouse-follow fit, lock, rotation, compact IME")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: upgrade-mobile-controls-v5.py /path/to/fully-patched/source")
    apply(Path(sys.argv[1]).resolve())
