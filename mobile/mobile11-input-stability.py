#!/usr/bin/env python3
"""Mobile11: preserve Samsung/Shift UI, pace physical key events, tolerate small finger drift.

Applied after Mobile10. Avoid protocol, Host, Router, Relay and signing changes.
These are input delivery changes for nested Aspia on Windows; live test remains required.
"""
from pathlib import Path
import sys


def replace_once(path: Path, before: str, after: str) -> None:
    original = path.read_text(encoding="utf-8")
    count = original.count(before)
    if count != 1:
        raise RuntimeError(f"{path}: expected one anchor, found {count}: {before[:90]!r}")
    path.write_text(original.replace(before, after, 1), encoding="utf-8")


def apply(root: Path) -> None:
    android = root / "source/client/android"
    view_h = android / "desktop_view.h"
    view = android / "desktop_view.cc"
    kb = android / "compact_keyboard.cc"

    # Android synthesizes pointer events from touch input; allowing a modest
    # amount of finger drift matches ordinary phone keyboards. A drag across
    # the spacebar remains handled by Mobile10's event filter instead.
    replace_once(kb,
        '#include <QMouseEvent>\n',
        '#include <QMouseEvent>\n#include <QPointF>\n')
    replace_once(kb,
        'namespace {\nconstexpr quint32 kUsbEnter = 0x070028;',
        '''namespace {
// Accept a tap when the finger drifts just outside a keycap during release.
// Unlike QAbstractButton's strict hitButton(), Samsung-like keys tolerate
// a small offset, but sliding a long distance must not type a letter.
class TolerantTouchKey final : public QPushButton
{
public:
    TolerantTouchKey(const QString& text, QWidget* parent)
        : QPushButton(text, parent) {}

protected:
    void mousePressEvent(QMouseEvent* event) override
    {
        if (event->button() == Qt::LeftButton)
            start_ = event->position();
        QPushButton::mousePressEvent(event);
    }

    void mouseReleaseEvent(QMouseEvent* event) override
    {
        const bool nearby = event->button() == Qt::LeftButton &&
            !rect().contains(event->position().toPoint()) &&
            (event->position() - start_).manhattanLength() <= 20.0;
        QPushButton::mouseReleaseEvent(event);
        if (nearby)
            click();  // Emits one click for a slightly misplaced release.
    }

private:
    QPointF start_;
};

constexpr quint32 kUsbEnter = 0x070028;''')
    replace_once(kb,
        '    QPushButton* key = new QPushButton(title, keys_panel_);',
        '    QPushButton* key = new TolerantTouchKey(title, keys_panel_);')

    # The old path sent key-down and key-up back-to-back (effectively 0ms).
    # Some nested Windows applications sample keyboard state across their
    # message dispatch cycle; pace virtual touch keys to resemble physical
    # keypresses and serialize them so rapid typing cannot interleave events.
    replace_once(view_h,
        '    void sendKeyWithModifiers(quint32 usb_keycode);',
        '    void sendKeyWithModifiers(quint32 usb_keycode);\n'
        '    void queueKeyboardStroke(quint32 usb_keycode, bool extra_shift);\n'
        '    void drainKeyboardStrokeQueue();')
    replace_once(view_h,
        '    QList<quint32> sticky_modifiers_;',
        '''    QList<quint32> sticky_modifiers_;
    struct TimedKeyboardStroke
    {
        quint32 usb_keycode = 0;
        QList<quint32> modifiers;
    };
    QList<TimedKeyboardStroke> timed_keyboard_strokes_;
    bool timed_keyboard_stroke_active_ = false;''')

    replace_once(view,
        '''    constexpr quint32 kShift = 0x0700e1;
    const bool local_shift = shift_needed && !sticky_modifiers_.contains(kShift);
    if (local_shift)
        sendRawKey(kShift, true);
    sendKeyWithModifiers(usb);
    if (local_shift)
        sendRawKey(kShift, false);''',
        '''    constexpr quint32 kShift = 0x0700e1;
    const bool local_shift = shift_needed && !sticky_modifiers_.contains(kShift);
    queueKeyboardStroke(usb, local_shift);''')

    replace_once(view,
        '''void DesktopView::onSpecialKey(quint32 usb_keycode)
{
    sendKeyWithModifiers(usb_keycode);
}''',
        '''void DesktopView::onSpecialKey(quint32 usb_keycode)
{
    // Backspace/Enter/Esc must retain their position relative to typed text.
    // Reuse the same ordered physical-key path for touchscreen keycaps.
    queueKeyboardStroke(usb_keycode, false);
}''')

    replace_once(view,
        '''void DesktopView::sendRawKey(quint32 usb_keycode, bool pressed)
{''',
        '''void DesktopView::queueKeyboardStroke(quint32 usb_keycode, bool extra_shift)
{
    TimedKeyboardStroke stroke;
    stroke.usb_keycode = usb_keycode;
    stroke.modifiers = sticky_modifiers_;

    constexpr quint32 kUsbShift = 0x0700e1;
    if (extra_shift && !stroke.modifiers.contains(kUsbShift))
        stroke.modifiers.prepend(kUsbShift);

    if (!sticky_modifiers_.isEmpty())
    {
        sticky_modifiers_.clear();
        emit sig_modifiersCleared();
    }

    timed_keyboard_strokes_.append(stroke);
    drainKeyboardStrokeQueue();
}

void DesktopView::drainKeyboardStrokeQueue()
{
    if (timed_keyboard_stroke_active_ || timed_keyboard_strokes_.isEmpty())
        return;

    timed_keyboard_stroke_active_ = true;
    const TimedKeyboardStroke stroke = timed_keyboard_strokes_.takeFirst();
    for (quint32 modifier : stroke.modifiers)
        sendRawKey(modifier, true);
    sendRawKey(stroke.usb_keycode, true);

    // Keep the actual key down for 32 ms: remote nested Qt clients then
    // observe a genuine non-zero pressed interval instead of an immediate
    // Windows scan-code down/up pair in the same scheduler slice.
    QTimer::singleShot(32, this, [this, stroke]()
    {
        sendRawKey(stroke.usb_keycode, false);
        for (auto it = stroke.modifiers.crbegin();
             it != stroke.modifiers.crend(); ++it)
        {
            sendRawKey(*it, false);
        }
        // Do not hold different keycaps at the same time; queue the next
        // event after a short release gap. UI feedback stays immediate.
        QTimer::singleShot(6, this, [this]()
        {
            timed_keyboard_stroke_active_ = false;
            drainKeyboardStrokeQueue();
        });
    });
}

//--------------------------------------------------------------------------------------------------
void DesktopView::sendRawKey(quint32 usb_keycode, bool pressed)
{''')

    replace_once(root / 'CMakePresets.json',
        '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.10",\n'
        '        "ASPIA_MOBILE_VERSION_CODE": "20702010"',
        '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.11",\n'
        '        "ASPIA_MOBILE_VERSION_CODE": "20702011"')
    client = root / 'source/client/CMakeLists.txt'
    replace_once(client,
        'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.10" CACHE STRING',
        'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.11" CACHE STRING')
    replace_once(client,
        'set(ASPIA_MOBILE_VERSION_CODE "20702010" CACHE STRING',
        'set(ASPIA_MOBILE_VERSION_CODE "20702011" CACHE STRING')

    print('PASS: Mobile11 held scan codes, serialized keys, tolerant 20px tap; '
          'Mobile10 Samsung layout/Shift untouched')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: mobile11-input-stability.py <prepared-mobile10-tree>')
    apply(Path(sys.argv[1]).resolve())
