#!/usr/bin/env python3
"""Mobile10: horizontal-only KeyBar and centered captions after Mobile9.

Keep exact keyboard handling, Router/Relay/Host protocols, signing identity,
clipboard paths, and biometric relock policy from the tested Mobile9.
"""
from pathlib import Path
import sys


def once(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one anchor, found {count}: {old[:100]!r}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def apply(root: Path) -> None:
    android = root / "source/client/android"
    bar = android / "key_bar.cc"
    window = android / "desktop_window.cc"

    # Prevent the 28px buttons + y margins exceeding the 33px strip.
    # Both the stationary LMB and the trailing More button sit at mid-height.
    once(bar, "    panel_layout_->setContentsMargins(2, 3, 2, 0);",
         "    panel_layout_->setContentsMargins(2, 0, 2, 0);")
    once(bar, "    controls_layout_->setContentsMargins(3, 3, 3, 0);",
         "    controls_layout_->setContentsMargins(3, 2, 3, 2);")
    once(bar, "    panel_layout_->addWidget(left_button_, 0);",
         "    panel_layout_->addWidget(left_button_, 0, Qt::AlignVCenter);")
    once(bar, "    panel_layout_->addWidget(more_button_);",
         "    panel_layout_->addWidget(more_button_, 0, Qt::AlignVCenter);")

    # Even when scroll bars are hidden, Qt kinetic scrolling can move a
    # 1px-overflowing child vertically and bounce beyond its bounds.
    # Center the child in the fixed-height viewport and disable bounce.
    once(bar, "#include <QScroller>\n",
         "#include <QScroller>\n#include <QScrollerProperties>\n")
    once(bar,
         "    QScroller::grabGesture(scroll_->viewport(), QScroller::TouchGesture);",
         """    QScroller::grabGesture(scroll_->viewport(), QScroller::TouchGesture);
    scroll_->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    QScroller* kinetic = QScroller::scroller(scroll_->viewport());
    QScrollerProperties flick = kinetic->scrollerProperties();
    flick.setScrollMetric(QScrollerProperties::VerticalOvershootPolicy,
                         QScrollerProperties::OvershootAlwaysOff);
    flick.setScrollMetric(QScrollerProperties::HorizontalOvershootPolicy,
                         QScrollerProperties::OvershootAlwaysOff);
    kinetic->setScrollerProperties(flick);
    // Never allow an accidental vertical offset, including on unusual
    // font scaling / density combinations.
    connect(scroll_->verticalScrollBar(), &QScrollBar::valueChanged,
            this, [this](int value)
    {
        if (value != 0)
            scroll_->verticalScrollBar()->setValue(0);
    });""")

    # Android may restore the Samsung IME above the app when returning from
    # the biometric overlay. Keep the custom keyboard in charge only when
    # it was open; never bypass or change the existing biometric relock.
    once(window,
         """    if (state != Qt::ApplicationActive)
        return;
    if (connected_)
    {""",
         """    if (state != Qt::ApplicationActive)
        return;
    if (connected_ && compact_keyboard_visible_ && view_)
    {
        // Android Activity resume is not an APK rollback. Keep the app-local
        // keyboard visible instead of the system IME after a secure unlock.
        view_->setAttribute(Qt::WA_InputMethodEnabled, false);
        QGuiApplication::inputMethod()->hide();
        layoutControls();
    }
    if (connected_)
    {""")

    once(root / "CMakePresets.json",
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.9",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702009"',
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.10",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702010"')
    cmake = root / "source/client/CMakeLists.txt"
    once(cmake, 'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.9" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.10" CACHE STRING')
    once(cmake, 'set(ASPIA_MOBILE_VERSION_CODE "20702009" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_CODE "20702010" CACHE STRING')
    print("PASS: Mobile10: 33px centered, horizontally scrolling-only KeyBar, "
          "Android IME kept behind custom keyboard on foreground resume")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: mobile10-keybar.py <prepared-mobile9-tree>")
    apply(Path(sys.argv[1]).resolve())
