// Aspia 2.7 community continuation, 2026. GPL-3.0-or-later.
#ifndef COMMON_CLIPBOARD_FILE_TRANSFER_H
#define COMMON_CLIPBOARD_FILE_TRANSFER_H

#include "common/file_packetizer.h"
#include "proto/clipboard_file.pb.h"
#include "proto/desktop.pb.h"
#include <chrono>
#include <functional>
#include <map>
#include <set>
#include <vector>

namespace common {
inline constexpr char kFileClipboardMime[] = "application/x-aspia-file-clipboard-v1";
inline constexpr char kFileClipboardCapability[] = "file_clipboard_v1";
inline constexpr size_t kClipboardMaxMessage = 2 * 1024 * 1024;
inline constexpr size_t kClipboardChunkSize = 256 * 1024;
inline constexpr int kClipboardMaxEntries = 4096;

bool parseFileClipboard(const proto::ClipboardEvent& event, proto::ClipboardFile* message);
proto::ClipboardEvent fileClipboardEvent(const proto::ClipboardFile& message);
bool validClipboardOffer(const proto::ClipboardFile& message);

// Single-threaded protocol engine. Paths are captured locally, never received from
// a peer. The wire contains indices into that snapshot, not filesystem commands.
class ClipboardFileTransfer {
public:
    using Send = std::function<void(const proto::ClipboardEvent&)>;
    using Offer = std::function<void(const proto::ClipboardFile&)>;
    struct ReadState {
        uint32_t peer = 0;
        uint64_t offer = 0, id = 0, offset = 0, size = 0;
        uint32_t index = 0;
        bool waiting = false, failed = false, last = false;
        std::string data;
    };
    ClipboardFileTransfer(Send send, Offer offer);
    ~ClipboardFileTransfer();
    void receive(const proto::ClipboardFile& message);
    void publish(proto::ClipboardFile offer, std::vector<std::filesystem::path> paths);
    void clearLocal();
    void clearRemote(bool notify_peer = true);
    bool enabled() const { return !peers_.empty(); }
    std::shared_ptr<ReadState> open(const proto::ClipboardFile& offer, uint32_t index);
    void request(const std::shared_ptr<ReadState>& state);
    void close(const std::shared_ptr<ReadState>& state);
private:
    using Clock = std::chrono::steady_clock;
    using Key = std::pair<uint32_t, uint64_t>;
    struct Writer {
        std::unique_ptr<FilePacketizer> file;
        uint64_t offer = 0, offset = 0;
        uint32_t index = 0;
        Clock::time_point used;
    };
    void send(proto::ClipboardFile message);
    void read(const proto::ClipboardFile& message);
    void data(const proto::ClipboardFile& message);
    void disconnect(uint32_t peer);
    Send send_;
    Offer offer_;
    std::set<uint32_t> peers_;
    proto::ClipboardFile local_, remote_;
    std::vector<std::filesystem::path> paths_;
    std::map<Key, Writer> writers_;
    std::map<uint64_t, std::weak_ptr<ReadState>> readers_;
    uint64_t next_id_ = 0;
};
} // namespace common
#endif
