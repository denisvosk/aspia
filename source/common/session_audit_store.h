// Copyright (C) 2026 Aspia+ contributors. GPL v3 or later.
#ifndef COMMON_SESSION_AUDIT_STORE_H
#define COMMON_SESSION_AUDIT_STORE_H

#include "proto/session_audit.pb.h"

#include <memory>
#include <string>
#include <vector>

struct sqlite3;

namespace common {

// Single-owner, single-thread SQLite store. Its transaction commit is the ACK boundary.
// Uses a separate file from authentication settings and never stores credentials.
class SessionAuditStore
{
public:
    static std::unique_ptr<SessionAuditStore> open(const std::string& file_name);
    ~SessionAuditStore();

    static bool validReport(const proto::SessionAuditRecord& record, int64_t now);
    bool issueGrant(uint64_t host_id, const std::string& token, const std::string& router_user_name,
                    const std::string& client_address, int64_t now);
    bool saveReport(proto::SessionAuditRecord record, int64_t now,
                    const std::string& host_name, const std::string& host_address);
    bool auditList(const proto::SessionAuditRequest& request, proto::SessionAuditList* result);
    bool interruptAll();
    bool interruptHost(uint64_t host_id);

    bool observeHost(uint64_t host_id, const std::string& name, const std::string& os,
                     const std::string& address, int64_t now, bool online);
    bool resetPresence();
    bool presenceList(const proto::HostPresenceRequest& request, proto::HostPresenceList* result);

    // Durable Host outbox. Active entries survive ACKs, so a service crash can be reported
    // as an unknown end on the next startup. Terminal entries leave only after matching ACK.
    bool queue(proto::SessionAuditRecord* record);
    bool interruptOutbox();
    bool acknowledge(const proto::SessionAuditAck& ack);
    bool defer(const proto::SessionAuditAck& ack);
    bool retryDeferred();
    std::vector<proto::SessionAuditRecord> pending(uint64_t host_id, size_t limit);

private:
    bool correlateGrant(uint64_t host_id, const std::string& event_id, const std::string& token);
    explicit SessionAuditStore(sqlite3* database) : db_(database) {}
    sqlite3* db_;
};

} // namespace common
#endif
