// Aspia Project
// SPDX-License-Identifier: GPL-3.0-or-later

#ifndef HOST_INVENTORY_COLLECTOR_H
#define HOST_INVENTORY_COLLECTOR_H

#include "base/peer/host_id.h"
#include "proto/inventory.pb.h"

#include <functional>
#include <memory>
#include <thread>

namespace base { class TaskRunner; }

namespace host {

// Internal service-executable mode: writes one bounded protobuf to inherited stdout.
int runInventoryCollectorProcess();

// Collects hardware in a disposable helper process with a 60 second deadline on Windows.
// One collection can be in flight; faulty storage drivers cannot stall the service thread.
// Completion is posted to the supplied runner and is suppressed after destruction.
class InventoryCollector
{
public:
    explicit InventoryCollector(std::shared_ptr<base::TaskRunner> task_runner);
    ~InventoryCollector();
    bool collect(base::HostId host_id, std::function<void(proto::InventorySnapshot)> callback);

private:
    struct State;
    std::shared_ptr<State> state_;
    std::thread worker_;
};

} // namespace host

#endif // HOST_INVENTORY_COLLECTOR_H
