//
// Aspia Project
// Copyright (C) 2016-2024 Dmitry Chapyshev <dmitry@aspia.ru>
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program. If not, see <https://www.gnu.org/licenses/>.
//

#include "common/clipboard_win.h"
#include "common/clipboard_files_win.h"
#include "common/clipboard_content_win.h"

#include "base/logging.h"
#include "base/strings/string_util.h"
#include "base/strings/unicode.h"
#include "base/win/message_window.h"
#include "base/win/scoped_clipboard.h"
#include "base/win/scoped_hglobal.h"

namespace common {

//--------------------------------------------------------------------------------------------------
ClipboardWin::ClipboardWin()
{
    LOG(LS_INFO) << "Ctor";
}

//--------------------------------------------------------------------------------------------------
ClipboardWin::~ClipboardWin()
{
    LOG(LS_INFO) << "Dtor";

    if (!window_)
    {
        LOG(LS_ERROR) << "Window not created";
        return;
    }

    files_.reset();
    RemoveClipboardFormatListener(window_->hwnd());
    window_.reset();
}

//--------------------------------------------------------------------------------------------------
void ClipboardWin::init()
{
    if (window_)
    {
        LOG(LS_ERROR) << "Window already created";
        return;
    }

    window_ = std::make_unique<base::win::MessageWindow>();

    if (!window_->create(std::bind(&ClipboardWin::onMessage,
                                   this,
                                   std::placeholders::_1, std::placeholders::_2,
                                   std::placeholders::_3, std::placeholders::_4)))
    {
        LOG(LS_ERROR) << "Couldn't create clipboard window.";
        return;
    }

    files_ = std::make_unique<ClipboardFilesWin>(
        [this](const proto::ClipboardEvent& event) { sendEvent(event); });

    if (!AddClipboardFormatListener(window_->hwnd()))
    {
        PLOG(LS_ERROR) << "AddClipboardFormatListener failed";
        return;
    }
}

//--------------------------------------------------------------------------------------------------
void ClipboardWin::setData(const std::string& data)
{
    setContent(data, proto::ClipboardEvent());
}

void ClipboardWin::setContent(const std::string& text, const proto::ClipboardEvent& content)
{
    if (!window_) return;
    if (files_) files_->resetRemote();
    if (!writeClipboardContentWin(window_->hwnd(), text, content))
        LOG(LS_ERROR) << "Unable to write clipboard content";
}

//--------------------------------------------------------------------------------------------------
bool ClipboardWin::onMessage(UINT message, WPARAM /* wParam */, LPARAM /* lParam */, LRESULT& result)
{
    switch (message)
    {
        case WM_CLIPBOARDUPDATE:
            onClipboardUpdate();
            break;

        default:
            return false;
    }

    result = 0;
    return true;
}

//--------------------------------------------------------------------------------------------------
void ClipboardWin::onClipboardUpdate()
{
    if (files_ && files_->onClipboardUpdate(window_->hwnd())) return;
    // Preserve the whole incoming bundle instead of echoing its plain text back.
    if (GetClipboardOwner() == window_->hwnd()) return;
    std::string text;
    proto::ClipboardEvent content;
    if (readClipboardContentWin(window_->hwnd(), &text, &content)) onData(text, content);
}

void ClipboardWin::setFileData(const proto::ClipboardEvent& event)
{
    proto::ClipboardFile message;
    if (files_ && parseFileClipboard(event, &message)) files_->receive(message);
}

} // namespace common
