// Copyright (C) 2026 Aspia+ contributors. GPL v3 or later.
#include "common/session_audit_store.h"

#include <gtest/gtest.h>
#include <chrono>
#include <filesystem>
#include <limits>

namespace common {
namespace {

constexpr int64_t kNow = 1800000000;

proto::SessionAuditRecord record(char id = 'a', uint64_t host = 42)
{
    proto::SessionAuditRecord r;
    r.set_event_id(std::string(16, id));
    r.set_host_id(host);
    r.set_user_name("ivanov");
    r.set_client_computer("WORK-PC");
    r.set_peer_address("192.0.2.1");
    r.set_session_type(1);
    r.set_started_at(kNow - 60);
    r.set_duration_seconds(60);
    r.set_state(proto::SessionAuditRecord::ACTIVE);
    r.set_revision(1);
    return r;
}

class SessionAuditStoreTest : public testing::Test
{
protected:
    void SetUp() override
    {
        store = SessionAuditStore::open(":memory:");
        ASSERT_TRUE(store);
    }
    proto::SessionAuditList list()
    {
        proto::SessionAuditList result;
        EXPECT_TRUE(store->auditList(proto::SessionAuditRequest(), &result));
        return result;
    }
    bool save(const proto::SessionAuditRecord& r)
    { return store->saveReport(r, kNow, "TARGET-PC", "192.0.2.2"); }
    std::unique_ptr<SessionAuditStore> store;
};

TEST_F(SessionAuditStoreTest, PersistsConfirmedLoginAndServerMetadata)
{
    auto r = record();
    r.set_id(999);
    r.set_host_name("spoofed");
    r.set_host_address("spoofed");
    r.set_last_seen(1);
    ASSERT_TRUE(save(r));
    const auto rows = list();
    ASSERT_EQ(rows.record_size(), 1);
    EXPECT_EQ(rows.record(0).id(), 1);
    EXPECT_EQ(rows.record(0).user_name(), "ivanov");
    EXPECT_EQ(rows.record(0).host_name(), "TARGET-PC");
    EXPECT_EQ(rows.record(0).host_address(), "192.0.2.2");
    EXPECT_EQ(rows.record(0).last_seen(), kNow);
}

TEST_F(SessionAuditStoreTest, DuplicateDoesNotCreateAnotherRow)
{
    ASSERT_TRUE(save(record()));
    ASSERT_TRUE(save(record()));
    EXPECT_EQ(list().record_size(), 1);
}

TEST_F(SessionAuditStoreTest, HostNamespaceSeparatesIdentifiers)
{
    ASSERT_TRUE(save(record('a', 1)));
    ASSERT_TRUE(save(record('a', 2)));
    EXPECT_EQ(list().record_size(), 2);
}

TEST_F(SessionAuditStoreTest, StaleRevisionCannotOverwriteEnd)
{
    auto r = record();
    ASSERT_TRUE(save(r));
    auto finished = r;
    finished.set_state(proto::SessionAuditRecord::FINISHED);
    finished.set_ended_at(kNow);
    finished.set_revision(2);
    ASSERT_TRUE(save(finished));
    ASSERT_TRUE(save(r));
    EXPECT_EQ(list().record(0).state(), proto::SessionAuditRecord::FINISHED);
    r.set_revision(3);
    EXPECT_FALSE(save(r));
}

TEST_F(SessionAuditStoreTest, ImmutableIdentityCannotChange)
{
    auto r = record();
    ASSERT_TRUE(save(r));
    r.set_revision(2);
    r.set_user_name("someone_else");
    EXPECT_FALSE(save(r));
    EXPECT_EQ(list().record(0).user_name(), "ivanov");
}

TEST_F(SessionAuditStoreTest, DurationCannotGoBackwards)
{
    auto r = record();
    ASSERT_TRUE(save(r));
    r.set_revision(2);
    r.set_duration_seconds(59);
    EXPECT_FALSE(save(r));
}

TEST_F(SessionAuditStoreTest, SnapshotNameSurvivesHostRename)
{
    auto r = record();
    ASSERT_TRUE(save(r));
    r.set_revision(2);
    ASSERT_TRUE(store->saveReport(r, kNow, "RENAMED-PC", "192.0.2.3"));
    EXPECT_EQ(list().record(0).host_name(), "TARGET-PC");
}

TEST_F(SessionAuditStoreTest, LostObservationDoesNotInventEndTime)
{
    auto r = record();
    ASSERT_TRUE(save(r));
    ASSERT_TRUE(store->interruptHost(r.host_id()));
    auto rows = list();
    ASSERT_EQ(rows.record_size(), 1);
    EXPECT_EQ(rows.record(0).state(), proto::SessionAuditRecord::INTERRUPTED);
    EXPECT_EQ(rows.record(0).ended_at(), 0);
    EXPECT_EQ(rows.record(0).duration_seconds(), 60);
    r.set_revision(2);
    ASSERT_TRUE(save(r));
    EXPECT_EQ(list().record(0).state(), proto::SessionAuditRecord::ACTIVE);
}

TEST_F(SessionAuditStoreTest, RouterRestartPreservesDurationAndReceipt)
{
    ASSERT_TRUE(save(record()));
    ASSERT_TRUE(store->interruptAll());
    const auto rows = list();
    EXPECT_EQ(rows.record(0).state(), proto::SessionAuditRecord::INTERRUPTED);
    EXPECT_EQ(rows.record(0).last_seen(), kNow);
    EXPECT_EQ(rows.record(0).duration_seconds(), 60);
}

TEST_F(SessionAuditStoreTest, RejectsMalformedOrOversizedReports)
{
    auto r = record();
    r.set_event_id("short");
    EXPECT_FALSE(save(r));
    r = record(); r.set_host_id(0); EXPECT_FALSE(save(r));
    r = record(); r.set_revision(0); EXPECT_FALSE(save(r));
    r = record(); r.set_user_name(""); EXPECT_FALSE(save(r));
    r = record(); r.set_user_name(std::string(257, 'x')); EXPECT_FALSE(save(r));
    r = record(); r.set_client_computer(std::string(1025, 'x')); EXPECT_FALSE(save(r));
    r = record(); r.set_session_type(3); EXPECT_FALSE(save(r));
    r = record(); r.set_session_type(32); EXPECT_FALSE(save(r));
    r = record(); r.set_user_name(std::string("a\0b", 3)); EXPECT_FALSE(save(r));
    r = record(); r.set_duration_seconds(std::numeric_limits<uint64_t>::max()); EXPECT_FALSE(save(r));
    EXPECT_EQ(list().record_size(), 0);
}

TEST_F(SessionAuditStoreTest, RejectsUnboundedFutureAndInvalidEndState)
{
    auto r = record();
    r.set_started_at(kNow + 86401); EXPECT_FALSE(save(r));
    r = record(); r.set_ended_at(kNow); EXPECT_FALSE(save(r));
    r = record(); r.set_state(proto::SessionAuditRecord::FINISHED); EXPECT_FALSE(save(r));
    r = record(); r.set_state(proto::SessionAuditRecord::UNKNOWN); EXPECT_FALSE(save(r));
}

TEST_F(SessionAuditStoreTest, WallClockAdjustmentDoesNotChangeMonotonicDuration)
{
    auto r = record();
    r.set_state(proto::SessionAuditRecord::FINISHED);
    r.set_ended_at(r.started_at() - 10); // NTP/manual clock correction.
    ASSERT_TRUE(save(r));
    EXPECT_EQ(list().record(0).duration_seconds(), 60);
}

TEST_F(SessionAuditStoreTest, StableCompositePagination)
{
    for (char id = 'a'; id <= 'e'; ++id)
        ASSERT_TRUE(save(record(id)));
    proto::SessionAuditRequest request;
    request.set_limit(2);
    request.set_request_id(91);
    proto::SessionAuditList first;
    ASSERT_TRUE(store->auditList(request, &first));
    ASSERT_EQ(first.record_size(), 2);
    EXPECT_EQ(first.request_id(), 91);
    EXPECT_EQ(first.record(0).event_id(), std::string(16, 'e'));
    request.set_before_id(first.next_before_id());
    request.set_before_started_at(first.next_before_started_at());
    proto::SessionAuditList second;
    ASSERT_TRUE(store->auditList(request, &second));
    ASSERT_EQ(second.record_size(), 2);
    EXPECT_EQ(second.record(0).event_id(), std::string(16, 'c'));
    request.set_before_id(second.next_before_id());
    request.set_before_started_at(second.next_before_started_at());
    proto::SessionAuditList third;
    ASSERT_TRUE(store->auditList(request, &third));
    ASSERT_EQ(third.record_size(), 1);
    EXPECT_EQ(third.next_before_id(), 0);
}

TEST_F(SessionAuditStoreTest, LateArrivalsAreOrderedByStartTime)
{
    auto recent = record('r');
    auto old = record('o');
    old.set_started_at(kNow - 1000);
    ASSERT_TRUE(save(recent));
    ASSERT_TRUE(save(old));
    EXPECT_EQ(list().record(0).event_id(), recent.event_id());
}

TEST_F(SessionAuditStoreTest, BoundedQueriesAndExactUserFilters)
{
    auto r = record();
    r.set_user_name("' OR 1=1 --");
    ASSERT_TRUE(save(r));
    ASSERT_TRUE(save(record('b', 43)));
    proto::SessionAuditRequest request;
    request.set_user_name(r.user_name());
    request.set_host_id(42);
    request.set_from_time(kNow - 60);
    request.set_to_time(kNow);
    proto::SessionAuditList result;
    ASSERT_TRUE(store->auditList(request, &result));
    EXPECT_EQ(result.record_size(), 1);
    request.set_limit(501);
    ASSERT_TRUE(store->auditList(request, &result));
    EXPECT_EQ(result.error_code(), proto::SessionAuditList::INVALID_REQUEST);
    request.set_limit(10); request.set_before_id(1);
    ASSERT_TRUE(store->auditList(request, &result));
    EXPECT_EQ(result.error_code(), proto::SessionAuditList::INVALID_REQUEST);
}

TEST_F(SessionAuditStoreTest, PresenceIsIndependentOfRemoteSessions)
{
    ASSERT_TRUE(store->observeHost(42, "OFFICE-PC", "Windows", "192.0.2.1", kNow, true));
    proto::HostPresenceList result;
    proto::HostPresenceRequest request;
    request.set_request_id(4);
    ASSERT_TRUE(store->presenceList(request, &result));
    ASSERT_EQ(result.host_size(), 1);
    EXPECT_TRUE(result.host(0).online());
    EXPECT_EQ(result.request_id(), 4);
    EXPECT_EQ(list().record_size(), 0);
    ASSERT_TRUE(store->observeHost(42, "OFFICE-PC", "Windows", "192.0.2.1", kNow + 60, false));
    ASSERT_TRUE(store->presenceList(request, &result));
    EXPECT_EQ(result.host(0).first_seen(), kNow);
    EXPECT_EQ(result.host(0).last_seen(), kNow + 60);
    EXPECT_FALSE(result.host(0).online());
}

TEST_F(SessionAuditStoreTest, PresenceRestartDoesNotInventNewLastSeen)
{
    ASSERT_TRUE(store->observeHost(42, "PC", "Windows", "192.0.2.1", kNow, true));
    ASSERT_TRUE(store->resetPresence());
    proto::HostPresenceList result;
    ASSERT_TRUE(store->presenceList(proto::HostPresenceRequest(), &result));
    EXPECT_FALSE(result.host(0).online());
    EXPECT_EQ(result.host(0).last_seen(), kNow);
}

TEST_F(SessionAuditStoreTest, PresencePaginationAndLimits)
{
    for (uint64_t i = 1; i <= 5; ++i)
        ASSERT_TRUE(store->observeHost(i, "PC", "Windows", "192.0.2.1", kNow, true));
    proto::HostPresenceRequest request;
    request.set_limit(2);
    proto::HostPresenceList result;
    ASSERT_TRUE(store->presenceList(request, &result));
    ASSERT_EQ(result.host_size(), 2);
    EXPECT_EQ(result.next_after_host_id(), 2);
    request.set_after_host_id(result.next_after_host_id());
    ASSERT_TRUE(store->presenceList(request, &result));
    EXPECT_EQ(result.host(0).host_id(), 3);
    request.set_limit(501);
    ASSERT_TRUE(store->presenceList(request, &result));
    EXPECT_EQ(result.error_code(), proto::HostPresenceList::INVALID_REQUEST);
}

TEST_F(SessionAuditStoreTest, ActiveAckRetainedForCrashRecovery)
{
    auto r = record();
    ASSERT_TRUE(store->queue(&r));
    proto::SessionAuditAck ack;
    ack.set_event_id(r.event_id()); ack.set_revision(r.revision()); ack.set_accepted(true);
    ASSERT_TRUE(store->acknowledge(ack));
    EXPECT_TRUE(store->pending(42, 100).empty());
    ASSERT_TRUE(store->interruptOutbox());
    auto pending = store->pending(42, 100);
    ASSERT_EQ(pending.size(), 1);
    EXPECT_EQ(pending[0].state(), proto::SessionAuditRecord::INTERRUPTED);
    EXPECT_EQ(pending[0].ended_at(), 0);
    EXPECT_GT(pending[0].revision(), ack.revision());
}

TEST_F(SessionAuditStoreTest, StaleAckCannotRemoveTerminalEvent)
{
    auto r = record();
    ASSERT_TRUE(store->queue(&r));
    proto::SessionAuditAck ack;
    ack.set_event_id(r.event_id()); ack.set_revision(r.revision()); ack.set_accepted(true);
    r.set_state(proto::SessionAuditRecord::FINISHED); r.set_ended_at(kNow);
    ASSERT_TRUE(store->queue(&r));
    ASSERT_TRUE(store->acknowledge(ack));
    ASSERT_EQ(store->pending(42, 100).size(), 1);
    ack.set_revision(r.revision());
    ASSERT_TRUE(store->acknowledge(ack));
    EXPECT_TRUE(store->pending(42, 100).empty());
}

TEST_F(SessionAuditStoreTest, NegativeAckKeepsPendingRecord)
{
    auto r = record();
    ASSERT_TRUE(store->queue(&r));
    proto::SessionAuditAck ack;
    ack.set_event_id(r.event_id()); ack.set_revision(r.revision());
    EXPECT_FALSE(store->acknowledge(ack));
    EXPECT_EQ(store->pending(42, 100).size(), 1);
    EXPECT_TRUE(store->pending(43, 100).empty());
}

TEST_F(SessionAuditStoreTest, DeferredRejectionCannotStarveLaterRecords)
{
    auto first = record('a');
    auto second = record('b');
    ASSERT_TRUE(store->queue(&first));
    ASSERT_TRUE(store->queue(&second));
    proto::SessionAuditAck rejection;
    rejection.set_event_id(first.event_id());
    rejection.set_revision(first.revision());
    ASSERT_TRUE(store->defer(rejection));
    const auto pending = store->pending(42, 1);
    ASSERT_EQ(pending.size(), 1);
    EXPECT_EQ(pending[0].event_id(), second.event_id());
    ASSERT_TRUE(store->retryDeferred());
    EXPECT_EQ(store->pending(42, 100).size(), 2);
}

TEST(SessionAuditPersistenceTest, CommittedOutboxAndJournalSurviveReopen)
{
    const auto suffix = std::chrono::steady_clock::now().time_since_epoch().count();
    const std::filesystem::path path = std::filesystem::path(testing::TempDir()) /
        ("aspia-audit-" + std::to_string(suffix) + ".db3");
    {
        auto store = SessionAuditStore::open(path.string());
        ASSERT_TRUE(store);
        auto r = record();
        ASSERT_TRUE(store->queue(&r));
        ASSERT_TRUE(store->saveReport(r, kNow, "PC", "192.0.2.2"));
    }
    {
        auto store = SessionAuditStore::open(path.string());
        ASSERT_TRUE(store);
        EXPECT_EQ(store->pending(42, 100).size(), 1);
        proto::SessionAuditList result;
        ASSERT_TRUE(store->auditList(proto::SessionAuditRequest(), &result));
        EXPECT_EQ(result.record_size(), 1);
    }
    std::error_code error;
    std::filesystem::remove(path, error);
    std::filesystem::remove(path.string() + "-wal", error);
    std::filesystem::remove(path.string() + "-shm", error);
}

} // namespace
} // namespace common
