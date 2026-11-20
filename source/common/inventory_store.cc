// Aspia Project
// SPDX-License-Identifier: GPL-3.0-or-later

#include "common/inventory_store.h"

#include <sqlite3.h>

#include <chrono>
#include <limits>
#include <set>

namespace common {

namespace {

constexpr size_t kMaxSnapshotBytes = 128 * 1024;
constexpr size_t kMaxReplyBytes = 2 * 1024 * 1024;

struct Statement
{
    sqlite3_stmt* value = nullptr;
    ~Statement() { sqlite3_finalize(value); }
};

bool validText(const std::string& value, size_t max = 1024)
{
    return value.size() <= max && value.find('\0') == std::string::npos;
}

// Copy only fields in the inventory contract; do not persist unknown fields from a newer or
// untrusted sender (which might otherwise smuggle credentials or enlarge query responses).
proto::InventorySnapshot cleanSnapshot(const proto::InventorySnapshot& input)
{
    proto::InventorySnapshot result;
    result.set_host_id(input.host_id());
    result.set_collection_id(input.collection_id());
    result.set_collected_at(input.collected_at());
    result.set_computer_name(input.computer_name());
    result.set_os_name(input.os_name());
    result.set_os_version(input.os_version());
    result.set_os_arch(input.os_arch());
    result.set_cpu_model(input.cpu_model());
    result.set_cpu_packages(input.cpu_packages());
    result.set_cpu_cores(input.cpu_cores());
    result.set_cpu_threads(input.cpu_threads());
    result.set_cpu_clock_mhz(input.cpu_clock_mhz());
    result.set_ram_bytes(input.ram_bytes());
    result.set_board_manufacturer(input.board_manufacturer());
    result.set_board_model(input.board_model());
    result.set_ram_source(input.ram_source());
    result.set_collection_note(input.collection_note());
    for (const auto& item : input.volumes())
    {
        auto output = result.add_volumes();
        output->set_path(item.path());
        output->set_file_system(item.file_system());
        output->set_total_bytes(item.total_bytes());
        output->set_free_bytes(item.free_bytes());
        output->set_drive_type(item.drive_type());
    }
    for (const auto& item : input.disks())
    {
        auto output = result.add_disks();
        output->set_device_number(item.device_number());
        output->set_model(item.model());
        output->set_size_bytes(item.size_bytes());
        output->set_media(item.media());
        output->set_media_evidence(item.media_evidence());
        output->set_bus_type(item.bus_type());
    }
    return result;
}

} // namespace

std::unique_ptr<InventoryStore> InventoryStore::open(const std::string& path)
{
    sqlite3* db = nullptr;
    if (sqlite3_open_v2(path.c_str(), &db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE |
                        SQLITE_OPEN_NOMUTEX, nullptr) != SQLITE_OK)
    {
        if (db)
            sqlite3_close(db);
        return nullptr;
    }
    sqlite3_busy_timeout(db, 2000);
    const char* sql = "PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;"
        "CREATE TABLE IF NOT EXISTS inventory_latest("
        "host_id INTEGER PRIMARY KEY CHECK(host_id>0), received_at INTEGER NOT NULL,"
        "snapshot BLOB NOT NULL);";
    if (sqlite3_exec(db, sql, nullptr, nullptr, nullptr) != SQLITE_OK)
    {
        sqlite3_close(db);
        return nullptr;
    }
    return std::unique_ptr<InventoryStore>(new InventoryStore(db));
}

InventoryStore::~InventoryStore()
{
    sqlite3_close(db_);
}

bool InventoryStore::validSnapshot(const proto::InventorySnapshot& snapshot)
{
    if (!snapshot.host_id() || snapshot.host_id() > static_cast<uint64_t>(std::numeric_limits<int64_t>::max()) ||
        snapshot.collected_at() <= 0 || snapshot.collection_id().size() != 16 || snapshot.ByteSizeLong() > kMaxSnapshotBytes ||
        snapshot.volumes_size() > 128 || snapshot.disks_size() > 128 ||
        !validText(snapshot.computer_name(), 512) || snapshot.computer_name().empty() ||
        !validText(snapshot.os_name()) || !validText(snapshot.os_version(), 256) ||
        !validText(snapshot.os_arch(), 128) || !validText(snapshot.cpu_model()) ||
        !validText(snapshot.board_manufacturer(), 512) || !validText(snapshot.board_model(), 512) ||
        !validText(snapshot.ram_source(), 128) || !validText(snapshot.collection_note(), 2048))
        return false;
    std::set<std::string> paths;
    for (const auto& volume : snapshot.volumes())
    {
        if (!validText(volume.path(), 1024) || !validText(volume.file_system(), 128) ||
            volume.free_bytes() > volume.total_bytes() || !paths.insert(volume.path()).second)
            return false;
    }
    std::set<uint32_t> devices;
    for (const auto& disk : snapshot.disks())
    {
        if (!validText(disk.model()) || !validText(disk.media_evidence(), 256) ||
            !proto::InventoryDisk_Media_IsValid(disk.media()) ||
            !devices.insert(disk.device_number()).second)
            return false;
    }
    return true;
}

bool InventoryStore::save(const proto::InventorySnapshot& input)
{
    if (!validSnapshot(input))
        return false;
    proto::InventorySnapshot snapshot = cleanSnapshot(input);
    // Retry/heartbeat traffic must not make an old hardware survey look newly collected.
    // The same collection ID is immutable; a changed payload requires a fresh ID.
    {
        Statement previous;
        if (sqlite3_prepare_v2(db_, "SELECT snapshot FROM inventory_latest WHERE host_id=?", -1,
                               &previous.value, nullptr) != SQLITE_OK ||
            sqlite3_bind_int64(previous.value, 1, static_cast<int64_t>(snapshot.host_id())) != SQLITE_OK)
            return false;
        const int code = sqlite3_step(previous.value);
        if (code == SQLITE_ROW)
        {
            proto::InventorySnapshot old;
            if (!old.ParseFromArray(sqlite3_column_blob(previous.value, 0), sqlite3_column_bytes(previous.value, 0)))
                return false;
            if (old.collection_id() == snapshot.collection_id())
                return cleanSnapshot(old).SerializeAsString() == snapshot.SerializeAsString();
        }
        else if (code != SQLITE_DONE)
            return false;
    }
    const int64_t now = std::chrono::duration_cast<std::chrono::seconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    snapshot.set_received_at(now);
    const std::string bytes = snapshot.SerializeAsString();
    Statement statement;
    const char* sql = "INSERT INTO inventory_latest(host_id,received_at,snapshot) VALUES(?,?,?) "
        "ON CONFLICT(host_id) DO UPDATE SET received_at=excluded.received_at,snapshot=excluded.snapshot";
    if (sqlite3_prepare_v2(db_, sql, -1, &statement.value, nullptr) != SQLITE_OK ||
        sqlite3_bind_int64(statement.value, 1, static_cast<int64_t>(snapshot.host_id())) != SQLITE_OK ||
        sqlite3_bind_int64(statement.value, 2, now) != SQLITE_OK ||
        sqlite3_bind_blob(statement.value, 3, bytes.data(), static_cast<int>(bytes.size()), SQLITE_TRANSIENT) != SQLITE_OK)
        return false;
    return sqlite3_step(statement.value) == SQLITE_DONE;
}

bool InventoryStore::query(const proto::InventoryRequest& request, proto::InventoryList* result)
{
    result->Clear();
    result->set_request_id(request.request_id());
    if (request.after_host_id() < 0 || request.limit() > 500)
    {
        result->set_error_code(proto::InventoryList::INVALID_REQUEST);
        return false;
    }
    const uint32_t limit = request.limit() ? request.limit() : 100;
    Statement statement;
    const char* sql = "SELECT host_id,snapshot FROM inventory_latest WHERE host_id>? ORDER BY host_id LIMIT ?";
    if (sqlite3_prepare_v2(db_, sql, -1, &statement.value, nullptr) != SQLITE_OK ||
        sqlite3_bind_int64(statement.value, 1, request.after_host_id()) != SQLITE_OK ||
        sqlite3_bind_int(statement.value, 2, static_cast<int>(limit + 1)) != SQLITE_OK)
    {
        result->set_error_code(proto::InventoryList::INTERNAL_ERROR);
        return false;
    }
    size_t byte_count = 0;
    int64_t last_id = 0;
    int code = SQLITE_DONE;
    while ((code = sqlite3_step(statement.value)) == SQLITE_ROW)
    {
        const int64_t host_id = sqlite3_column_int64(statement.value, 0);
        const int size = sqlite3_column_bytes(statement.value, 1);
        if (result->inventory_size() >= static_cast<int>(limit) ||
            (result->inventory_size() && byte_count + static_cast<size_t>(size) > kMaxReplyBytes))
        {
            result->set_next_after_host_id(last_id);
            break;
        }
        proto::InventorySnapshot snapshot;
        if (size <= 0 || size > static_cast<int>(kMaxSnapshotBytes) ||
            !snapshot.ParseFromArray(sqlite3_column_blob(statement.value, 1), size) ||
            snapshot.host_id() != static_cast<uint64_t>(host_id) || !validSnapshot(snapshot))
        {
            result->clear_inventory();
            result->set_error_code(proto::InventoryList::INTERNAL_ERROR);
            return false;
        }
        byte_count += static_cast<size_t>(size);
        last_id = host_id;
        result->add_inventory()->Swap(&snapshot);
    }
    if (code != SQLITE_DONE && code != SQLITE_ROW)
    {
        result->clear_inventory();
        result->set_error_code(proto::InventoryList::INTERNAL_ERROR);
        return false;
    }
    result->set_error_code(proto::InventoryList::SUCCESS);
    return true;
}

} // namespace common
