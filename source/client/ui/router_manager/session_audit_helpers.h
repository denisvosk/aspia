// Aspia+ audit UI helpers. GPL-3.0-or-later; see LICENSE.md.
#ifndef CLIENT_UI_ROUTER_MANAGER_SESSION_AUDIT_HELPERS_H
#define CLIENT_UI_ROUTER_MANAGER_SESSION_AUDIT_HELPERS_H

#include <QDate>
#include <QString>

namespace client {

enum class AuditDateGroup { FUTURE, TODAY, YESTERDAY, THIS_WEEK, LAST_WEEK, EARLIER };

AuditDateGroup auditDateGroup(const QDate& date, const QDate& today);
// UTF-8 CSV still needs a text prefix for values which spreadsheet software
// could interpret as formulas, including formulas after leading whitespace.
QString auditCsvCell(QString value);
QString auditDuration(quint64 seconds);

} // namespace client
#endif
