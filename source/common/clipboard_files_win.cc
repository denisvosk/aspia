// Aspia 2.7 community continuation, 2026. GPL-3.0-or-later.
// Windows delayed rendering follows the FILEDESCRIPTOR/FILECONTENTS mechanism
// used by upstream Aspia 3.x. This implementation retains the 2.7 transport.
#include "common/clipboard_files_win.h"
#include "base/strings/unicode.h"
#include "base/win/scoped_clipboard.h"
#include <ShlObj.h>
#include <algorithm>
#include <atomic>
#include <cstring>
#include <limits>

namespace common {
struct ClipboardFileControl {
    ClipboardFileTransfer* transfer = nullptr;
    DWORD thread = GetCurrentThreadId();
};
namespace {
using ReadState = ClipboardFileTransfer::ReadState;

class RemoteFileStream final : public IStream {
public:
    RemoteFileStream(std::shared_ptr<ClipboardFileControl> control, proto::ClipboardFile offer,
                     uint32_t index, std::shared_ptr<ReadState> state)
        : control_(std::move(control)), offer_(std::move(offer)), index_(index), state_(std::move(state)) {}
    ~RemoteFileStream() { if (control_->transfer) control_->transfer->close(state_); }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** out) override
    {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (iid != IID_IUnknown && iid != IID_ISequentialStream && iid != IID_IStream) return E_NOINTERFACE;
        *out = static_cast<IStream*>(this); AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++refs_; }
    ULONG STDMETHODCALLTYPE Release() override
    {
        ULONG count = --refs_;
        if (!count) delete this;
        else if (count == 1 && reading_ && control_->transfer) control_->transfer->close(state_);
        return count;
    }
    HRESULT STDMETHODCALLTYPE Read(void* buffer, ULONG count, ULONG* read) override
    {
        if (read) *read = 0;
        if (count && !buffer) return STG_E_INVALIDPOINTER;
        if (GetCurrentThreadId() != control_->thread) return RPC_E_WRONG_THREAD;
        if (reading_) return RPC_E_CALL_REJECTED;
        reading_ = true;
        AddRef(); // A nested COM cancellation may release the caller's reference.
        struct Guard { RemoteFileStream* self; ~Guard() { self->reading_ = false; self->Release(); } } guard{this};
        ULONG done = 0;
        while (done < count)
        {
            if (!control_->transfer || state_->failed) return STG_E_READFAULT;
            if (state_->data.empty())
            {
                if (state_->last) break;
                control_->transfer->request(state_);
                const auto deadline = GetTickCount64() + 30000;
                while (state_->waiting && !state_->failed && control_->transfer)
                {
                    if (GetTickCount64() >= deadline)
                    { control_->transfer->close(state_); break; }
                    // Aspia's WIN task pump accepts network callbacks in nested loops.
                    MsgWaitForMultipleObjectsEx(0, nullptr, 20, QS_ALLINPUT, MWMO_INPUTAVAILABLE);
                    MSG message;
                    for (int n = 0; n < 64 && PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE); ++n)
                    {
                        if (message.message == WM_QUIT)
                        {
                            if (control_->transfer) control_->transfer->close(state_);
                            PostQuitMessage(static_cast<int>(message.wParam));
                            break;
                        }
                        TranslateMessage(&message);
                        DispatchMessageW(&message);
                    }
                }
                if (!control_->transfer || state_->failed) return STG_E_READFAULT;
                if (state_->data.empty() && state_->last) break;
            }
            const auto length = std::min<size_t>(count - done, state_->data.size());
            if (!length) return STG_E_READFAULT;
            memcpy(static_cast<char*>(buffer) + done, state_->data.data(), length);
            state_->data.erase(0, length);
            done += static_cast<ULONG>(length);
            position_ += length;
            if (read) *read = done;
        }
        return done == count ? S_OK : S_FALSE;
    }
    HRESULT STDMETHODCALLTYPE Write(const void*, ULONG, ULONG*) override { return STG_E_ACCESSDENIED; }
    HRESULT STDMETHODCALLTYPE Seek(LARGE_INTEGER move, DWORD origin, ULARGE_INTEGER* result) override
    {
        if (!control_->transfer || state_->failed) return STG_E_REVERTED;
        if (reading_) return RPC_E_CALL_REJECTED;
        int64_t base = 0;
        if (origin == STREAM_SEEK_CUR) base = static_cast<int64_t>(position_);
        else if (origin == STREAM_SEEK_END) base = static_cast<int64_t>(state_->size);
        else if (origin != STREAM_SEEK_SET) return STG_E_INVALIDFUNCTION;
        if (move.QuadPart < -base || move.QuadPart > static_cast<int64_t>(state_->size) - base)
            return STG_E_INVALIDFUNCTION;
        const auto target = static_cast<uint64_t>(base + move.QuadPart);
        if (target < position_)
        {
            control_->transfer->close(state_);
            state_ = control_->transfer->open(offer_, index_);
            if (!state_) return STG_E_REVERTED;
            position_ = 0;
        }
        char discard[65536];
        while (position_ < target)
        {
            ULONG got = 0;
            HRESULT hr = Read(discard, static_cast<ULONG>(std::min<uint64_t>(sizeof(discard), target - position_)), &got);
            if (FAILED(hr) || !got) return STG_E_READFAULT;
        }
        if (result) result->QuadPart = position_;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE SetSize(ULARGE_INTEGER) override { return STG_E_ACCESSDENIED; }
    HRESULT STDMETHODCALLTYPE CopyTo(IStream* destination, ULARGE_INTEGER size, ULARGE_INTEGER* read,
                                     ULARGE_INTEGER* written) override
    {
        if (!destination) return STG_E_INVALIDPOINTER;
        if (read) read->QuadPart = 0;
        if (written) written->QuadPart = 0;
        char buffer[65536];
        uint64_t left = size.QuadPart;
        while (left)
        {
            ULONG got = 0, put = 0;
            HRESULT hr = Read(buffer, static_cast<ULONG>(std::min<uint64_t>(left, sizeof(buffer))), &got);
            if (read) read->QuadPart += got;
            if (FAILED(hr)) return hr;
            if (got)
            {
                HRESULT whr = destination->Write(buffer, got, &put);
                if (written) written->QuadPart += put;
                if (FAILED(whr)) return whr;
                if (put != got) return STG_E_WRITEFAULT;
                left -= got;
            }
            if (hr == S_FALSE) return S_FALSE;
        }
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE Commit(DWORD) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE Revert() override { return STG_E_INVALIDFUNCTION; }
    HRESULT STDMETHODCALLTYPE LockRegion(ULARGE_INTEGER, ULARGE_INTEGER, DWORD) override { return STG_E_INVALIDFUNCTION; }
    HRESULT STDMETHODCALLTYPE UnlockRegion(ULARGE_INTEGER, ULARGE_INTEGER, DWORD) override { return STG_E_INVALIDFUNCTION; }
    HRESULT STDMETHODCALLTYPE Stat(STATSTG* stat, DWORD flags) override
    {
        if (!stat) return STG_E_INVALIDPOINTER;
        *stat = {};
        stat->type = STGTY_STREAM;
        stat->cbSize.QuadPart = offer_.entry(static_cast<int>(index_)).size();
        stat->grfMode = STGM_READ;
        if (!(flags & STATFLAG_NONAME))
        {
            auto name = base::wideFromUtf8(offer_.entry(static_cast<int>(index_)).name());
            stat->pwcsName = static_cast<wchar_t*>(CoTaskMemAlloc((name.size() + 1) * sizeof(wchar_t)));
            if (!stat->pwcsName) return E_OUTOFMEMORY;
            memcpy(stat->pwcsName, name.c_str(), (name.size() + 1) * sizeof(wchar_t));
        }
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE Clone(IStream**) override { return E_NOTIMPL; }
private:
    std::atomic<ULONG> refs_{1};
    std::shared_ptr<ClipboardFileControl> control_;
    proto::ClipboardFile offer_;
    uint32_t index_;
    std::shared_ptr<ReadState> state_;
    uint64_t position_ = 0;
    bool reading_ = false;
};

class RemoteFileObject final : public IDataObject {
public:
    RemoteFileObject(std::shared_ptr<ClipboardFileControl> control, const proto::ClipboardFile& offer)
        : control_(std::move(control)), offer_(offer)
    {
        descriptor_ = static_cast<CLIPFORMAT>(RegisterClipboardFormatW(CFSTR_FILEDESCRIPTORW));
        contents_ = static_cast<CLIPFORMAT>(RegisterClipboardFormatW(CFSTR_FILECONTENTS));
        effect_ = static_cast<CLIPFORMAT>(RegisterClipboardFormatW(CFSTR_PREFERREDDROPEFFECT));
    }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** out) override
    {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (iid != IID_IUnknown && iid != IID_IDataObject) return E_NOINTERFACE;
        *out = static_cast<IDataObject*>(this); AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++refs_; }
    ULONG STDMETHODCALLTYPE Release() override { ULONG count = --refs_; if (!count) delete this; return count; }
    HRESULT STDMETHODCALLTYPE QueryGetData(FORMATETC* format) override
    {
        if (!format) return E_POINTER;
        if (format->dwAspect != DVASPECT_CONTENT) return DV_E_DVASPECT;
        if (format->cfFormat == contents_)
        {
            if (!(format->tymed & TYMED_ISTREAM)) return DV_E_TYMED;
            if (format->lindex == -1) return S_OK; // Format availability query from Explorer.
            if (format->lindex < 0 || format->lindex >= offer_.entry_size() ||
                offer_.entry(format->lindex).directory()) return DV_E_LINDEX;
            return S_OK;
        }
        if (format->cfFormat != descriptor_ && format->cfFormat != effect_) return DV_E_FORMATETC;
        if (!(format->tymed & TYMED_HGLOBAL)) return DV_E_TYMED;
        return format->lindex == -1 ? S_OK : DV_E_LINDEX;
    }
    HRESULT STDMETHODCALLTYPE GetData(FORMATETC* format, STGMEDIUM* medium) override
    {
        if (!medium) return E_POINTER;
        *medium = {};
        HRESULT hr = QueryGetData(format);
        if (FAILED(hr)) return hr;
        if (format->cfFormat == contents_)
        {
            if (format->lindex < 0 || format->lindex >= offer_.entry_size() ||
                offer_.entry(format->lindex).directory()) return DV_E_LINDEX;
            if (!control_->transfer) return STG_E_REVERTED;
            auto state = control_->transfer->open(offer_, static_cast<uint32_t>(format->lindex));
            if (!state) return STG_E_REVERTED;
            medium->tymed = TYMED_ISTREAM;
            medium->pstm = new RemoteFileStream(control_, offer_, static_cast<uint32_t>(format->lindex), state);
            return S_OK;
        }
        const size_t bytes = format->cfFormat == effect_ ? sizeof(DWORD) :
            offsetof(FILEGROUPDESCRIPTORW, fgd) + sizeof(FILEDESCRIPTORW) * offer_.entry_size();
        HGLOBAL memory = GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, bytes);
        if (!memory) return E_OUTOFMEMORY;
        void* data = GlobalLock(memory);
        if (!data) { GlobalFree(memory); return E_OUTOFMEMORY; }
        if (format->cfFormat == effect_) *static_cast<DWORD*>(data) = DROPEFFECT_COPY;
        else
        {
            auto* group = static_cast<FILEGROUPDESCRIPTORW*>(data);
            group->cItems = static_cast<UINT>(offer_.entry_size());
            for (int i = 0; i < offer_.entry_size(); ++i)
            {
                const auto& entry = offer_.entry(i);
                auto& descriptor = group->fgd[i];
                descriptor.dwFlags = FD_ATTRIBUTES | FD_UNICODE;
                if (!entry.directory()) descriptor.dwFlags |= FD_FILESIZE | FD_PROGRESSUI;
                descriptor.dwFileAttributes = entry.directory() ? FILE_ATTRIBUTE_DIRECTORY : FILE_ATTRIBUTE_NORMAL;
                descriptor.nFileSizeHigh = static_cast<DWORD>(entry.size() >> 32);
                descriptor.nFileSizeLow = static_cast<DWORD>(entry.size());
                auto name = base::wideFromUtf8(entry.name());
                if (name.empty() || name.size() >= MAX_PATH)
                { GlobalUnlock(memory); GlobalFree(memory); return DV_E_FORMATETC; }
                memcpy(descriptor.cFileName, name.c_str(), (name.size() + 1) * sizeof(wchar_t));
            }
        }
        GlobalUnlock(memory);
        medium->tymed = TYMED_HGLOBAL;
        medium->hGlobal = memory;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetDataHere(FORMATETC*, STGMEDIUM*) override { return DATA_E_FORMATETC; }
    HRESULT STDMETHODCALLTYPE GetCanonicalFormatEtc(FORMATETC*, FORMATETC* out) override
    { if (out) out->ptd = nullptr; return DATA_S_SAMEFORMATETC; }
    HRESULT STDMETHODCALLTYPE SetData(FORMATETC*, STGMEDIUM*, BOOL) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE EnumFormatEtc(DWORD direction, IEnumFORMATETC** out) override
    {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (direction != DATADIR_GET) return E_NOTIMPL;
        FORMATETC formats[] = {{descriptor_, nullptr, DVASPECT_CONTENT, -1, TYMED_HGLOBAL},
                              {contents_, nullptr, DVASPECT_CONTENT, -1, TYMED_ISTREAM},
                              {effect_, nullptr, DVASPECT_CONTENT, -1, TYMED_HGLOBAL}};
        return SHCreateStdEnumFmtEtc(3, formats, out);
    }
    HRESULT STDMETHODCALLTYPE DAdvise(FORMATETC*, DWORD, IAdviseSink*, DWORD*) override { return OLE_E_ADVISENOTSUPPORTED; }
    HRESULT STDMETHODCALLTYPE DUnadvise(DWORD) override { return OLE_E_ADVISENOTSUPPORTED; }
    HRESULT STDMETHODCALLTYPE EnumDAdvise(IEnumSTATDATA**) override { return OLE_E_ADVISENOTSUPPORTED; }
private:
    std::atomic<ULONG> refs_{1};
    std::shared_ptr<ClipboardFileControl> control_;
    proto::ClipboardFile offer_;
    CLIPFORMAT descriptor_, contents_, effect_;
};

bool appendPath(const std::filesystem::path& path, const std::filesystem::path& relative,
                proto::ClipboardFile* offer, std::vector<std::filesystem::path>* paths)
{
    const std::string name = base::utf8FromWide(relative.native());
    if (offer->entry_size() >= kClipboardMaxEntries || name.empty() || name.size() >= 260) return false;
    const DWORD attributes = GetFileAttributesW(path.c_str());
    // Do not traverse junctions/symlinks or copy device/alternate stream paths.
    if (attributes == INVALID_FILE_ATTRIBUTES || (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) return false;
    std::error_code ec;
    auto canonical = std::filesystem::canonical(path, ec);
    if (ec) return false;
    auto* entry = offer->add_entry();
    entry->set_name(name);
    const bool directory = (attributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
    entry->set_directory(directory);
    if (!directory)
    {
        if (!std::filesystem::is_regular_file(path, ec) || ec) return false;
        auto size = std::filesystem::file_size(path, ec);
        if (ec) return false;
        entry->set_size(size);
    }
    paths->push_back(std::move(canonical));
    if (directory)
    {
        std::filesystem::directory_iterator it(path, ec), end;
        if (ec) return false;
        while (it != end)
        {
            if (!appendPath(it->path(), relative / it->path().filename(), offer, paths)) return false;
            it.increment(ec);
            if (ec) return false;
        }
    }
    return true;
}
} // namespace

ClipboardFilesWin::ClipboardFilesWin(ClipboardFileTransfer::Send send)
    : control_(std::make_shared<ClipboardFileControl>())
{
    ole_initialized_ = SUCCEEDED(OleInitialize(nullptr));
    transfer_ = std::make_unique<ClipboardFileTransfer>(std::move(send),
        [this](const proto::ClipboardFile& offer) { setOffer(offer); });
    control_->transfer = transfer_.get();
}
ClipboardFilesWin::~ClipboardFilesWin()
{
    resetRemote();
    control_->transfer = nullptr;
    transfer_.reset();
    if (ole_initialized_) OleUninitialize();
}
void ClipboardFilesWin::resetRemote()
{
    transfer_->clearRemote();
    if (object_)
    {
        if (OleIsCurrentClipboard(object_) == S_OK) OleSetClipboard(nullptr);
        object_->Release();
        object_ = nullptr;
    }
}
void ClipboardFilesWin::setOffer(const proto::ClipboardFile& offer)
{
    // The protocol already invalidated old read states. Do not clear the new offer.
    if (object_)
    {
        if (OleIsCurrentClipboard(object_) == S_OK) OleSetClipboard(nullptr);
        object_->Release(); object_ = nullptr;
    }
    if (!ole_initialized_ || !offer.entry_size()) return;
    // Reject names invalid in UTF-8, and case collisions using Windows' Unicode rules.
    std::vector<std::wstring> names;
    for (const auto& entry : offer.entry())
    {
        std::wstring name;
        if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, entry.name().data(),
                                 static_cast<int>(entry.name().size()), nullptr, 0) ||
            !base::utf8ToWide(entry.name(), &name) || name.empty() || name.size() >= MAX_PATH) return;
        for (const auto& previous : names)
            if (CompareStringOrdinal(name.c_str(), -1, previous.c_str(), -1, TRUE) == CSTR_EQUAL) return;
        names.push_back(std::move(name));
    }
    auto* object = new RemoteFileObject(control_, offer);
    if (FAILED(OleSetClipboard(object))) { object->Release(); return; }
    object_ = object;
    sequence_ = GetClipboardSequenceNumber();
}
void ClipboardFilesWin::receive(const proto::ClipboardFile& message)
{
    if (!ole_initialized_) return;
    transfer_->receive(message);
    if (message.type() == proto::ClipboardFile::HELLO)
    {
        // Re-read a pre-existing local Ctrl+C selection when the session becomes ready.
        sequence_ = 0;
        onClipboardUpdate(nullptr);
    }
}
bool ClipboardFilesWin::onClipboardUpdate(HWND window)
{
    if (object_ && OleIsCurrentClipboard(object_) == S_OK) return true;
    if (object_) resetRemote();
    if (!ole_initialized_ || !transfer_->enabled()) return false;
    const DWORD sequence = GetClipboardSequenceNumber();
    const bool files = IsClipboardFormatAvailable(CF_HDROP) != FALSE;
    if (sequence == sequence_) return files;
    sequence_ = sequence;
    transfer_->clearLocal();
    if (!files) return false;
    std::vector<std::filesystem::path> selected;
    {
        base::win::ScopedClipboard clipboard;
        if (!clipboard.init(window)) { sequence_ = 0; return true; }
        HDROP drop = static_cast<HDROP>(clipboard.data(CF_HDROP));
        if (!drop) return true;
        const UINT count = DragQueryFileW(drop, 0xFFFFFFFF, nullptr, 0);
        if (!count || count > static_cast<UINT>(kClipboardMaxEntries)) return true;
        for (UINT i = 0; i < count; ++i)
        {
            const UINT length = DragQueryFileW(drop, i, nullptr, 0);
            if (!length || length > 32767) return true;
            std::wstring path(length + 1, L'\0');
            if (DragQueryFileW(drop, i, path.data(), length + 1) != length) return true;
            path.resize(length);
            selected.emplace_back(path);
        }
    }
    proto::ClipboardFile offer;
    std::vector<std::filesystem::path> paths;
    for (const auto& path : selected)
        if (!appendPath(path, path.filename(), &offer, &paths)) return true;
    transfer_->publish(std::move(offer), std::move(paths));
    return true;
}
} // namespace common
