// Aspia 2.7 community continuation, 2026. GPL-3.0-or-later.
#include "common/clipboard_file_transfer.h"
#include "base/crypto/random.h"
#include <algorithm>
#include <cctype>
#include <limits>

namespace common {
bool parseFileClipboard(const proto::ClipboardEvent& event, proto::ClipboardFile* message)
{
    return event.mime_type() == kFileClipboardMime && event.data().size() <= kClipboardMaxMessage &&
        message->ParseFromString(event.data()) && message->type() != proto::ClipboardFile::UNKNOWN;
}

proto::ClipboardEvent fileClipboardEvent(const proto::ClipboardFile& message)
{
    proto::ClipboardEvent event;
    event.set_mime_type(kFileClipboardMime);
    message.SerializeToString(event.mutable_data());
    return event;
}

bool validClipboardOffer(const proto::ClipboardFile& message)
{
    if (message.type() != proto::ClipboardFile::OFFER || !message.offer_id() ||
        message.entry_size() > kClipboardMaxEntries || message.ByteSizeLong() > kClipboardMaxMessage)
        return false;
    std::map<std::string, bool> names;
    for (const auto& entry : message.entry())
    {
        const auto& name = entry.name();
        if (name.empty() || name.size() >= 260 || name.front() == '\\' ||
            entry.size() > static_cast<uint64_t>(std::numeric_limits<int64_t>::max()) ||
            (entry.directory() && entry.size()))
            return false;
        std::string folded;
        for (unsigned char c : name)
        {
            if (c < 32 || c == '/' || c == ':' || c == '*' || c == '?' || c == '"' ||
                c == '<' || c == '>' || c == '|')
                return false;
            folded += c < 128 ? static_cast<char>(std::tolower(c)) : static_cast<char>(c);
        }
        size_t start = 0;
        while (start < folded.size())
        {
            size_t end = folded.find('\\', start);
            if (end == std::string::npos) end = folded.size();
            std::string part = folded.substr(start, end - start);
            if (part.empty() || part.back() == '.' || part.back() == ' ') return false;
            std::string stem = part.substr(0, part.find('.'));
            while (!stem.empty() && stem.back() == ' ') stem.pop_back();
            if (stem == "con" || stem == "prn" || stem == "aux" || stem == "nul" ||
                stem == "conin$" || stem == "conout$" ||
                (stem.size() == 5 && (stem.substr(0, 3) == "com" || stem.substr(0, 3) == "lpt") &&
                 (stem.substr(3) == "\xc2\xb9" || stem.substr(3) == "\xc2\xb2" || stem.substr(3) == "\xc2\xb3")) ||
                (stem.size() == 4 && (stem.substr(0, 3) == "com" || stem.substr(0, 3) == "lpt") &&
                 stem[3] >= '0' && stem[3] <= '9')) return false;
            if (end != folded.size())
            {
                auto parent = names.find(folded.substr(0, end));
                if (parent == names.end() || !parent->second) return false;
            }
            start = end + 1;
        }
        if (folded.back() == '\\' || !names.emplace(folded, entry.directory()).second) return false;
    }
    return true;
}

ClipboardFileTransfer::ClipboardFileTransfer(Send send, Offer offer)
    : send_(std::move(send)), offer_(std::move(offer)) {}
ClipboardFileTransfer::~ClipboardFileTransfer() { clearRemote(false); }
void ClipboardFileTransfer::send(proto::ClipboardFile message) { send_(fileClipboardEvent(message)); }

void ClipboardFileTransfer::clearRemote(bool notify_peer)
{
    std::vector<std::shared_ptr<ReadState>> states;
    for (auto& reader : readers_)
        if (auto state = reader.second.lock()) states.push_back(state);
    readers_.clear();
    remote_.Clear();
    for (auto& state : states)
    {
        if (notify_peer) close(state);
        else { state->failed = true; state->waiting = false; }
    }
}
void ClipboardFileTransfer::clearLocal()
{
    writers_.clear();
    paths_.clear();
    local_.Clear();
}
void ClipboardFileTransfer::publish(proto::ClipboardFile offer, std::vector<std::filesystem::path> paths)
{
    offer.set_type(proto::ClipboardFile::OFFER);
    offer.set_offer_id(base::Random::number64() | 1);
    if (!validClipboardOffer(offer) || paths.size() != static_cast<size_t>(offer.entry_size())) return;
    clearRemote();
    clearLocal();
    local_ = std::move(offer);
    paths_ = std::move(paths);
    for (auto peer : peers_) { auto message = local_; message.set_peer_id(peer); send(std::move(message)); }
}
void ClipboardFileTransfer::disconnect(uint32_t peer)
{
    peers_.erase(peer);
    for (auto it = writers_.begin(); it != writers_.end();)
        if (it->first.first == peer) it = writers_.erase(it); else ++it;
    if (remote_.offer_id() && remote_.peer_id() == peer) { clearRemote(); offer_(remote_); }
}
void ClipboardFileTransfer::receive(const proto::ClipboardFile& message)
{
    if (message.type() == proto::ClipboardFile::HELLO)
    {
        // Bounded as well as authenticated by the service's session gate.
        if (peers_.size() >= 64 && !peers_.count(message.peer_id())) return;
        peers_.insert(message.peer_id());
        if (local_.offer_id()) { auto offer = local_; offer.set_peer_id(message.peer_id()); send(offer); }
        return;
    }
    if (message.type() == proto::ClipboardFile::DISCONNECT) { disconnect(message.peer_id()); return; }
    if (!peers_.count(message.peer_id())) return;
    switch (message.type())
    {
        case proto::ClipboardFile::OFFER:
            if (!validClipboardOffer(message)) return;
            clearRemote();
            clearLocal();
            remote_ = message;
            offer_(remote_);
            break;
        case proto::ClipboardFile::READ: read(message); break;
        case proto::ClipboardFile::DATA: case proto::ClipboardFile::ERROR: data(message); break;
        case proto::ClipboardFile::CANCEL:
            writers_.erase({message.peer_id(), message.transfer_id()}); break;
        default: break;
    }
}

std::shared_ptr<ClipboardFileTransfer::ReadState> ClipboardFileTransfer::open(
    const proto::ClipboardFile& offer, uint32_t index)
{
    if (offer.offer_id() != remote_.offer_id() || offer.peer_id() != remote_.peer_id() ||
        index >= static_cast<uint32_t>(offer.entry_size()) || offer.entry(static_cast<int>(index)).directory())
        return nullptr;
    for (auto it = readers_.begin(); it != readers_.end();)
        if (it->second.expired()) it = readers_.erase(it); else ++it;
    if (readers_.size() >= 8) return nullptr;
    auto state = std::make_shared<ReadState>();
    state->id = ++next_id_;
    state->peer = offer.peer_id();
    state->offer = offer.offer_id();
    state->index = index;
    state->size = offer.entry(static_cast<int>(index)).size();
    readers_[state->id] = state;
    return state;
}
void ClipboardFileTransfer::request(const std::shared_ptr<ReadState>& state)
{
    if (state->failed || state->last || state->waiting || !state->data.empty()) return;
    proto::ClipboardFile message;
    message.set_type(proto::ClipboardFile::READ);
    message.set_peer_id(state->peer);
    message.set_offer_id(state->offer);
    message.set_transfer_id(state->id);
    message.set_index(state->index);
    message.set_offset(state->offset);
    state->waiting = true;
    send(std::move(message));
}
void ClipboardFileTransfer::close(const std::shared_ptr<ReadState>& state)
{
    if (!state) return;
    readers_.erase(state->id);
    if (!state->last && peers_.count(state->peer))
    {
        proto::ClipboardFile message;
        message.set_type(proto::ClipboardFile::CANCEL);
        message.set_peer_id(state->peer);
        message.set_transfer_id(state->id);
        send(std::move(message));
    }
    state->failed = true;
    state->waiting = false;
}
void ClipboardFileTransfer::data(const proto::ClipboardFile& message)
{
    auto it = readers_.find(message.transfer_id());
    if (it == readers_.end()) return;
    auto state = it->second.lock();
    if (!state || state->peer != message.peer_id() || state->offer != message.offer_id() ||
        state->index != message.index() || !state->waiting || state->offset != message.offset()) return;
    state->waiting = false;
    const auto& packet = message.packet();
    const bool first = (packet.flags() & proto::FilePacket::FIRST_PACKET) != 0;
    const bool last = (packet.flags() & proto::FilePacket::LAST_PACKET) != 0;
    const auto size = packet.data().size();
    if (message.type() == proto::ClipboardFile::ERROR || size > kClipboardChunkSize ||
        size > state->size - state->offset || first != (state->offset == 0) ||
        (first && packet.file_size() != state->size) ||
        last != (state->offset + size == state->size) || (!size && !last))
    { state->failed = true; return; }
    state->data = packet.data();
    state->offset += size;
    state->last = last;
}
void ClipboardFileTransfer::read(const proto::ClipboardFile& request)
{
    proto::ClipboardFile response;
    response.set_type(proto::ClipboardFile::ERROR);
    response.set_peer_id(request.peer_id());
    response.set_offer_id(request.offer_id());
    response.set_transfer_id(request.transfer_id());
    response.set_index(request.index());
    response.set_offset(request.offset());
    const Key key(request.peer_id(), request.transfer_id());
    const auto now = Clock::now();
    for (auto it = writers_.begin(); it != writers_.end();)
        if (now - it->second.used > std::chrono::seconds(60)) it = writers_.erase(it); else ++it;
    auto fail = [&] { writers_.erase(key); send(response); };
    if (!request.transfer_id() || request.offer_id() != local_.offer_id() ||
        request.index() >= static_cast<uint32_t>(local_.entry_size())) { fail(); return; }
    const auto& entry = local_.entry(static_cast<int>(request.index()));
    if (entry.directory() || request.offset() > entry.size()) { fail(); return; }
    auto it = writers_.find(key);
    if (it == writers_.end())
    {
        size_t count = 0;
        for (const auto& writer : writers_) if (writer.first.first == request.peer_id()) ++count;
        if (request.offset() || count >= 8 || writers_.size() >= 64) { fail(); return; }
        const auto& path = paths_[request.index()];
        std::error_code ec;
        // Refuse renamed/replaced directory links or files which changed since Ctrl+C.
        auto canonical = std::filesystem::canonical(path, ec);
        if (ec || canonical != path || std::filesystem::file_size(path, ec) != entry.size() || ec)
        { fail(); return; }
        auto file = FilePacketizer::create(path);
        if (!file) { fail(); return; }
        Writer writer;
        writer.file = std::move(file);
        writer.offer = request.offer_id();
        writer.index = request.index();
        writer.used = now;
        it = writers_.emplace(key, std::move(writer)).first;
    }
    auto& writer = it->second;
    if (writer.offset != request.offset() || writer.offer != request.offer_id() ||
        writer.index != request.index()) { fail(); return; }
    proto::FilePacket aggregate;
    for (int i = 0; i < 4; ++i)
    {
        proto::FilePacketRequest next;
        auto packet = writer.file->readNextPacket(next);
        if (!packet) { fail(); return; }
        if (packet->flags() & proto::FilePacket::FIRST_PACKET)
        {
            if (packet->file_size() != entry.size()) { fail(); return; }
            aggregate.set_file_size(packet->file_size());
        }
        aggregate.set_flags(aggregate.flags() | packet->flags());
        aggregate.mutable_data()->append(packet->data());
        if (packet->flags() & proto::FilePacket::LAST_PACKET) break;
    }
    writer.offset += aggregate.data().size();
    writer.used = now;
    response.set_type(proto::ClipboardFile::DATA);
    response.mutable_packet()->Swap(&aggregate);
    if (response.packet().flags() & proto::FilePacket::LAST_PACKET) writers_.erase(it);
    send(std::move(response));
}
} // namespace common
