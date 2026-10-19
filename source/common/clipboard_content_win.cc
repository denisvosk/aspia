// Rich clipboard handling adapted from Aspia v3.1.1 common/clipboard_win.cc.
// Copyright (C) 2016-2026 Dmitry Chapyshev <dmitry@aspia.ru>
// Aspia 2.7 community continuation, 2026. GPL-3.0-or-later.
#include "common/clipboard_content_win.h"
#include "base/logging.h"
#include "base/strings/string_util.h"
#include "base/strings/unicode.h"
#include "base/win/scoped_clipboard.h"
#include <QBuffer>
#include <QImage>
#include <QImageReader>
#include <algorithm>
#include <charconv>
#include <cstring>
#include <vector>

namespace common {
namespace {
using Format = proto::ClipboardEvent::Format;
constexpr size_t kImageLimit = 64 * 1024 * 1024;
UINT formatId(Format::Type type)
{
    switch (type)
    {
        case Format::RTF: return RegisterClipboardFormatW(L"Rich Text Format");
        case Format::HTML: return RegisterClipboardFormatW(L"HTML Format");
        case Format::PNG: return RegisterClipboardFormatW(L"PNG");
        default: return 0;
    }
}
std::string clipboardBytes(base::win::ScopedClipboard& clipboard, UINT format, size_t limit)
{
    if (!IsClipboardFormatAvailable(format)) return {};
    HGLOBAL handle = clipboard.data(format);
    if (!handle) return {};
    const size_t size = GlobalSize(handle);
    if (!size || size > limit) return {};
    const auto* data = static_cast<const char*>(GlobalLock(handle));
    if (!data) return {};
    std::string result(data, size);
    GlobalUnlock(handle);
    return result;
}
size_t htmlSize(const std::string& html)
{
    // Retain the entire CF_HTML document: its head can contain Word's styles.
    auto offset = [&html](const char* key) -> int64_t {
        auto pos = html.find(key);
        if (pos == std::string::npos || pos > 4096) return -1;
        pos += strlen(key);
        int64_t value = -1;
        const auto parsed = std::from_chars(html.data() + pos, html.data() + html.size(), value);
        return parsed.ec == std::errc() ? value : -1;
    };
    const auto begin = offset("StartHTML:"), end = offset("EndHTML:");
    const auto fragment = offset("StartFragment:"), finish = offset("EndFragment:");
    if (begin < 0 || end < begin || static_cast<uint64_t>(end) > html.size() ||
        fragment < begin || finish < fragment || finish > end) return 0;
    return static_cast<size_t>(end);
}
size_t rtfSize(const std::string& data)
{
    if (data.compare(0, 5, "{\\rtf") != 0) return 0;
    size_t depth = 0;
    auto alpha = [](char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); };
    for (size_t i = 0; i < data.size();)
    {
        const char c = data[i++];
        if (c == '\0') return 0;
        if (c == '{') ++depth;
        else if (c == '}') { if (!depth) return 0; if (!--depth) return i; }
        else if (c == '\\')
        {
            if (i >= data.size()) return 0;
            if (!alpha(data[i])) { ++i; continue; }
            const size_t word = i;
            while (i < data.size() && alpha(data[i])) ++i;
            const bool binary = data.compare(word, i - word, "bin") == 0;
            const size_t number = i;
            if (i < data.size() && data[i] == '-') ++i;
            while (i < data.size() && data[i] >= '0' && data[i] <= '9') ++i;
            size_t count = 0;
            if (binary && (number == i || std::from_chars(data.data() + number, data.data() + i, count).ec != std::errc()))
                return 0;
            if (i < data.size() && data[i] == ' ') ++i;
            if (binary) { if (count > data.size() - i) return 0; i += count; }
        }
    }
    return 0;
}
size_t pngSize(const std::string& data)
{
    if (data.size() < 8 || memcmp(data.data(), "\x89PNG\r\n\x1a\n", 8)) return 0;
    for (size_t offset = 8; data.size() - offset >= 12;)
    {
        const auto* bytes = reinterpret_cast<const unsigned char*>(data.data() + offset);
        const uint64_t count = (uint32_t(bytes[0]) << 24) | (uint32_t(bytes[1]) << 16) |
                               (uint32_t(bytes[2]) << 8) | bytes[3];
        if (count > data.size() - offset - 12) return 0;
        offset += static_cast<size_t>(count) + 12;
        if (!memcmp(bytes + 4, "IEND", 4)) return count == 0 ? offset : 0;
    }
    return 0;
}
bool imageSizeAllowed(int64_t width, int64_t height)
{
    return width > 0 && height > 0 && width <= 16384 && height <= 16384 &&
           static_cast<uint64_t>(width * height) <= kImageLimit / 4;
}
QImage decodePng(const std::string& png)
{
    QByteArray bytes = QByteArray::fromRawData(png.data(), static_cast<int>(png.size()));
    QBuffer buffer(&bytes); buffer.open(QIODevice::ReadOnly);
    QImageReader reader(&buffer, "PNG");
    const QSize size = reader.size();
    if (!imageSizeAllowed(size.width(), size.height())) return {};
    return reader.read();
}
std::string dibToPng(const std::string& dib)
{
    if (dib.size() < sizeof(BITMAPINFOHEADER)) return {};
    BITMAPINFOHEADER header{}; memcpy(&header, dib.data(), sizeof(header));
    const int64_t height = header.biHeight < 0 ? -static_cast<int64_t>(header.biHeight) : header.biHeight;
    if (header.biSize < sizeof(header) || header.biSize > dib.size() || header.biPlanes != 1 ||
        !imageSizeAllowed(header.biWidth, height)) return {};
    uint32_t palette = header.biClrUsed;
    if (header.biBitCount <= 8 && !palette) palette = 1u << header.biBitCount;
    const uint32_t masks = header.biCompression == BI_BITFIELDS && header.biSize == sizeof(header) ? 12 : 0;
    const uint64_t offset = sizeof(BITMAPFILEHEADER) + header.biSize + masks + uint64_t(palette) * sizeof(RGBQUAD);
    if (offset >= sizeof(BITMAPFILEHEADER) + dib.size()) return {};
    BITMAPFILEHEADER file{}; file.bfType = 0x4D42;
    file.bfSize = static_cast<DWORD>(sizeof(file) + dib.size()); file.bfOffBits = static_cast<DWORD>(offset);
    QByteArray bmp(reinterpret_cast<const char*>(&file), sizeof(file));
    bmp.append(dib.data(), static_cast<int>(dib.size()));
    const QImage image = QImage::fromData(bmp, "BMP");
    if (image.isNull()) return {};
    QByteArray png; QBuffer buffer(&png); buffer.open(QIODevice::WriteOnly);
    if (!image.save(&buffer, "PNG") || static_cast<size_t>(png.size()) > kClipboardContentDecodedLimit) return {};
    return std::string(png.constData(), png.size());
}
std::string pngToDib(const QImage& decoded)
{
    const QImage image = decoded.convertToFormat(QImage::Format_ARGB32);
    if (image.isNull()) return {};
    BITMAPINFOHEADER header{};
    header.biSize = sizeof(header); header.biWidth = image.width(); header.biHeight = image.height();
    header.biPlanes = 1; header.biBitCount = 32; header.biCompression = BI_RGB;
    const size_t stride = static_cast<size_t>(image.width()) * 4;
    header.biSizeImage = static_cast<DWORD>(stride * image.height());
    std::string dib(reinterpret_cast<const char*>(&header), sizeof(header));
    dib.reserve(sizeof(header) + header.biSizeImage);
    for (int y = image.height() - 1; y >= 0; --y)
        dib.append(reinterpret_cast<const char*>(image.constScanLine(y)), stride);
    return dib;
}
struct Payload { UINT format; std::string bytes; HGLOBAL memory = nullptr; };
struct Payloads : std::vector<Payload> {
    ~Payloads() { for (auto& item : *this) if (item.memory) GlobalFree(item.memory); }
};
} // namespace

bool readClipboardContentWin(HWND owner, std::string* text, proto::ClipboardEvent* content)
{
    text->clear(); content->Clear();
    std::string wide, rtf, html, png, dib;
    {
        base::win::ScopedClipboard clipboard;
        if (!clipboard.init(owner)) return false;
        wide = clipboardBytes(clipboard, CF_UNICODETEXT, kClipboardContentDecodedLimit);
        rtf = clipboardBytes(clipboard, formatId(Format::RTF), kClipboardContentDecodedLimit);
        html = clipboardBytes(clipboard, formatId(Format::HTML), kClipboardContentDecodedLimit);
        png = clipboardBytes(clipboard, formatId(Format::PNG), kClipboardContentDecodedLimit);
        if (png.empty()) dib = clipboardBytes(clipboard, CF_DIB, kImageLimit + sizeof(BITMAPV5HEADER));
    }
    if (!wide.empty() && wide.size() % sizeof(wchar_t) == 0)
    {
        std::wstring value(wide.size() / sizeof(wchar_t), L'\0');
        memcpy(value.data(), wide.data(), wide.size());
        value.resize(wcsnlen(value.data(), value.size()));
        if (!base::wideToUtf8(value, text)) return false;
        *text = base::replaceCrLfByLf(*text);
    }
    // Do not send allocation padding. RTF can contain binary \\bin payloads,
    // so its first zero byte is not necessarily the end of the document.
    rtf.resize(rtfSize(rtf));
    html.resize(htmlSize(html));
    png.resize(pngSize(png));
    // Word's RTF embeds pictures, whereas its HTML can name inaccessible local
    // temporary image files. Prefer the self-contained representation in that case.
    std::string lower = html;
    std::transform(lower.begin(), lower.end(), lower.begin(), [](unsigned char c) {
        return static_cast<char>(c >= 'A' && c <= 'Z' ? c + ('a' - 'A') : c);
    });
    if (rtf.find("\\pict") != std::string::npos && lower.find("<img") != std::string::npos)
        html.clear();
    if (png.empty() && !dib.empty()) png = dibToPng(dib);
    if (!png.empty() && decodePng(png).isNull()) png.clear();
    if (text->size() + rtf.size() + html.size() + png.size() > kClipboardContentDecodedLimit)
    {
        LOG(LS_ERROR) << "Rich clipboard exceeds decoded limit; keeping plain text";
        return !text->empty() && text->size() <= kClipboardContentDecodedLimit;
    }
    auto add = [content](Format::Type type, std::string& bytes) {
        if (bytes.empty()) return;
        auto* format = content->add_format(); format->set_type(type); format->set_data(std::move(bytes));
    };
    add(Format::RTF, rtf); add(Format::HTML, html); add(Format::PNG, png);
    return !text->empty() || content->format_size() != 0;
}

bool writeClipboardContentWin(HWND owner, const std::string& text, const proto::ClipboardEvent& content)
{
    Payloads payloads;
    if (!text.empty())
    {
        std::wstring wide;
        if (!base::utf8ToWide(base::replaceLfByCrLf(text), &wide)) return false;
        payloads.push_back({CF_UNICODETEXT,
            std::string(reinterpret_cast<const char*>(wide.c_str()), (wide.size() + 1) * sizeof(wchar_t))});
    }
    // Prepare/validate/allocate everything before emptying the current clipboard.
    for (const auto& format : content.format())
    {
        if (format.compressed() || format.data().empty()) return false;
        const UINT id = formatId(format.type());
        if (!id) return false;
        std::string bytes = format.data();
        if (format.type() == Format::HTML) bytes.resize(htmlSize(bytes));
        if (format.type() == Format::RTF) bytes.resize(rtfSize(bytes));
        if (format.type() == Format::PNG) bytes.resize(pngSize(bytes));
        if (bytes.empty()) continue;
        if (format.type() == Format::PNG)
        {
            const QImage image = decodePng(bytes);
            if (image.isNull()) continue;
            std::string dib = pngToDib(image);
            if (!dib.empty()) payloads.push_back({CF_DIB, std::move(dib)});
        }
        else bytes.push_back('\0');
        payloads.push_back({id, std::move(bytes)});
    }
    if (payloads.empty() && (!text.empty() || content.format_size())) return false;
    if (!payloads.empty())
    {
        // Match upstream's opt-out of clipboard history and cloud synchronization.
        const std::string no(sizeof(DWORD), '\0');
        payloads.push_back({RegisterClipboardFormatW(L"CanIncludeInClipboardHistory"), no});
        payloads.push_back({RegisterClipboardFormatW(L"CanUploadToCloudClipboard"), no});
        payloads.push_back({RegisterClipboardFormatW(L"ExcludeClipboardContentFromMonitorProcessing"), no});
    }
    for (auto& item : payloads)
    {
        item.memory = GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, item.bytes.size());
        if (!item.memory) return false;
        void* data = GlobalLock(item.memory);
        if (!data) return false;
        memcpy(data, item.bytes.data(), item.bytes.size()); GlobalUnlock(item.memory);
    }
    base::win::ScopedClipboard clipboard;
    if (!clipboard.init(owner) || !clipboard.empty()) return false;
    bool success = true;
    for (auto& item : payloads)
    {
        if (SetClipboardData(item.format, item.memory)) item.memory = nullptr;
        else success = false;
    }
    return success;
}
} // namespace common
