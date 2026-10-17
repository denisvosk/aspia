// Aspia 2.7 community continuation, 2026. GPL-3.0-or-later.
#include "common/clipboard_files_win.h"
#include "base/crypto/random.h"
#include <gtest/gtest.h>
#include <ShlObj.h>
#include <fstream>

namespace common {
namespace {
class OleClipboardTest : public testing::Test {
protected:
    std::filesystem::path directory;
    void SetUp() override
    {
        ASSERT_TRUE(SUCCEEDED(OleInitialize(nullptr)));
        ASSERT_TRUE(SUCCEEDED(OleSetClipboard(nullptr)));
        directory = std::filesystem::temp_directory_path() / ("aspia-ole-test-" + std::to_string(base::Random::number64()));
        std::filesystem::create_directory(directory);
    }
    void TearDown() override
    {
        OleSetClipboard(nullptr); OleUninitialize(); std::filesystem::remove_all(directory);
    }
};
TEST_F(OleClipboardTest, ExplorerFormatsStreamAndSeekRoundTrip)
{
    ClipboardFilesWin* receiver = nullptr;
    ClipboardFileTransfer sender([&](const proto::ClipboardEvent& event) {
        proto::ClipboardFile message;
        ASSERT_TRUE(parseFileClipboard(event, &message)); receiver->receive(message);
    }, [](const auto&) {});
    ClipboardFilesWin windows([&](const proto::ClipboardEvent& event) {
        proto::ClipboardFile message;
        ASSERT_TRUE(parseFileClipboard(event, &message)); sender.receive(message);
    });
    receiver = &windows;
    proto::ClipboardFile hello; hello.set_type(proto::ClipboardFile::HELLO);
    sender.receive(hello); windows.receive(hello);
    std::string input(1024 * 1024 + 3, '\0');
    for (size_t i = 0; i < input.size(); ++i) input[i] = static_cast<char>(i % 251);
    const auto path = directory / "binary.dat";
    { std::ofstream file(path, std::ios::binary); file.write(input.data(), input.size()); }
    const auto empty = directory / "empty.dat"; std::ofstream(empty).close();
    proto::ClipboardFile offer;
    offer.add_entry()->set_name("Folder"); offer.mutable_entry(0)->set_directory(true);
    auto* file = offer.add_entry(); file->set_name("Folder\\\xD0\xA4\xD0\xB0\xD0\xB9\xD0\xBB.dat"); file->set_size(input.size());
    offer.add_entry()->set_name("empty.dat");
    sender.publish(offer, {std::filesystem::canonical(directory), std::filesystem::canonical(path), std::filesystem::canonical(empty)});
    IDataObject* object = nullptr;
    ASSERT_EQ(S_OK, OleGetClipboard(&object)); ASSERT_NE(nullptr, object);
    FORMATETC format{static_cast<CLIPFORMAT>(RegisterClipboardFormatW(CFSTR_FILEDESCRIPTORW)), nullptr, DVASPECT_CONTENT, -1, TYMED_HGLOBAL};
    STGMEDIUM medium{};
    ASSERT_EQ(S_OK, object->GetData(&format, &medium));
    auto* group = static_cast<FILEGROUPDESCRIPTORW*>(GlobalLock(medium.hGlobal));
    ASSERT_NE(nullptr, group); EXPECT_EQ(3u, group->cItems);
    EXPECT_TRUE(group->fgd[0].dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY);
    EXPECT_EQ(input.size(), group->fgd[1].nFileSizeLow);
    EXPECT_STREQ(L"Folder\\\u0424\u0430\u0439\u043B.dat", group->fgd[1].cFileName);
    GlobalUnlock(medium.hGlobal); ReleaseStgMedium(&medium);
    format.cfFormat = static_cast<CLIPFORMAT>(RegisterClipboardFormatW(CFSTR_FILECONTENTS));
    format.tymed = TYMED_ISTREAM; format.lindex = -1;
    EXPECT_EQ(S_OK, object->QueryGetData(&format));
    EXPECT_EQ(DV_E_LINDEX, object->GetData(&format, &medium));
    format.lindex = 1;
    ASSERT_EQ(S_OK, object->GetData(&format, &medium));
    STATSTG stat{}; ASSERT_EQ(S_OK, medium.pstm->Stat(&stat, STATFLAG_NONAME));
    EXPECT_EQ(input.size(), stat.cbSize.QuadPart);
    std::string output(input.size() + 10, '\0'); ULONG got = 0;
    EXPECT_EQ(S_FALSE, medium.pstm->Read(output.data(), static_cast<ULONG>(output.size()), &got));
    EXPECT_EQ(input.size(), got); output.resize(got); EXPECT_EQ(input, output);
    LARGE_INTEGER zero{};
    EXPECT_EQ(S_OK, medium.pstm->Seek(zero, STREAM_SEEK_SET, nullptr));
    char prefix[123]; EXPECT_EQ(S_OK, medium.pstm->Read(prefix, sizeof(prefix), &got));
    EXPECT_EQ(input.substr(0, sizeof(prefix)), std::string(prefix, got));
    ReleaseStgMedium(&medium);
    format.lindex = 2;
    ASSERT_EQ(S_OK, object->GetData(&format, &medium));
    EXPECT_EQ(S_FALSE, medium.pstm->Read(prefix, sizeof(prefix), &got)); EXPECT_EQ(0u, got);
    ReleaseStgMedium(&medium);
    format.lindex = 0; EXPECT_EQ(DV_E_LINDEX, object->GetData(&format, &medium));
    object->Release();
}
TEST_F(OleClipboardTest, DisconnectInvalidatesExistingOleStream)
{
    ClipboardFilesWin windows([](const auto&) {});
    proto::ClipboardFile message; message.set_type(proto::ClipboardFile::HELLO); windows.receive(message);
    message.set_type(proto::ClipboardFile::OFFER); message.set_offer_id(42);
    auto* entry = message.add_entry(); entry->set_name("file.txt"); entry->set_size(4); windows.receive(message);
    IDataObject* object = nullptr; ASSERT_EQ(S_OK, OleGetClipboard(&object));
    FORMATETC format{static_cast<CLIPFORMAT>(RegisterClipboardFormatW(CFSTR_FILECONTENTS)), nullptr, DVASPECT_CONTENT, 0, TYMED_ISTREAM};
    STGMEDIUM medium{}; ASSERT_EQ(S_OK, object->GetData(&format, &medium));
    message.Clear(); message.set_type(proto::ClipboardFile::DISCONNECT); windows.receive(message);
    char data[4]; ULONG got = 0;
    EXPECT_TRUE(FAILED(medium.pstm->Read(data, sizeof(data), &got))); EXPECT_EQ(0u, got);
    ReleaseStgMedium(&medium); object->Release();
}
} // namespace
} // namespace common
