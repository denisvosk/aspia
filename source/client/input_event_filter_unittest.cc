// Aspia 2.7 community continuation, 2026. GPL-3.0-or-later.
#include "client/input_event_filter.h"
#include "common/clipboard_file_transfer.h"
#include <gtest/gtest.h>
namespace client {
TEST(ClipboardFilter, FileMessagesAreLosslessButStillRequireManageAndClipboard)
{
    InputEventFilter filter;
    proto::ClipboardEvent file; file.set_mime_type(common::kFileClipboardMime);
    proto::ClipboardEvent text; text.set_mime_type("text/plain; charset=UTF-8");
    filter.setSessionType(proto::SESSION_TYPE_DESKTOP_MANAGE);
    EXPECT_FALSE(filter.sendClipboardEvent(file));
    EXPECT_FALSE(filter.readClipboardEvent(file));
    filter.setClipboardEnabled(true);
    EXPECT_TRUE(filter.sendClipboardEvent(file));
    EXPECT_TRUE(filter.sendClipboardEvent(text));
    filter.setNetworkOverflow(true);
    EXPECT_TRUE(filter.sendClipboardEvent(file));
    EXPECT_FALSE(filter.sendClipboardEvent(text));
    filter.setSessionType(proto::SESSION_TYPE_DESKTOP_VIEW);
    EXPECT_FALSE(filter.sendClipboardEvent(file));
    EXPECT_FALSE(filter.readClipboardEvent(file));
    filter.setSessionType(proto::SESSION_TYPE_DESKTOP_MANAGE);
    filter.setClipboardEnabled(false);
    EXPECT_FALSE(filter.sendClipboardEvent(file));
    EXPECT_FALSE(filter.readClipboardEvent(file));
}
} // namespace client
