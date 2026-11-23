// Aspia 2.7 community continuation, 2026. GPL-3.0-or-later.
#ifndef COMMON_CLIPBOARD_FILES_WIN_H
#define COMMON_CLIPBOARD_FILES_WIN_H
#include "common/clipboard_file_transfer.h"
#include <Windows.h>
#include <objidl.h>

namespace common {
struct ClipboardFileControl;
// All methods and OLE objects belong to the clipboard monitor's STA thread.
class ClipboardFilesWin {
public:
    explicit ClipboardFilesWin(ClipboardFileTransfer::Send send);
    ~ClipboardFilesWin();
    void receive(const proto::ClipboardFile& message);
    // True when this clipboard contains files (including our virtual files).
    bool onClipboardUpdate(HWND window);
    void resetRemote();
private:
    void setOffer(const proto::ClipboardFile& offer);
    std::shared_ptr<ClipboardFileControl> control_;
    std::unique_ptr<ClipboardFileTransfer> transfer_;
    IDataObject* object_ = nullptr;
    bool ole_initialized_ = false;
    DWORD sequence_ = 0;
};
} // namespace common
#endif
