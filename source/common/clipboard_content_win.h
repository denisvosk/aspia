// Aspia 2.7 community continuation, 2026. GPL-3.0-or-later.
#ifndef COMMON_CLIPBOARD_CONTENT_WIN_H
#define COMMON_CLIPBOARD_CONTENT_WIN_H
#include "common/clipboard.h"
#include <Windows.h>
namespace common {
// Content is a single collection of decoded formats, separate from file offers.
bool readClipboardContentWin(HWND owner, std::string* text, proto::ClipboardEvent* content);
bool writeClipboardContentWin(HWND owner, const std::string& text, const proto::ClipboardEvent& content);
} // namespace common
#endif
