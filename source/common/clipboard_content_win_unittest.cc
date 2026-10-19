// Aspia 2.7 community continuation, 2026. GPL-3.0-or-later.
#include "common/clipboard_content_win.h"
#include "base/win/scoped_clipboard.h"
#include <gtest/gtest.h>
#include <cstdio>
#include <cstring>

namespace common {
namespace {
class ClipboardContentWinTest : public testing::Test {
protected:
    HWND window = nullptr;
    void SetUp() override
    {
        window = CreateWindowExW(0, L"STATIC", L"Aspia clipboard test", 0, 0, 0, 0, 0,
                                 HWND_MESSAGE, nullptr, GetModuleHandleW(nullptr), nullptr);
        ASSERT_NE(nullptr, window);
    }
    void TearDown() override
    {
        { base::win::ScopedClipboard clipboard; if (clipboard.init(window)) clipboard.empty(); }
        if (window) DestroyWindow(window);
    }
    static std::string html(const std::string& fragment)
    {
        const char* layout = "Version:0.9\r\nStartHTML:%010d\r\nEndHTML:%010d\r\nStartFragment:%010d\r\nEndFragment:%010d\r\n";
        char header[160]{}; int size = snprintf(header, sizeof(header), layout, 0, 0, 0, 0);
        snprintf(header, sizeof(header), layout, size, size + static_cast<int>(fragment.size()),
                 size, size + static_cast<int>(fragment.size()));
        return std::string(header) + fragment;
    }
};
TEST_F(ClipboardContentWinTest, TextRtfHtmlAreInstalledTogether)
{
    proto::ClipboardEvent content;
    auto* rtf = content.add_format(); rtf->set_type(proto::ClipboardEvent::Format::RTF);
    rtf->set_data("{\\rtf1\\b Bold\\b0 \\i italic\\i0}");
    auto* markup = content.add_format(); markup->set_type(proto::ClipboardEvent::Format::HTML);
    markup->set_data(html("<html><head><style>b{color:red}</style></head><body><b>Bold</b></body></html>"));
    ASSERT_TRUE(writeClipboardContentWin(window, "Bold\nitalic", content));
    EXPECT_TRUE(IsClipboardFormatAvailable(CF_UNICODETEXT));
    EXPECT_TRUE(IsClipboardFormatAvailable(RegisterClipboardFormatW(L"Rich Text Format")));
    EXPECT_TRUE(IsClipboardFormatAvailable(RegisterClipboardFormatW(L"HTML Format")));
    std::string text; proto::ClipboardEvent captured;
    ASSERT_TRUE(readClipboardContentWin(window, &text, &captured));
    EXPECT_EQ("Bold\nitalic", text); EXPECT_EQ(content.SerializeAsString(), captured.SerializeAsString());
    // A later plain-text copy clears stale rich formats.
    ASSERT_TRUE(writeClipboardContentWin(window, "plain", {}));
    EXPECT_FALSE(IsClipboardFormatAvailable(RegisterClipboardFormatW(L"Rich Text Format")));
}
TEST_F(ClipboardContentWinTest, EmbeddedRtfPictureWinsOverLocalHtmlImage)
{
    proto::ClipboardEvent content;
    auto* rtf = content.add_format(); rtf->set_type(proto::ClipboardEvent::Format::RTF);
    rtf->set_data(std::string("{\\rtf1{\\pict\\bin3 ") + std::string("a\0b", 3) + "}}");
    auto* markup = content.add_format(); markup->set_type(proto::ClipboardEvent::Format::HTML);
    markup->set_data(html("<img src=\"file:///C:/Temp/word/image001.png\">"));
    ASSERT_TRUE(writeClipboardContentWin(window, "picture", content));
    std::string text; proto::ClipboardEvent captured;
    ASSERT_TRUE(readClipboardContentWin(window, &text, &captured));
    ASSERT_EQ(1, captured.format_size()); EXPECT_EQ(content.format(0).data(), captured.format(0).data());
}
TEST_F(ClipboardContentWinTest, DibImageGetsLosslessPngAndBitmapFallback)
{
    BITMAPINFOHEADER header{}; header.biSize = sizeof(header); header.biWidth = 2; header.biHeight = 1;
    header.biPlanes = 1; header.biBitCount = 32; header.biSizeImage = 8;
    const unsigned char pixels[] = {0, 0, 255, 255, 0, 255, 0, 255};
    const size_t size = sizeof(header) + sizeof(pixels);
    HGLOBAL memory = GlobalAlloc(GMEM_MOVEABLE, size); ASSERT_NE(nullptr, memory);
    char* data = static_cast<char*>(GlobalLock(memory)); ASSERT_NE(nullptr, data);
    memcpy(data, &header, sizeof(header)); memcpy(data + sizeof(header), pixels, sizeof(pixels)); GlobalUnlock(memory);
    { base::win::ScopedClipboard clipboard; ASSERT_TRUE(clipboard.init(window)); ASSERT_TRUE(clipboard.empty());
      ASSERT_NE(nullptr, SetClipboardData(CF_DIB, memory)); }
    std::string text; proto::ClipboardEvent content;
    ASSERT_TRUE(readClipboardContentWin(window, &text, &content)); ASSERT_EQ(1, content.format_size());
    EXPECT_EQ(proto::ClipboardEvent::Format::PNG, content.format(0).type());
    ASSERT_TRUE(writeClipboardContentWin(window, text, content));
    EXPECT_TRUE(IsClipboardFormatAvailable(RegisterClipboardFormatW(L"PNG")));
    EXPECT_TRUE(IsClipboardFormatAvailable(CF_DIB));
    proto::ClipboardEvent again;
    ASSERT_TRUE(readClipboardContentWin(window, &text, &again));
    EXPECT_EQ(content.SerializeAsString(), again.SerializeAsString());
}
TEST_F(ClipboardContentWinTest, InvalidHtmlDoesNotEraseExistingText)
{
    ASSERT_TRUE(writeClipboardContentWin(window, "keep me", {}));
    proto::ClipboardEvent bad; auto* format = bad.add_format(); format->set_type(proto::ClipboardEvent::Format::HTML);
    format->set_data("StartHTML:9999999999\r\nEndHTML:9999999999\r\nStartFragment:0\r\nEndFragment:1\r\n");
    EXPECT_FALSE(writeClipboardContentWin(window, "", bad));
    std::string text; proto::ClipboardEvent captured;
    ASSERT_TRUE(readClipboardContentWin(window, &text, &captured)); EXPECT_EQ("keep me", text);
}
} // namespace
} // namespace common
