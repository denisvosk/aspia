// Aspia+ audit UI regression tests. GPL-3.0-or-later; see LICENSE.md.
#include "client/ui/router_manager/session_audit_helpers.h"
#include <gtest/gtest.h>

namespace client {
TEST(SessionAuditHelpers, MondayYesterdayDoesNotBecomeLastWeek)
{
    const QDate monday(2026, 11, 23);
    EXPECT_EQ(auditDateGroup(monday, monday), AuditDateGroup::TODAY);
    EXPECT_EQ(auditDateGroup(monday.addDays(-1), monday), AuditDateGroup::YESTERDAY);
    EXPECT_EQ(auditDateGroup(monday.addDays(-2), monday), AuditDateGroup::LAST_WEEK);
    EXPECT_EQ(auditDateGroup(monday.addDays(-8), monday), AuditDateGroup::EARLIER);
}

TEST(SessionAuditHelpers, LeapDayYearBoundaryAndFuture)
{
    EXPECT_EQ(auditDateGroup(QDate(2024, 2, 29), QDate(2024, 3, 1)), AuditDateGroup::YESTERDAY);
    EXPECT_EQ(auditDateGroup(QDate(2025, 12, 31), QDate(2026, 1, 1)), AuditDateGroup::YESTERDAY);
    EXPECT_EQ(auditDateGroup(QDate(2026, 11, 21), QDate(2026, 11, 20)), AuditDateGroup::FUTURE);
    EXPECT_EQ(auditDateGroup(QDate(2026, 11, 16), QDate(2026, 11, 20)), AuditDateGroup::THIS_WEEK);
}

TEST(SessionAuditHelpers, CsvBlocksFormulaInjectionWithoutDestroyingText)
{
    EXPECT_EQ(auditCsvCell(QStringLiteral("=1+1")), QStringLiteral("\"'=1+1\""));
    EXPECT_EQ(auditCsvCell(QStringLiteral("\t @SUM(A1)")), QStringLiteral("\"'\t @SUM(A1)\""));
    EXPECT_EQ(auditCsvCell(QStringLiteral("name;\"value\"\nnext")),
              QStringLiteral("\"name;\"\"value\"\"\nnext\""));
    EXPECT_EQ(auditCsvCell(QStringLiteral("12345")), QStringLiteral("\"12345\""));
}

TEST(SessionAuditHelpers, LongSessionsDoNotWrapAtMidnight)
{
    EXPECT_EQ(auditDuration(0), QStringLiteral("0:00:00"));
    EXPECT_EQ(auditDuration(90061), QStringLiteral("25:01:01"));
}
} // namespace client
