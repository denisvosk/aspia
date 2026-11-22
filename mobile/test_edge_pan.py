#!/usr/bin/env python3
"""Source checks and a geometric model for bounded mobile remote-desktop auto-pan."""
from __future__ import annotations
import math
import sys
from pathlib import Path


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def step(cursor, image_offset, view_size, content_size, target=None):
    """Follow the C++ per-axis 12/24% hysteresis and finite animation."""
    x, y = cursor
    width, height = view_size
    content_w, content_h = content_size
    offset_x, offset_y = image_offset
    if target is None:
        target = image_offset
    tx, ty = target
    for i, (cursor_axis, offset, view, content, previous) in enumerate([
        (x, offset_x, width, content_w, tx),
        (y, offset_y, height, content_h, ty),
    ]):
        q = previous if math.dist(image_offset, target) > 0.75 else offset
        if content > view + 1:
            trigger = view * .12
            comfort = view * .24
            if cursor_axis < trigger:
                q = offset + comfort - cursor_axis
            elif cursor_axis > view-trigger:
                q = offset + view - comfort - cursor_axis
            elif comfort <= cursor_axis <= view-comfort:
                q = offset
            q = max(view-content, min(0, q))
        else:
            q = offset
        if i == 0:
            tx = q
        else:
            ty = q
    target = (tx, ty)
    delta = (tx-offset_x, ty-offset_y)
    distance = math.hypot(*delta)
    if distance <= .75:
        return (offset_x, offset_y), target, False
    travel = min(distance, min(28, max(1.25, distance*.20)))
    offset_x += delta[0]*travel/distance
    offset_y += delta[1]*travel/distance
    offset_x = max(width-content_w, min(0, offset_x))
    offset_y = max(height-content_h, min(0, offset_y))
    return (offset_x, offset_y), target, math.dist((offset_x,offset_y), target) > .75


def simulate_cursor_in_view(cursor_frame, view=(1000,600), content=(2000,1200), offset=(-500,-300)):
    target = None
    # The host cursor does not move: only rendered pixels move.
    pointer_positions=[]
    for n in range(500):
        point = (cursor_frame[0] + offset[0], cursor_frame[1] + offset[1])
        previous=offset
        offset,target,active=step(point,offset,view,content,target)
        pointer_positions.append(point)
        if not active:
            return n+1, offset, target, point, pointer_positions
    raise AssertionError("edge animation did not settle")


def main():
    root=Path(sys.argv[1])
    h=(root/'source/client/android/desktop_view.h').read_text()
    c=(root/'source/client/android/desktop_view.cc').read_text()
    guards = {
        'timer explicitly declared': 'QTimer* edge_pan_timer_ = nullptr;' in h,
        '15-60 fps timer': 'edge_pan_timer_->setInterval(16)' in c,
        'per-axis 12% trigger': 'view_width * 0.12' in c and 'bottom * 0.12' in c,
        'per-axis 24% comfort': 'view_width * 0.24' in c and 'bottom * 0.24' in c,
        'pending target persisted': 'edge_pan_target_ = target;' in c,
        'damped movement to target': 'const qreal travel = qMin(distance, qMin(qreal(28)' in c,
        'no motion on bound': 'QLineF(previous, content_pos_).length() < 0.01' in c,
        'no repeated finger-driven mouse movement when zoomed': 'if (zoom_ > 1.01)' in c and 'edge_scroll_timer_->stop();' in c,
        'two-finger wheel left unchanged': 'sendWheel(steps)' in c,
        'touch zoom cancels pan': 'edge_pan_target_ = content_pos_' in c,
    }
    for name, ok in guards.items():
        require(ok, name)

    # Right edge: cursor x=950, viewport 1000 -> stop when pointer moves
    # to approximately 760, not when it exits the outer trigger zone (880).
    steps,off,tar,point,positions=simulate_cursor_in_view((1450,600))
    require(15 <= steps <= 100, 'right-pan convergence duration')
    require(abs(point[0]-760) < 1, 'right-pan must stop at 24% comfort margin')
    require(abs(point[1]-300) < 1, 'idle perpendicular axis should not move')
    for i in range(10):
        old=off
        p=(1450+off[0],600+off[1])
        off,tar,active=step(p,off,(1000,600),(2000,1200),tar)
        require(not active and off == old, 'no movement after settling')

    # Diagonal into the bottom right corner should shift on both axes.
    steps,off,tar,point,_=simulate_cursor_in_view((1450,850))
    require(abs(point[0]-760)<1 and abs(point[1]-456)<1, 'diagonal comfort stop')

    # Remote border: there's not enough content beyond cursor; must stop at bounds.
    steps,off,tar,point,_=simulate_cursor_in_view((1950,1000),content=(2000,1200),offset=(-1000,-600))
    require(steps <= 100 and off[0]>=-1000 and off[1]>=-600, 'remote boundary clamp')

    print(f"PASS: {len(guards)} source guards + stationary-pointer, diagonal and boundary finite-pan scenarios")


if __name__ == '__main__':
    main()
