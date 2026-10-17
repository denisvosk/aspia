// Aspia 2.7 community continuation, 2026. GPL-3.0-or-later.
#include "common/clipboard_file_transfer.h"
#include <gtest/gtest.h>
#include <fstream>
#include <queue>
#include "base/crypto/random.h"

namespace common {
namespace {
proto::ClipboardFile offerOf(std::string name, uint64_t size = 0)
{
    proto::ClipboardFile offer;
    offer.set_type(proto::ClipboardFile::OFFER); offer.set_offer_id(1);
    auto* entry = offer.add_entry(); entry->set_name(std::move(name)); entry->set_size(size);
    return offer;
}
TEST(ClipboardFiles, ValidatesNamesAndHierarchy)
{
    EXPECT_TRUE(validClipboardOffer(offerOf("report.txt")));
    EXPECT_TRUE(validClipboardOffer(offerOf("\xD0\xA4\xD0\xB0\xD0\xB9\xD0\xBB.txt")));
    for (const char* name : {"", "..", ".", "..\\secret", "\\server\\file", "C:\\file",
                            "x:stream", "a/b", "NUL.txt", "COM1", "CON .txt", "CONOUT$", "LPT\xc2\xb9", "x.", "x ", "a\\", "a\\b"})
        EXPECT_FALSE(validClipboardOffer(offerOf(name))) << name;
    auto offer = offerOf("folder"); offer.mutable_entry(0)->set_directory(true);
    offer.add_entry()->set_name("folder\\file.txt");
    EXPECT_TRUE(validClipboardOffer(offer));
    offer.add_entry()->set_name("FOLDER\\FILE.TXT");
    EXPECT_FALSE(validClipboardOffer(offer));
}
TEST(ClipboardFiles, RejectsMalformedAndOversizedEnvelope)
{
    proto::ClipboardEvent event; proto::ClipboardFile message;
    event.set_mime_type(kFileClipboardMime); event.set_data("\xff");
    EXPECT_FALSE(parseFileClipboard(event, &message));
    event.set_data(std::string(kClipboardMaxMessage + 1, 'x'));
    EXPECT_FALSE(parseFileClipboard(event, &message));
    auto offer = offerOf("f");
    for (int i = 0; i < kClipboardMaxEntries; ++i) offer.add_entry()->set_name(std::to_string(i));
    EXPECT_FALSE(validClipboardOffer(offer));
}
class TransferTest : public testing::Test {
protected:
    std::filesystem::path directory;
    std::queue<proto::ClipboardEvent> to_source, to_target;
    proto::ClipboardFile received;
    ClipboardFileTransfer source{
        [this](const auto& event) { to_target.push(event); }, [](const auto&) {}};
    ClipboardFileTransfer target{
        [this](const auto& event) { to_source.push(event); }, [this](const auto& offer) { received = offer; }};
    void SetUp() override
    {
        directory = std::filesystem::temp_directory_path() / ("aspia-clipboard-test-" + std::to_string(base::Random::number64()));
        std::filesystem::create_directory(directory);
        proto::ClipboardFile hello; hello.set_type(proto::ClipboardFile::HELLO);
        source.receive(hello); target.receive(hello);
    }
    void TearDown() override { std::filesystem::remove_all(directory); }
    void pump()
    {
        for (int i = 0; i < 100 && (!to_source.empty() || !to_target.empty()); ++i)
        {
            if (!to_source.empty())
            { proto::ClipboardFile message; ASSERT_TRUE(parseFileClipboard(to_source.front(), &message));
              to_source.pop(); source.receive(message); }
            if (!to_target.empty())
            { proto::ClipboardFile message; ASSERT_TRUE(parseFileClipboard(to_target.front(), &message));
              to_target.pop(); target.receive(message); }
        }
    }
    void publish(const std::string& bytes)
    {
        auto path = directory / "test.bin";
        { std::ofstream file(path, std::ios::binary); file.write(bytes.data(), bytes.size()); }
        source.publish(offerOf("test.bin", bytes.size()), {std::filesystem::canonical(path)});
        pump();
    }
};
TEST_F(TransferTest, CopiesZeroAndMultipleChunksByteForByte)
{
    for (size_t size : {size_t(0), size_t(1), size_t(65536), size_t(262144), size_t(1048593)})
    {
        std::string input(size, '\0');
        for (size_t i = 0; i < size; ++i) input[i] = static_cast<char>(i % 251);
        publish(input);
        auto state = target.open(received, 0); ASSERT_TRUE(state);
        std::string output;
        do
        {
            target.request(state); pump(); ASSERT_FALSE(state->failed);
            ASSERT_LE(state->data.size(), kClipboardChunkSize);
            output += state->data; state->data.clear();
        } while (!state->last);
        EXPECT_EQ(input, output);
        target.close(state);
    }
}
TEST_F(TransferTest, RejectsUnknownPeerAndInvalidFileIndex)
{
    publish("data");
    proto::ClipboardFile request;
    request.set_type(proto::ClipboardFile::READ); request.set_offer_id(received.offer_id());
    request.set_transfer_id(1); request.set_peer_id(999);
    source.receive(request); EXPECT_TRUE(to_target.empty());
    request.set_peer_id(0); request.set_index(100);
    source.receive(request); ASSERT_FALSE(to_target.empty());
    proto::ClipboardFile response; ASSERT_TRUE(parseFileClipboard(to_target.front(), &response));
    EXPECT_EQ(response.type(), proto::ClipboardFile::ERROR);
}
TEST_F(TransferTest, ChangedSourceFailsWithoutPartialSuccess)
{
    publish("original");
    std::ofstream(directory / "test.bin", std::ios::trunc) << "changed size";
    auto state = target.open(received, 0); ASSERT_TRUE(state);
    target.request(state); pump(); EXPECT_TRUE(state->failed);
}
TEST_F(TransferTest, DisconnectAndNewOfferInvalidateOldStreams)
{
    publish("first"); auto state = target.open(received, 0); ASSERT_TRUE(state);
    publish("second"); EXPECT_TRUE(state->failed);
    EXPECT_FALSE(target.open(offerOf("test.bin"), 0));
    auto current = target.open(received, 0); ASSERT_TRUE(current);
    proto::ClipboardFile disconnect; disconnect.set_type(proto::ClipboardFile::DISCONNECT);
    target.receive(disconnect); EXPECT_TRUE(current->failed); EXPECT_FALSE(target.enabled());
}
TEST_F(TransferTest, RejectsTruncatedAndWrongPeerData)
{
    publish("123456"); auto state = target.open(received, 0); ASSERT_TRUE(state);
    target.request(state);
    proto::ClipboardFile message;
    message.set_type(proto::ClipboardFile::DATA); message.set_transfer_id(state->id);
    message.set_offer_id(state->offer); message.set_index(state->index);
    message.set_peer_id(999); message.mutable_packet()->set_data("bad");
    target.receive(message); EXPECT_TRUE(state->waiting); EXPECT_FALSE(state->failed);
    message.set_peer_id(0); message.mutable_packet()->set_flags(proto::FilePacket::FIRST_PACKET | proto::FilePacket::LAST_PACKET);
    message.mutable_packet()->set_file_size(6);
    target.receive(message); EXPECT_TRUE(state->failed);
}
TEST_F(TransferTest, BoundsOpenStreams)
{
    publish("data"); std::vector<std::shared_ptr<ClipboardFileTransfer::ReadState>> states;
    for (int i = 0; i < 8; ++i) { auto state = target.open(received, 0); ASSERT_TRUE(state); states.push_back(state); }
    EXPECT_FALSE(target.open(received, 0));
    target.close(states.front()); EXPECT_TRUE(target.open(received, 0));
}
} // namespace
} // namespace common
