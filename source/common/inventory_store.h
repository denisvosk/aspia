// Aspia Project
// SPDX-License-Identifier: GPL-3.0-or-later

#ifndef COMMON_INVENTORY_STORE_H
#define COMMON_INVENTORY_STORE_H

#include "proto/inventory.pb.h"

#include <memory>
#include <string>

struct sqlite3;

namespace common {

// Access only from the Router thread. One bounded, latest snapshot per authenticated Host ID.
// This database is independent from credentials and never contains them.
class InventoryStore
{
public:
    static std::unique_ptr<InventoryStore> open(const std::string& path);
    ~InventoryStore();
    static bool validSnapshot(const proto::InventorySnapshot& snapshot);
    bool save(const proto::InventorySnapshot& snapshot);
    bool query(const proto::InventoryRequest& request, proto::InventoryList* result);

private:
    explicit InventoryStore(sqlite3* db) : db_(db) {}
    sqlite3* db_;
};

} // namespace common

#endif // COMMON_INVENTORY_STORE_H
