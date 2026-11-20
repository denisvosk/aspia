// Aspia+ audit UI helpers. GPL-3.0-or-later; see LICENSE.md.
#include "client/ui/router_manager/session_audit_helpers.h"

namespace client {

AuditDateGroup auditDateGroup(const QDate& date, const QDate& today)
{
    if (date > today)
        return AuditDateGroup::FUTURE;
    if (date == today)
        return AuditDateGroup::TODAY;
    if (date == today.addDays(-1))
        return AuditDateGroup::YESTERDAY;
    const QDate monday = today.addDays(1 - today.dayOfWeek());
    if (date >= monday)
        return AuditDateGroup::THIS_WEEK;
    if (date >= monday.addDays(-7))
        return AuditDateGroup::LAST_WEEK;
    return AuditDateGroup::EARLIER;
}

QString auditCsvCell(QString value)
{
    const QString trimmed = value.trimmed();
    if (!trimmed.isEmpty() && QStringLiteral("=+-@").contains(trimmed.front()))
        value.prepend(QLatin1Char('\''));
    value.replace(QLatin1Char('"'), QStringLiteral("\"\""));
    return QLatin1Char('"') + value + QLatin1Char('"');
}

QString auditDuration(quint64 seconds)
{
    // Total hours deliberately do not wrap at 24.
    return QStringLiteral("%1:%2:%3").arg(seconds / 3600)
        .arg((seconds / 60) % 60, 2, 10, QLatin1Char('0'))
        .arg(seconds % 60, 2, 10, QLatin1Char('0'));
}

} // namespace client
