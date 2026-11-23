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

#include "common/clipboard.h"
#include "common/clipboard_file_transfer.h"

#include "base/logging.h"

#include <zstd.h>

namespace common {

namespace {

const char kMimeTypeTextUtf8[] = "text/plain; charset=UTF-8";
const char kMimeTypeCompressedTextUtf8[] = "text/plain; charset=UTF-8; compression=ZSTD";

// The compression ratio can be in the range of 1 to 22.
const int kCompressionRatio = 8;

// Smaller data will not be compressed.
const size_t kMinSizeToCompress = 512;

//--------------------------------------------------------------------------------------------------
uint8_t* outputBuffer(std::string* out, size_t size)
{
    out->resize(size);
    return reinterpret_cast<uint8_t*>(out->data());
}

//--------------------------------------------------------------------------------------------------
bool compress(const std::string& in, std::string* out)
{
    if (in.empty())
        return false;

    const size_t input_size = in.size();
    const uint8_t* input_data = reinterpret_cast<const uint8_t*>(in.data());

    size_t output_size = ZSTD_compressBound(in.size());
    uint8_t* output_data = outputBuffer(out, output_size);

    size_t ret = ZSTD_compress(
        output_data, output_size, input_data, input_size, kCompressionRatio);
    if (ZSTD_isError(ret))
    {
        LOG(LS_ERROR) << "ZSTD_compress failed: " << ZSTD_getErrorName(ret);
        return false;
    }

    out->resize(ret);
    return true;
}

//--------------------------------------------------------------------------------------------------
bool decompress(const std::string& in, std::string* out, size_t limit)
{
    if (in.empty())
        return false;

    unsigned long long output_size = ZSTD_getFrameContentSize(in.data(), in.size());
    if (output_size == ZSTD_CONTENTSIZE_ERROR)
    {
        LOG(LS_ERROR) << "Data not compressed by ZSTD";
        return false;
    }

    if (output_size == ZSTD_CONTENTSIZE_UNKNOWN)
    {
        LOG(LS_ERROR) << "Original size unknown";
        return false;
    }

    if (!output_size || output_size > limit)
        return false;

    uint8_t* output_data = outputBuffer(out, static_cast<size_t>(output_size));

    size_t ret = ZSTD_decompress(
        output_data, static_cast<size_t>(output_size), in.data(), in.size());
    if (ZSTD_isError(ret))
    {
        LOG(LS_ERROR) << "ZSTD_decompress failed: " << ZSTD_getErrorName(ret);
        return false;
    }

    return ret == output_size;
}

bool validFormatType(proto::ClipboardEvent::Format::Type type)
{
    return type == proto::ClipboardEvent::Format::RTF ||
           type == proto::ClipboardEvent::Format::HTML ||
           type == proto::ClipboardEvent::Format::PNG;
}

} // namespace

//--------------------------------------------------------------------------------------------------
void Clipboard::start(Delegate* delegate)
{
    delegate_ = delegate;
    DCHECK(delegate_);
    init();
}

//--------------------------------------------------------------------------------------------------
void Clipboard::injectClipboardEvent(const proto::ClipboardEvent& event)
{
    if (event.mime_type() == kFileClipboardMime)
    {
        last_data_.clear();
        last_formats_.clear();
        setFileData(event);
        return;
    }
    if (event.ByteSizeLong() > kClipboardContentWireLimit || event.format_size() > 3) return;
    std::string text;
    if (event.mime_type() == kMimeTypeCompressedTextUtf8)
    {
        if (!decompress(event.data(), &text, kClipboardContentDecodedLimit))
            return;
    }
    else if (event.mime_type() == kMimeTypeTextUtf8)
    {
        text = event.data();
    }
    else
    {
        LOG(LS_ERROR) << "Unsupported mime type: " << event.mime_type();
        return;
    }

    // Validate/decompress the complete bundle before changing the clipboard.
    proto::ClipboardEvent content;
    size_t remaining = kClipboardContentDecodedLimit - text.size();
    unsigned seen = 0;
    for (const auto& format : event.format())
    {
        if (!validFormatType(format.type()) || (seen & (1u << format.type()))) return;
        seen |= 1u << format.type();
        auto* decoded = content.add_format();
        decoded->set_type(format.type());
        if (format.compressed())
        {
            if (!decompress(format.data(), decoded->mutable_data(), remaining)) return;
        }
        else
        {
            if (format.data().size() > remaining) return;
            decoded->set_data(format.data());
        }
        if (decoded->data().empty()) return;
        remaining -= decoded->data().size();
    }
    last_data_ = std::move(text);
    last_formats_ = content.SerializeAsString();
    setContent(last_data_, content);
}

//--------------------------------------------------------------------------------------------------
void Clipboard::clearClipboard()
{
    last_data_.clear();
    last_formats_.clear();
    setData(std::string());
}

//--------------------------------------------------------------------------------------------------
void Clipboard::onData(const std::string& data, const proto::ClipboardEvent& content)
{
    if (data.size() > kClipboardContentDecodedLimit || content.format_size() > 3) return;
    const std::string formats = content.SerializeAsString();
    if (last_data_ == data && last_formats_ == formats)
        return;

    proto::ClipboardEvent event;

    if (data.size() > kMinSizeToCompress)
    {
        std::string compressed_data;
        if (!compress(data, &compressed_data))
            return;

        event.set_mime_type(kMimeTypeCompressedTextUtf8);
        event.set_data(std::move(compressed_data));
    }
    else
    {
        event.set_mime_type(kMimeTypeTextUtf8);
        event.set_data(data);
    }

    size_t remaining = kClipboardContentDecodedLimit - data.size();
    unsigned seen = 0;
    for (const auto& format : content.format())
    {
        if (!validFormatType(format.type()) || format.compressed() || format.data().empty() ||
            (seen & (1u << format.type())) || format.data().size() > remaining) return;
        seen |= 1u << format.type();
        remaining -= format.data().size();
        auto* encoded = event.add_format();
        *encoded = format;
        std::string compressed;
        if (format.data().size() > kMinSizeToCompress && compress(format.data(), &compressed) &&
            compressed.size() < format.data().size())
        {
            encoded->set_data(std::move(compressed));
            encoded->set_compressed(true);
        }
    }
    if (event.ByteSizeLong() > kClipboardContentWireLimit)
    {
        LOG(LS_ERROR) << "Clipboard content exceeds transfer limit; using plain text";
        event.clear_format();
        if (data.empty() || event.ByteSizeLong() > kClipboardContentWireLimit) return;
    }
    last_data_ = data;
    last_formats_ = formats;

    if (delegate_)
        delegate_->onClipboardEvent(event);
}

void Clipboard::sendEvent(const proto::ClipboardEvent& event)
{
    if (event.mime_type() == kFileClipboardMime)
    {
        last_data_.clear();
        last_formats_.clear();
    }
    if (delegate_) delegate_->onClipboardEvent(event);
}

} // namespace common
