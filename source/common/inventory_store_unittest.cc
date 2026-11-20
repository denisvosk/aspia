// Aspia Project
// SPDX-License-Identifier: GPL-3.0-or-later
#include "common/inventory_store.h"

#include <gtest/gtest.h>
#include <sqlite3.h>

#include <atomic>
#include <chrono>
#include <filesystem>
#include <limits>

namespace common {
namespace {

proto::InventorySnapshot sample(uint64_t id = 1, char collection = 'a')
{
    proto::InventorySnapshot value;
    value.set_host_id(id);
    value.set_collection_id(std::string(16, collection));
    value.set_collected_at(1700000000);
    value.set_computer_name("test-pc");
    value.set_cpu_model("Example CPU");
    value.set_cpu_cores(4);
    value.set_ram_bytes(8ULL * 1024 * 1024 * 1024);
    auto disk = value.add_disks();
    disk->set_device_number(0);
    disk->set_model("Example disk");
    disk->set_media(proto::InventoryDisk::UNKNOWN);
    auto volume = value.add_volumes();
    volume->set_path("C:\\");
    volume->set_total_bytes(1000);
    volume->set_free_bytes(200);
    return value;
}

class InventoryStoreTest : public ::testing::Test
{
protected:
    void SetUp() override
    {
        static std::atomic_uint64_t counter{0};
        const auto ticks = std::chrono::steady_clock::now().time_since_epoch().count();
        path_ = (std::filesystem::temp_directory_path() /
            ("aspia-inventory-test-" + std::to_string(ticks) + "-" + std::to_string(counter++) + ".db")).string();
        store_ = InventoryStore::open(path_);
        ASSERT_TRUE(store_);
    }
    void TearDown() override
    {
        store_.reset();
        std::error_code error;
        std::filesystem::remove(path_, error);
        std::filesystem::remove(path_ + "-wal", error);
        std::filesystem::remove(path_ + "-shm", error);
    }
    proto::InventoryList read(uint32_t limit = 100, int64_t after = 0)
    {
        proto::InventoryRequest request;
        request.set_limit(limit);
        request.set_after_host_id(after);
        request.set_request_id(77);
        proto::InventoryList result;
        EXPECT_TRUE(store_->query(request, &result));
        EXPECT_EQ(result.request_id(), 77);
        return result;
    }
    std::string path_;
    std::unique_ptr<InventoryStore> store_;
};

TEST_F(InventoryStoreTest, PersistsAcrossRestartAndStampsReceipt)
{
    auto value = sample();
    value.set_received_at(std::numeric_limits<int64_t>::max());
    ASSERT_TRUE(store_->save(value));
    store_.reset();
    store_ = InventoryStore::open(path_);
    ASSERT_TRUE(store_);
    const auto result = read();
    ASSERT_EQ(result.inventory_size(), 1);
    EXPECT_GT(result.inventory(0).received_at(), 1700000000);
    EXPECT_NE(result.inventory(0).received_at(), value.received_at());
    EXPECT_EQ(result.inventory(0).disks(0).media(), proto::InventoryDisk::UNKNOWN);
}

TEST_F(InventoryStoreTest, RetryPreservesOriginalReceiptAndRejectsChangedPayload)
{
    auto value = sample();
    ASSERT_TRUE(store_->save(value));
    auto saved = read().inventory(0);
    saved.set_received_at(1000);
    sqlite3* db = nullptr;
    ASSERT_EQ(sqlite3_open(path_.c_str(), &db), SQLITE_OK);
    sqlite3_stmt* statement = nullptr;
    ASSERT_EQ(sqlite3_prepare_v2(db, "UPDATE inventory_latest SET received_at=1000,snapshot=? WHERE host_id=1",
                               -1, &statement, nullptr), SQLITE_OK);
    const auto bytes = saved.SerializeAsString();
    ASSERT_EQ(sqlite3_bind_blob(statement, 1, bytes.data(), static_cast<int>(bytes.size()), SQLITE_TRANSIENT), SQLITE_OK);
    ASSERT_EQ(sqlite3_step(statement), SQLITE_DONE);
    sqlite3_finalize(statement);
    sqlite3_close(db);
    ASSERT_TRUE(store_->save(value));
    EXPECT_EQ(read().inventory(0).received_at(), 1000);
    value.set_ram_bytes(16ULL * 1024 * 1024 * 1024);
    EXPECT_FALSE(store_->save(value));
    EXPECT_EQ(read().inventory(0).ram_bytes(), saved.ram_bytes());
    value.set_collection_id(std::string(16, 'b'));
    value.set_collected_at(1600000000); // Source clock rolled back, actual new collection.
    ASSERT_TRUE(store_->save(value));
    EXPECT_GT(read().inventory(0).received_at(), 1000);
    EXPECT_EQ(read().inventory(0).ram_bytes(), value.ram_bytes());
}

TEST_F(InventoryStoreTest, PagesWithoutLosingOrDuplicatingRows)
{
    ASSERT_TRUE(store_->save(sample(50)));
    ASSERT_TRUE(store_->save(sample(10)));
    ASSERT_TRUE(store_->save(sample(90)));
    const auto first = read(2);
    ASSERT_EQ(first.inventory_size(), 2);
    EXPECT_EQ(first.inventory(0).host_id(), 10);
    EXPECT_EQ(first.inventory(1).host_id(), 50);
    EXPECT_EQ(first.next_after_host_id(), 50);
    const auto second = read(2, first.next_after_host_id());
    ASSERT_EQ(second.inventory_size(), 1);
    EXPECT_EQ(second.inventory(0).host_id(), 90);
    EXPECT_EQ(second.next_after_host_id(), 0);
}

TEST_F(InventoryStoreTest, RemovesUnknownFieldsBeforeStorage)
{
    auto value = sample();
    std::string bytes = value.SerializeAsString();
    bytes.append("\xa2\x06\x07", 3); // unknown field 100, length 7
    bytes.append("SECRET!");
    ASSERT_TRUE(value.ParseFromString(bytes));
    ASSERT_TRUE(store_->save(value));
    EXPECT_EQ(read().inventory(0).SerializeAsString().find("SECRET!"), std::string::npos);
}

TEST_F(InventoryStoreTest, RejectsInvalidBoundsAndPreservesPreviousSnapshot)
{
    ASSERT_TRUE(store_->save(sample()));
    auto bad = sample();
    bad.set_host_id(0);
    EXPECT_FALSE(store_->save(bad));
    bad = sample(); bad.set_collection_id("short");
    EXPECT_FALSE(store_->save(bad));
    bad = sample(); bad.set_computer_name(std::string(513, 'x'));
    EXPECT_FALSE(store_->save(bad));
    bad = sample(); bad.mutable_volumes(0)->set_free_bytes(1001);
    EXPECT_FALSE(store_->save(bad));
    bad = sample(); bad.add_disks()->CopyFrom(bad.disks(0));
    EXPECT_FALSE(store_->save(bad));
    bad = sample(); bad.add_volumes()->CopyFrom(bad.volumes(0));
    EXPECT_FALSE(store_->save(bad));
    EXPECT_EQ(read().inventory_size(), 1);
}

TEST_F(InventoryStoreTest, RejectsInvalidQueryAndEchoesCorrelation)
{
    proto::InventoryRequest request;
    request.set_limit(501);
    request.set_request_id(9);
    proto::InventoryList result;
    EXPECT_FALSE(store_->query(request, &result));
    EXPECT_EQ(result.error_code(), proto::InventoryList::INVALID_REQUEST);
    EXPECT_EQ(result.request_id(), 9);
    request.set_limit(0); request.set_after_host_id(-1);
    EXPECT_FALSE(store_->query(request, &result));
}

} // namespace
} // namespace common
