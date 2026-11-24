#!/usr/bin/env python3
"""Source regression: Android never requests wallpaper suppression.
Live Windows 2.7 and modern Host tests are still required.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
a = root / "source/client/android"
w = (a / "desktop_window.cc").read_text(encoding="utf-8")
s = (a / "settings_widget.cc").read_text(encoding="utf-8")
config = w.split("void DesktopWindow::sendConfig(", 1)[1].split(
    "void DesktopWindow::sendCapabilities()", 1)[0]
legacy = config.split("if (isLegacy())", 1)[1].split("    else\n", 1)[0]
modern = config.split("    else\n", 1)[1]
assert 'tr("Disable desktop wallpaper")' not in s
assert 'set_wallpaper(!checked)' not in s
assert ('desktop_config_ = Database::instance().desktopConfig();\n'
        '    desktop_config_.set_wallpaper(true);') in w
assert "DISABLE_WALLPAPER" not in legacy
assert "flags |= proto::legacy::ENABLE_CLIPBOARD;" in legacy
assert "flags |= proto::legacy::DISABLE_EFFECTS;" in legacy
assert "flags |= proto::legacy::LOCK_AT_DISCONNECT;" in legacy
assert "flags |= proto::legacy::BLOCK_REMOTE_INPUT;" in legacy
assert "legacy_config->set_flags(flags);" in legacy
assert "sendMessage(proto::desktop::CHANNEL_ID_LEGACY, serialize(message));" in legacy
assert modern.index("message.mutable_config()->CopyFrom(desktop_config_);") < modern.index(
    "message.mutable_config()->set_wallpaper(true);") < modern.index(
    "sendMessage(proto::desktop::CHANNEL_ID_CONTROL, serialize(message));")
assert 'tr("Enable clipboard")' in s
assert 'tr("Disable desktop effects")' in s
assert 'tr("Lock computer at disconnect")' in s
assert 'tr("Block remote input")' in s
assert "2.7.2-mobile.15" in (root / "CMakePresets.json").read_text(encoding="utf-8")
print("PASS: Mobile15 wallpaper preserved; other remote desktop options unchanged")
