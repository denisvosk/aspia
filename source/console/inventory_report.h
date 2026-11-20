// Aspia Project
// SPDX-License-Identifier: GPL-3.0-or-later

#ifndef CONSOLE_INVENTORY_REPORT_H
#define CONSOLE_INVENTORY_REPORT_H

#include "client/client_config.h"
#include "proto/address_book.pb.h"
#include "proto/system_info.pb.h"
#include "proto/inventory.pb.h"

#include <QJsonObject>
#include <QMap>
#include <QStringList>
#include <QVector>

namespace console {

struct InventoryTarget
{
    QString key;
    QString name;
    QString group;
    QString address;
    quint64 host_id = 0;
    client::Config config;
};

// The endpoint key is scoped to the router, not to a user name or a book alias.
// It identifies a configured endpoint; it is not a physical-machine serial number.
QString inventoryEndpointKey(const client::Config& config);
QVector<InventoryTarget> inventoryTargets(const proto::address_book::ComputerGroup& root,
                                         const std::optional<client::RouterConfig>& router,
                                         const std::string& display_name);
QMap<quint64, QString> inventoryComputerAliases(
    const proto::address_book::ComputerGroup& root);

// Only explicitly selected hardware fields are persisted. In particular, OS product keys,
// user credentials, unknown protobuf fields and the address-book contents are never serialized.
QJsonObject inventorySummary(const proto::system_info::SystemInfo& info, qint64 collected_at);
QJsonObject inventorySummary(const proto::InventorySnapshot& info);
QString inventoryCsvCell(QString value);
QByteArray inventoryCsvRow(const QStringList& fields);
bool inventoryTimestampIsStale(qint64 timestamp, qint64 now, int days);

} // namespace console

#endif // CONSOLE_INVENTORY_REPORT_H
