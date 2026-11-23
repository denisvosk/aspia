// Aspia 2.7 community continuation, 2026. GPL-3.0-or-later.
#include "common/clipboard.h"
#include <gtest/gtest.h>
#include <zstd.h>

namespace common {
namespace {
class MemoryClipboard final : public Clipboard, public Clipboard::Delegate {
public:
    MemoryClipboard() { start(this); }
    void capture(const std::string& text, const proto::ClipboardEvent& formats = {}) { onData(text, formats); }
    void onClipboardEvent(const proto::ClipboardEvent& event) override { sent = event; ++sends; }
    std::string received_text;
    proto::ClipboardEvent sent, received;
    int writes = 0, sends = 0;
private:
    void init() override {}
    void setData(const std::string& text) override { received_text = text; received.Clear(); ++writes; }
    void setContent(const std::string& text, const proto::ClipboardEvent& formats) override
    { received_text = text; received = formats; ++writes; }
};
void add(proto::ClipboardEvent& content, proto::ClipboardEvent::Format::Type type, const std::string& data)
{
    auto* format = content.add_format(); format->set_type(type); format->set_data(data);
}
TEST(ClipboardContent, AtomicRichBundleAndLegacyTextFallback)
{
    MemoryClipboard source, target, legacy;
    proto::ClipboardEvent content;
    const std::string rtf = "{\\rtf1\\b Bold\\b0 " + std::string(8192, 'x') + "}";
    add(content, proto::ClipboardEvent::Format::RTF, rtf);
    add(content, proto::ClipboardEvent::Format::HTML, "CF_HTML bytes including head styles");
    add(content, proto::ClipboardEvent::Format::PNG, std::string("PNG\0data", 8));
    source.capture("Bold text", content);
    ASSERT_EQ(1, source.sends); ASSERT_EQ(3, source.sent.format_size());
    EXPECT_TRUE(source.sent.format(0).compressed());
    target.injectClipboardEvent(source.sent);
    EXPECT_EQ(1, target.writes); EXPECT_EQ("Bold text", target.received_text);
    EXPECT_EQ(content.SerializeAsString(), target.received.SerializeAsString());
    // Both negotiated fallback paths remove optional formats, leaving old fields unchanged.
    proto::ClipboardEvent fallback = source.sent; fallback.clear_format();
    legacy.injectClipboardEvent(fallback);
    EXPECT_EQ("Bold text", legacy.received_text); EXPECT_EQ(0, legacy.received.format_size());
    target.capture("Bold text", content); EXPECT_EQ(0, target.sends); // No echo.
    content.mutable_format(0)->set_data("{\\rtf1\\i Bold text}");
    target.capture("Bold text", content); EXPECT_EQ(1, target.sends); // Same text, different style.
}
TEST(ClipboardContent, InvalidBundleLeavesPreviousClipboardUntouched)
{
    MemoryClipboard target;
    proto::ClipboardEvent event; event.set_mime_type("text/plain; charset=UTF-8"); event.set_data("original");
    target.injectClipboardEvent(event); ASSERT_EQ(1, target.writes);
    add(event, proto::ClipboardEvent::Format::RTF, "not a compressed stream");
    event.mutable_format(0)->set_compressed(true); target.injectClipboardEvent(event);
    EXPECT_EQ(1, target.writes); EXPECT_EQ("original", target.received_text);
    event.mutable_format(0)->set_compressed(false);
    add(event, proto::ClipboardEvent::Format::RTF, "duplicate format"); target.injectClipboardEvent(event);
    EXPECT_EQ(1, target.writes);
}
TEST(ClipboardContent, DecompressionBudgetRejectsOversizedPayload)
{
    MemoryClipboard target;
    const std::string data(kClipboardContentDecodedLimit + 1, 'x');
    std::string packed(ZSTD_compressBound(data.size()), '\0');
    size_t size = ZSTD_compress(packed.data(), packed.size(), data.data(), data.size(), 1);
    ASSERT_FALSE(ZSTD_isError(size)); packed.resize(size);
    proto::ClipboardEvent event; event.set_mime_type("text/plain; charset=UTF-8");
    add(event, proto::ClipboardEvent::Format::RTF, packed); event.mutable_format(0)->set_compressed(true);
    target.injectClipboardEvent(event); EXPECT_EQ(0, target.writes);
    event.clear_format(); event.set_mime_type("text/plain; charset=UTF-8; compression=ZSTD"); event.set_data(packed);
    target.injectClipboardEvent(event); EXPECT_EQ(0, target.writes);
}
TEST(ClipboardContent, ImageOnlyAndPlainTextRemainSeparateOffers)
{
    MemoryClipboard source, target;
    proto::ClipboardEvent image;
    add(image, proto::ClipboardEvent::Format::PNG, "PNG bytes");
    source.capture("", image); ASSERT_EQ(1, source.sends);
    target.injectClipboardEvent(source.sent);
    EXPECT_EQ(1, target.received.format_size()); EXPECT_TRUE(target.received_text.empty());
    source.capture("plain text"); target.injectClipboardEvent(source.sent);
    EXPECT_EQ("plain text", target.received_text); EXPECT_EQ(0, target.received.format_size());
}
} // namespace
} // namespace common
