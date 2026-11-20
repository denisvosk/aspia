// Copyright (C) 2026 Aspia+ contributors. GPL v3 or later.
#include "common/session_audit_store.h"

#include <sqlite3.h>
#include <algorithm>
#include <limits>

namespace common {
namespace {

class Statement
{
public:
    Statement(sqlite3* db, const char* sql)
    {
        if (sqlite3_prepare_v2(db, sql, -1, &stmt_, nullptr) != SQLITE_OK)
        {
            sqlite3_finalize(stmt_);
            stmt_ = nullptr;
        }
    }
    ~Statement() { sqlite3_finalize(stmt_); }
    explicit operator bool() const { return stmt_ != nullptr; }
    bool integer(int pos, int64_t value) { return sqlite3_bind_int64(stmt_, pos, value) == SQLITE_OK; }
    bool text(int pos, const std::string& value)
    {
        return sqlite3_bind_text(stmt_, pos, value.data(), static_cast<int>(value.size()),
                                 SQLITE_TRANSIENT) == SQLITE_OK;
    }
    bool blob(int pos, const std::string& value)
    {
        return sqlite3_bind_blob(stmt_, pos, value.data(), static_cast<int>(value.size()),
                                 SQLITE_TRANSIENT) == SQLITE_OK;
    }
    int step() { return sqlite3_step(stmt_); }
    int64_t integer(int col) const { return sqlite3_column_int64(stmt_, col); }
    std::string text(int col) const
    {
        const char* p = reinterpret_cast<const char*>(sqlite3_column_text(stmt_, col));
        return p ? std::string(p, sqlite3_column_bytes(stmt_, col)) : std::string();
    }
    bool record(int col, proto::SessionAuditRecord* value) const
    {
        int size = sqlite3_column_bytes(stmt_, col);
        return size > 0 && size <= 8192 &&
            value->ParseFromArray(sqlite3_column_blob(stmt_, col), size);
    }
private:
    sqlite3_stmt* stmt_ = nullptr;
};

bool execute(sqlite3* db, const char* sql)
{
    return sqlite3_exec(db, sql, nullptr, nullptr, nullptr) == SQLITE_OK;
}

bool fitsId(uint64_t id)
{
    return id > 0 && id <= static_cast<uint64_t>(std::numeric_limits<int64_t>::max());
}

bool bounded(const std::string& value, size_t max)
{
    return value.size() <= max && value.find('\0') == std::string::npos;
}

} // namespace

std::unique_ptr<SessionAuditStore> SessionAuditStore::open(const std::string& file_name)
{
    sqlite3* db = nullptr;
    if (sqlite3_open_v2(file_name.c_str(), &db,
                      SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, nullptr) != SQLITE_OK)
    {
        sqlite3_close(db);
        return nullptr;
    }
    sqlite3_busy_timeout(db, 1000);
    if (!execute(db, "PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;"
        "CREATE TABLE IF NOT EXISTS audit ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, host_id INTEGER NOT NULL, event_id BLOB NOT NULL,"
        "started_at INTEGER NOT NULL, user_name TEXT NOT NULL, state INTEGER NOT NULL,"
        "revision INTEGER NOT NULL, payload BLOB NOT NULL, UNIQUE(host_id,event_id));"
        "CREATE INDEX IF NOT EXISTS audit_time ON audit(started_at DESC,id DESC);"
        "CREATE INDEX IF NOT EXISTS audit_host ON audit(host_id,started_at DESC,id DESC);"
        "CREATE INDEX IF NOT EXISTS audit_user ON audit(user_name,started_at DESC,id DESC);"
        "CREATE TABLE IF NOT EXISTS presence (host_id INTEGER PRIMARY KEY, name TEXT NOT NULL,"
        "os TEXT NOT NULL, address TEXT NOT NULL, first_seen INTEGER NOT NULL,"
        "last_seen INTEGER NOT NULL, online INTEGER NOT NULL);"
        "CREATE TABLE IF NOT EXISTS outbox (event_id BLOB PRIMARY KEY,host_id INTEGER NOT NULL,"
        "revision INTEGER NOT NULL,state INTEGER NOT NULL,dirty INTEGER NOT NULL,payload BLOB NOT NULL);"
        "UPDATE outbox SET dirty=1 WHERE dirty=2;"))
    {
        sqlite3_close(db);
        return nullptr;
    }
    return std::unique_ptr<SessionAuditStore>(new SessionAuditStore(db));
}

SessionAuditStore::~SessionAuditStore() { sqlite3_close(db_); }

bool SessionAuditStore::validReport(const proto::SessionAuditRecord& r, int64_t now)
{
    const uint32_t allowed_types = 1 | 2 | 4 | 8 | 16;
    return now > 0 && now <= std::numeric_limits<int64_t>::max() - 86400 &&
        r.event_id().size() == 16 && fitsId(r.host_id()) && fitsId(r.revision()) &&
        r.session_type() != 0 && (r.session_type() & (r.session_type() - 1)) == 0 &&
        (r.session_type() & allowed_types) != 0 &&
        !r.user_name().empty() && bounded(r.user_name(), 256) &&
        bounded(r.client_computer(), 1024) && bounded(r.peer_address(), 256) &&
        r.started_at() > 0 && r.started_at() <= now + 86400 &&
        r.ended_at() >= 0 && r.ended_at() <= now + 86400 &&
        r.duration_seconds() <= 315576000ULL &&
        (r.state() == proto::SessionAuditRecord::ACTIVE ||
         r.state() == proto::SessionAuditRecord::FINISHED ||
         r.state() == proto::SessionAuditRecord::INTERRUPTED) &&
        ((r.state() == proto::SessionAuditRecord::FINISHED) == (r.ended_at() != 0)) &&
        r.ByteSizeLong() <= 8192;
}

bool SessionAuditStore::saveReport(proto::SessionAuditRecord record, int64_t now,
                                 const std::string& host_name, const std::string& host_address)
{
    if (!validReport(record, now) || !bounded(host_name, 1024) || !bounded(host_address, 256))
        return false;
    {
        Statement existing(db_, "SELECT payload,revision,state FROM audit WHERE host_id=? AND event_id=?");
        if (!existing || !existing.integer(1, static_cast<int64_t>(record.host_id())) ||
            !existing.blob(2, record.event_id()))
            return false;
        const int step = existing.step();
        if (step == SQLITE_ROW)
        {
            proto::SessionAuditRecord old;
            if (!existing.record(0, &old) || old.started_at() != record.started_at() ||
                old.user_name() != record.user_name() || old.session_type() != record.session_type() ||
                old.client_computer() != record.client_computer() ||
                old.peer_address() != record.peer_address())
                return false;
            // A duplicate is acknowledged. Older messages cannot reopen or overwrite a session.
            if (static_cast<uint64_t>(existing.integer(1)) >= record.revision())
                return true;
            if (existing.integer(2) == proto::SessionAuditRecord::FINISHED ||
                record.duration_seconds() < old.duration_seconds())
                return false;
            record.set_host_name(old.host_name()); // Snapshot, unaffected by later renames.
            record.set_host_address(old.host_address());
        }
        else if (step != SQLITE_DONE)
            return false;
        else
        {
            record.set_host_name(host_name);
            record.set_host_address(host_address);
        }
    } // Finalize the read before the committing write/ACK boundary.
    record.set_id(0);
    record.set_last_seen(now);
    Statement write(db_, "INSERT INTO audit(host_id,event_id,started_at,user_name,state,revision,payload)"
        " VALUES(?,?,?,?,?,?,?) ON CONFLICT(host_id,event_id) DO UPDATE SET "
        "state=excluded.state,revision=excluded.revision,payload=excluded.payload");
    return write && write.integer(1, static_cast<int64_t>(record.host_id())) &&
        write.blob(2, record.event_id()) && write.integer(3, record.started_at()) &&
        write.text(4, record.user_name()) && write.integer(5, record.state()) &&
        write.integer(6, static_cast<int64_t>(record.revision())) &&
        write.blob(7, record.SerializeAsString()) && write.step() == SQLITE_DONE;
}

bool SessionAuditStore::auditList(const proto::SessionAuditRequest& request,
                                proto::SessionAuditList* result)
{
    result->Clear();
    result->set_request_id(request.request_id());
    if (request.from_time() < 0 || request.to_time() < 0 || request.before_id() < 0 ||
        request.before_started_at() < 0 || request.limit() > 500 ||
        (request.before_id() == 0) != (request.before_started_at() == 0) ||
        (request.to_time() && request.from_time() >= request.to_time()) ||
        !bounded(request.user_name(), 256) ||
        request.host_id() > static_cast<uint64_t>(std::numeric_limits<int64_t>::max()))
    {
        result->set_error_code(proto::SessionAuditList::INVALID_REQUEST);
        return true;
    }
    const uint32_t limit = request.limit() ? request.limit() : 200;
    Statement query(db_, "SELECT id,payload,state FROM audit WHERE (?=0 OR started_at>=?) "
        "AND (?=0 OR started_at<?) AND (?=0 OR started_at<? OR (started_at=? AND id<?)) "
        "AND (?='' OR user_name=?) AND (?=0 OR host_id=?) "
        "ORDER BY started_at DESC,id DESC LIMIT ?");
    if (!query || !query.integer(1, request.from_time()) || !query.integer(2, request.from_time()) ||
        !query.integer(3, request.to_time()) || !query.integer(4, request.to_time()) ||
        !query.integer(5, request.before_id()) || !query.integer(6, request.before_started_at()) ||
        !query.integer(7, request.before_started_at()) || !query.integer(8, request.before_id()) ||
        !query.text(9, request.user_name()) || !query.text(10, request.user_name()) ||
        !query.integer(11, static_cast<int64_t>(request.host_id())) ||
        !query.integer(12, static_cast<int64_t>(request.host_id())) || !query.integer(13, limit + 1))
        return false;
    int step = SQLITE_DONE;
    while ((step = query.step()) == SQLITE_ROW)
    {
        if (result->record_size() == static_cast<int>(limit))
        {
            const auto& last = result->record(result->record_size() - 1);
            result->set_next_before_id(last.id());
            result->set_next_before_started_at(last.started_at());
            return true;
        }
        proto::SessionAuditRecord* record = result->add_record();
        if (!query.record(1, record))
            return false;
        record->set_id(query.integer(0));
        record->set_state(static_cast<proto::SessionAuditRecord::State>(query.integer(2)));
    }
    return step == SQLITE_DONE;
}

bool SessionAuditStore::interruptAll()
{
    return execute(db_, "UPDATE audit SET state=3 WHERE state=1");
}

bool SessionAuditStore::interruptHost(uint64_t host_id)
{
    Statement query(db_, "UPDATE audit SET state=3 WHERE state=1 AND host_id=?");
    return query && query.integer(1, static_cast<int64_t>(host_id)) && query.step() == SQLITE_DONE;
}

bool SessionAuditStore::observeHost(uint64_t host_id, const std::string& name, const std::string& os,
                                  const std::string& address, int64_t now, bool online)
{
    if (!fitsId(host_id) || !bounded(name, 1024) || !bounded(os, 1024) ||
        !bounded(address, 256) || now <= 0)
        return false;
    Statement query(db_, "INSERT INTO presence(host_id,name,os,address,first_seen,last_seen,online) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(host_id) DO UPDATE SET name=excluded.name,os=excluded.os,"
        "address=excluded.address,last_seen=excluded.last_seen,online=excluded.online");
    return query && query.integer(1, static_cast<int64_t>(host_id)) && query.text(2, name) &&
        query.text(3, os) && query.text(4, address) && query.integer(5, now) &&
        query.integer(6, now) && query.integer(7, online ? 1 : 0) && query.step() == SQLITE_DONE;
}

bool SessionAuditStore::resetPresence()
{
    return execute(db_, "UPDATE presence SET online=0");
}

bool SessionAuditStore::presenceList(const proto::HostPresenceRequest& request,
                                   proto::HostPresenceList* result)
{
    result->Clear();
    result->set_request_id(request.request_id());
    if (request.after_host_id() < 0 || request.limit() > 500)
    {
        result->set_error_code(proto::HostPresenceList::INVALID_REQUEST);
        return true;
    }
    const uint32_t limit = request.limit() ? request.limit() : 200;
    Statement query(db_, "SELECT host_id,name,os,address,first_seen,last_seen,online "
        "FROM presence WHERE host_id>? ORDER BY host_id LIMIT ?");
    if (!query || !query.integer(1, request.after_host_id()) || !query.integer(2, limit + 1))
        return false;
    int step = SQLITE_DONE;
    while ((step = query.step()) == SQLITE_ROW)
    {
        if (result->host_size() == static_cast<int>(limit))
        {
            result->set_next_after_host_id(static_cast<int64_t>(
                result->host(result->host_size() - 1).host_id()));
            return true;
        }
        proto::HostPresence* host = result->add_host();
        host->set_host_id(static_cast<uint64_t>(query.integer(0)));
        host->set_computer_name(query.text(1));
        host->set_os_name(query.text(2));
        host->set_address(query.text(3));
        host->set_first_seen(query.integer(4));
        host->set_last_seen(query.integer(5));
        host->set_online(query.integer(6) != 0);
    }
    return step == SQLITE_DONE;
}

bool SessionAuditStore::queue(proto::SessionAuditRecord* record)
{
    if (record->event_id().size() != 16 || !fitsId(record->host_id()) || record->ByteSizeLong() > 8192)
        return false;
    int64_t previous = 0;
    {
        Statement query(db_, "SELECT revision FROM outbox WHERE event_id=?");
        if (!query || !query.blob(1, record->event_id()))
            return false;
        int step = query.step();
        if (step != SQLITE_ROW && step != SQLITE_DONE)
            return false;
        previous = step == SQLITE_ROW ? query.integer(0) : 0;
    }
    if (previous >= std::numeric_limits<int64_t>::max() - 1)
        return false;
    record->set_revision(static_cast<uint64_t>(previous + 1));
    Statement write(db_, "INSERT INTO outbox(event_id,host_id,revision,state,dirty,payload) "
        "VALUES(?,?,?,?,1,?) ON CONFLICT(event_id) DO UPDATE SET "
        "revision=excluded.revision,state=excluded.state,dirty=1,payload=excluded.payload");
    return write && write.blob(1, record->event_id()) &&
        write.integer(2, static_cast<int64_t>(record->host_id())) &&
        write.integer(3, static_cast<int64_t>(record->revision())) && write.integer(4, record->state()) &&
        write.blob(5, record->SerializeAsString()) && write.step() == SQLITE_DONE;
}

bool SessionAuditStore::interruptOutbox()
{
    std::vector<proto::SessionAuditRecord> records;
    {
        Statement query(db_, "SELECT payload FROM outbox WHERE state=1");
        if (!query)
            return false;
        int step = SQLITE_DONE;
        while ((step = query.step()) == SQLITE_ROW)
        {
            proto::SessionAuditRecord record;
            if (!query.record(0, &record))
                return false;
            records.push_back(std::move(record));
        }
        if (step != SQLITE_DONE)
            return false;
    }
    for (auto& record : records)
    {
        record.set_state(proto::SessionAuditRecord::INTERRUPTED);
        record.set_ended_at(0);
        if (!queue(&record))
            return false;
    }
    return true;
}

bool SessionAuditStore::acknowledge(const proto::SessionAuditAck& ack)
{
    if (!ack.accepted() || ack.event_id().size() != 16 || !fitsId(ack.revision()))
        return false;
    Statement remove(db_, "DELETE FROM outbox WHERE event_id=? AND revision=? AND state<>1");
    Statement clean(db_, "UPDATE outbox SET dirty=0 WHERE event_id=? AND revision=? AND state=1");
    return remove && clean && remove.blob(1, ack.event_id()) &&
        remove.integer(2, static_cast<int64_t>(ack.revision())) && remove.step() == SQLITE_DONE &&
        clean.blob(1, ack.event_id()) && clean.integer(2, static_cast<int64_t>(ack.revision())) &&
        clean.step() == SQLITE_DONE;
}

bool SessionAuditStore::defer(const proto::SessionAuditAck& ack)
{
    Statement update(db_, "UPDATE outbox SET dirty=2 WHERE event_id=? AND revision=?");
    return update && update.blob(1, ack.event_id()) &&
        update.integer(2, static_cast<int64_t>(ack.revision())) && update.step() == SQLITE_DONE;
}

bool SessionAuditStore::retryDeferred()
{
    return execute(db_, "UPDATE outbox SET dirty=1 WHERE dirty=2");
}

std::vector<proto::SessionAuditRecord> SessionAuditStore::pending(uint64_t host_id, size_t limit)
{
    std::vector<proto::SessionAuditRecord> records;
    Statement query(db_, "SELECT payload FROM outbox WHERE host_id=? AND dirty=1 ORDER BY rowid LIMIT ?");
    if (!query || !query.integer(1, static_cast<int64_t>(host_id)) ||
        !query.integer(2, static_cast<int64_t>(std::min<size_t>(limit, 100))))
        return records;
    while (query.step() == SQLITE_ROW)
    {
        proto::SessionAuditRecord record;
        if (query.record(0, &record))
            records.push_back(std::move(record));
    }
    return records;
}

} // namespace common
