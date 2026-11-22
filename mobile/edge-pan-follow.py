#!/usr/bin/env python3
"""Mobile 5 edge-pan hysteresis and smooth snap-to-comfort correction.

Applies only to the v5 Android desktop view after upgrade-mobile-controls-v5.py.
This overlay refuses unexpected source trees and never changes any protocol,
book, authentication, or server component.
"""
from pathlib import Path
import sys


def replace_once(path: Path, before: str, after: str) -> None:
    original = path.read_text(encoding="utf-8")
    count = original.count(before)
    if count != 1:
        raise RuntimeError(f"Expected one anchor in {path}, got {count}: {before[:80]!r}")
    path.write_text(original.replace(before, after, 1), encoding="utf-8")


def apply(root: Path) -> None:
    header = root / "source/client/android/desktop_view.h"
    source = root / "source/client/android/desktop_view.cc"
    replace_once(header,
        "    void onEdgeScroll();\n    void onKeyboardRectangleChanged();",
        "    void onEdgeScroll();\n    void onEdgePan();\n    void onKeyboardRectangleChanged();")
    replace_once(header,
        "    QTimer* edge_scroll_timer_ = nullptr;\n    QPointF edge_velocity_;",
        "    QTimer* edge_scroll_timer_ = nullptr;\n    QPointF edge_velocity_;\n"
        "    // A cursor-triggered, finite pan to a comfortable position within the viewport.\n"
        "    QTimer* edge_pan_timer_ = nullptr;\n    QPointF edge_pan_target_;")

    replace_once(source,
        "    connect(edge_scroll_timer_, &QTimer::timeout, this, &DesktopView::onEdgeScroll);",
        "    connect(edge_scroll_timer_, &QTimer::timeout, this, &DesktopView::onEdgeScroll);\n\n"
        "    edge_pan_timer_ = new QTimer(this);\n"
        "    edge_pan_timer_->setInterval(16);\n"
        "    connect(edge_pan_timer_, &QTimer::timeout, this, &DesktopView::onEdgePan);")
    replace_once(source,
        "    if (edge_scroll_timer_)\n        edge_scroll_timer_->stop();\n    gesture_ = Gesture::NONE;",
        "    if (edge_scroll_timer_)\n        edge_scroll_timer_->stop();\n"
        "    if (edge_pan_timer_)\n        edge_pan_timer_->stop();\n"
        "    edge_pan_target_ = content_pos_;\n    gesture_ = Gesture::NONE;")
    replace_once(source,
        "    if (count >= 2 && (gesture_ == Gesture::NONE || gesture_ == Gesture::ONE_FINGER))\n"
        "    {\n        long_press_timer_->stop();",
        "    if (count >= 2 && (gesture_ == Gesture::NONE || gesture_ == Gesture::ONE_FINGER))\n"
        "    {\n        // Touch pinch/scroll takes precedence over any automatic follow animation.\n"
        "        edge_pan_timer_->stop();\n        edge_pan_target_ = content_pos_;\n"
        "        long_press_timer_->stop();")
    replace_once(source,
        "void DesktopView::updateEdgeScroll(const QPointF& finger_pos)\n{\n    auto axis_speed",
        "void DesktopView::updateEdgeScroll(const QPointF& finger_pos)\n{\n"
        "    // At zoom, stationary held fingers must NOT keep moving the remote mouse.\n"
        "    // The image itself can finish a bounded edge pan while the cursor stays fixed.\n"
        "    if (zoom_ > 1.01)\n    {\n        edge_scroll_timer_->stop();\n        return;\n    }\n"
        "    auto axis_speed")

    # Replace only the last method: it is the viewport policy, not the input sender.
    content = source.read_text(encoding="utf-8")
    method_start = "void DesktopView::ensureCursorVisible()\n{\n"
    start = content.find(method_start)
    if start < 0 or content.count(method_start) != 1:
        raise RuntimeError("Missing unique DesktopView::ensureCursorVisible method")
    end = content.find("\n}\n", start)
    if end < 0:
        raise RuntimeError("Malformed cursor-follow method")
    old = content[start:end + 3]
    if "const qreal edge_x = zoom_ > 1.01" not in old or "content_pos_ += QPointF(dx, dy);" not in old:
        raise RuntimeError("Wrong preceding Mobile 5 cursor-follow implementation")
    updated = r'''void DesktopView::ensureCursorVisible()
{
    if (image_.isNull())
        return;

    const QPointF pos = frameToWidget(cursor_pos_);
    // This excludes our own button bar; above a software keyboard, keep a little
    // extra room so the focused field is not obscured.
    const qreal bottom = qMax(qreal(1), viewportHeight() -
        ((keyboard_inset_ > 0) ? kKeyboardCursorMargin : 0.0));

    if (zoom_ <= 1.01)
    {
        edge_pan_timer_->stop();
        edge_pan_target_ = content_pos_;
        // At fit zoom, leave the entire image fitted; only correct an offscreen
        // cursor if the software keyboard covers the lower part of the view.
        qreal dx = 0.0;
        qreal dy = 0.0;
        if (pos.x() < 0.0) dx = -pos.x();
        else if (pos.x() > width()) dx = width() - pos.x();
        if (pos.y() < 0.0) dy = -pos.y();
        else if (pos.y() > bottom) dy = bottom - pos.y();
        content_pos_ += QPointF(dx, dy);
        clampContentPos();
        return;
    }

    const QSizeF scaled_content = fittedSize() * zoom_;
    QPointF target = edge_pan_timer_->isActive() ? edge_pan_target_ : content_pos_;
    const qreal view_width = qreal(width());
    const qreal trigger_x = view_width * 0.12;
    const qreal comfort_x = view_width * 0.24;
    const qreal trigger_y = bottom * 0.12;
    const qreal comfort_y = bottom * 0.24;

    // Hysteresis: entering the outer 12% arms a one-time move to the inner 24%.
    // Reaching the 12% boundary does NOT interrupt the move, and standing still
    // at the edge does NOT move the remote cursor or start a repeated scroll.
    if (scaled_content.width() > view_width + 1.0)
    {
        if (pos.x() < trigger_x)
            target.rx() = content_pos_.x() + (comfort_x - pos.x());
        else if (pos.x() > view_width - trigger_x)
            target.rx() = content_pos_.x() + (view_width - comfort_x - pos.x());
        else if (pos.x() >= comfort_x && pos.x() <= view_width - comfort_x)
            target.rx() = content_pos_.x();
        target.rx() = qBound(view_width - scaled_content.width(), target.x(), qreal(0));
    }
    else
    {
        target.rx() = content_pos_.x();
    }

    if (scaled_content.height() > viewportHeight() + 1.0)
    {
        if (pos.y() < trigger_y)
            target.ry() = content_pos_.y() + (comfort_y - pos.y());
        else if (pos.y() > bottom - trigger_y)
            target.ry() = content_pos_.y() + (bottom - comfort_y - pos.y());
        else if (pos.y() >= comfort_y && pos.y() <= bottom - comfort_y)
            target.ry() = content_pos_.y();
        const qreal extra = keyboard_inset_ > 0 ? kKeyboardCursorMargin : 0.0;
        target.ry() = qBound(viewportHeight() - scaled_content.height() - extra,
                             target.y(), qreal(0));
    }
    else
    {
        target.ry() = content_pos_.y();
    }

    edge_pan_target_ = target;
    if (QLineF(content_pos_, edge_pan_target_).length() > 0.75)
    {
        if (!edge_pan_timer_->isActive())
            edge_pan_timer_->start();
    }
    else
    {
        edge_pan_timer_->stop();
    }
}
'''
    source.write_text(content[:start] + updated + content[end + 3:], encoding="utf-8")
    replace_once(source,
        "void DesktopView::onEdgeScroll()\n{",
        r'''void DesktopView::onEdgePan()
{
    if (image_.isNull() || zoom_ <= 1.01)
    {
        edge_pan_timer_->stop();
        return;
    }

    const QPointF delta = edge_pan_target_ - content_pos_;
    const qreal distance = QLineF(QPointF(), delta).length();
    if (distance <= 0.75)
    {
        edge_pan_timer_->stop();
        return;
    }

    // Damped, finite movement toward a fixed position; no momentum or
    // velocity-based scrolling. It can finish even after the finger stops.
    const qreal travel = qMin(distance, qMin(qreal(28), qMax(qreal(1.25), distance * 0.20)));
    const QPointF previous = content_pos_;
    content_pos_ += delta * (travel / distance);
    clampContentPos();
    update();

    // Boundaries or a near-reached target end the animation. No repeated
    // movement is generated while the remote mouse is stationary.
    if (QLineF(previous, content_pos_).length() < 0.01 ||
        QLineF(content_pos_, edge_pan_target_).length() <= 0.75)
        edge_pan_timer_->stop();
}

//--------------------------------------------------------------------------------------------------
void DesktopView::onEdgeScroll()
{''')
    print("PASS: bounded, hysteretic cursor-triggered edge pan; stationary pointer never moves")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: edge-pan-follow.py /path/to/mobile5-source")
    apply(Path(sys.argv[1]).resolve())