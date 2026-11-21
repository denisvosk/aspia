#!/usr/bin/env python3
"""Minimal Aspia+ Mobile v2 UX layer over the verified v3.0.37 mobile port.

Keep the existing 2.7 Router/Host compatibility patch unchanged. This layer
only makes the built-in Router editor reachable, adds a direct empty-book
"Add computer" action and increments the Android package version.
"""
from __future__ import annotations

import sys
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    data = path.read_text(encoding="utf-8")
    count = data.count(old)
    if count != 1:
        raise ValueError(f"Expected one matching code fragment in {path}, found {count}")
    path.write_text(data.replace(old, new, 1), encoding="utf-8")


def apply(root: Path) -> None:
    source = root / "source/client/android/main_window.cc"

    replace_once(source,
        """    SECTION_LOCAL = 0,
    SECTION_SETTINGS,
    SECTION_REMOTE,
    SECTION_ROUTERS
""",
        """    SECTION_LOCAL = 0,
    SECTION_ROUTERS,
    SECTION_SETTINGS,
    SECTION_REMOTE
""")

    replace_once(source,
        """    stack_content_->addWidget(local);
    stack_content_->addWidget(settings);
    stack_content_->addWidget(remote);
    stack_content_->addWidget(routers);
""",
        """    stack_content_->addWidget(local);
    stack_content_->addWidget(routers);
    stack_content_->addWidget(settings);
    stack_content_->addWidget(remote);
""")

    replace_once(source,
        """    nav_bar_->addItem(QStringLiteral("Компьютеры"), ":/img/folder.svg");
    nav_bar_->addItem(tr("Settings"), ":/img/settings.svg");
""",
        """    nav_bar_->addItem(QStringLiteral("Компьютеры"), ":/img/folder.svg");
    nav_bar_->addItem(QStringLiteral("Сервер"), ":/img/stack.svg");
    nav_bar_->addItem(QStringLiteral("Настройки"), ":/img/settings.svg");
""")

    local = root / "source/client/android/local_widget.cc"
    replace_once(local,
        """    auto* empty_hint = new Label(QStringLiteral("Импортируйте книгу .aab из консоли. "
        "Группы, адреса и сохранённые пароли перенесутся вместе."), Label::Role::BODY);""",
        """    auto* empty_hint = new Label(QStringLiteral("Для первого подключения добавьте Router "
        "на вкладке «Сервер», затем свой компьютер. Или импортируйте книгу .aab."), Label::Role::BODY);""")

    replace_once(local,
        '    auto* server_book = new Button(QStringLiteral("Загрузить с сервера"), Button::Role::TEXT);',
        '    auto* server_book = new Button(QStringLiteral("Добавить компьютер"), Button::Role::TEXT);')

    replace_once(local,
        '    connect(server_book, &Button::clicked, book_manager_, &MobileBookManager::configureSource);',
        '    connect(server_book, &Button::clicked, this, &LocalWidget::onAddHost);')

    presets = root / "CMakePresets.json"
    replace_once(presets,
        '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.1",',
        '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.2",')
    replace_once(presets,
        '"ASPIA_MOBILE_VERSION_CODE": "20702001"',
        '"ASPIA_MOBILE_VERSION_CODE": "20702002"')

    cmake = root / "source/client/CMakeLists.txt"
    replace_once(cmake,
        'set(ASPIA_MOBILE_VERSION_CODE "20702001" CACHE STRING',
        'set(ASPIA_MOBILE_VERSION_CODE "20702002" CACHE STRING')
    replace_once(cmake,
        'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.1" CACHE STRING',
        'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.2" CACHE STRING')

    print("Aspia+ Mobile 2.7.2-mobile.2: Router tab, manual Host setup, version bump applied")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: upgrade-mobile-v2.py /path/to/patched/aspia-source")
    apply(Path(sys.argv[1]).resolve())
