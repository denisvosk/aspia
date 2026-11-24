#!/usr/bin/env python3
"""Mobile15: preserve the remote desktop wallpaper. Android UI only.

The existing authenticated session, notifications, audit, Host/Router/Relay,
and other desktop settings remain unchanged. Do not migrate Windows settings.
"""
from pathlib import Path
import sys


def once(path, old, new):
    s = path.read_text(encoding="utf-8")
    if s.count(old) != 1:
        raise RuntimeError(f"{path}: expected one anchor: {old[:120]!r}")
    path.write_text(s.replace(old, new, 1), encoding="utf-8")


def apply(root):
    android = root / "source/client/android"
    settings = android / "settings_widget.cc"
    window = android / "desktop_window.cc"

    # No user-facing option to change somebody's wallpaper.
    once(settings, '''    addBoolSetting(layout, tr("Disable desktop wallpaper"), !desktop_config_.wallpaper(),
                   [this](bool checked)
    {
        desktop_config_.set_wallpaper(!checked);
        Database::instance().setDesktopConfig(desktop_config_);
    });
''', '')

    # Ignore a previously saved false preference in the mobile session only.
    once(window,
         '    desktop_config_ = Database::instance().desktopConfig();',
         '    desktop_config_ = Database::instance().desktopConfig();\n'
         '    desktop_config_.set_wallpaper(true);')

    # Enforce preservation at the wire boundary for both protocols.
    # Legacy false is an opt-in disable bit, not a request to set a picture.
    once(window,
         '''        if (!config.wallpaper())
            flags |= proto::legacy::DISABLE_WALLPAPER;
''',
         '        // Never request a wallpaper change from a legacy Host.\n')
    once(window,
         '        message.mutable_config()->CopyFrom(desktop_config_);\n'
         '        sendMessage(proto::desktop::CHANNEL_ID_CONTROL, serialize(message));',
         '        message.mutable_config()->CopyFrom(desktop_config_);\n'
         '        message.mutable_config()->set_wallpaper(true);\n'
         '        sendMessage(proto::desktop::CHANNEL_ID_CONTROL, serialize(message));')

    # Bump only the Android package version.
    once(root / "CMakePresets.json",
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.14",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702014"',
         '"ASPIA_MOBILE_VERSION_NAME": "2.7.2-mobile.15",\n'
         '        "ASPIA_MOBILE_VERSION_CODE": "20702015"')
    cmake = root / "source/client/CMakeLists.txt"
    once(cmake, 'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.14" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_NAME "2.7.2-mobile.15" CACHE STRING')
    once(cmake, 'set(ASPIA_MOBILE_VERSION_CODE "20702014" CACHE STRING',
         'set(ASPIA_MOBILE_VERSION_CODE "20702015" CACHE STRING')
    print("PASS: Mobile15 leaves remote wallpaper enabled on legacy and modern sessions")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: mobile15-preserve-wallpaper.py <prepared-Mobile14-tree>")
    apply(Path(sys.argv[1]).resolve())
