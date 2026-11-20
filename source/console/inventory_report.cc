// Aspia Project
// SPDX-License-Identifier: GPL-3.0-or-later

#include "console/inventory_report.h"

#include <QCryptographicHash>
#include <QJsonArray>
#include <QJsonDocument>

#include <functional>
#include <limits>

namespace console {

namespace {

quint64 hostId(const QString& address)
{
    if (address.isEmpty())
        return 0;
    for (QChar c : address)
    {
        if (c < QLatin1Char('0') || c > QLatin1Char('9'))
            return 0;
    }
    bool ok = false;
    quint64 id = address.toULongLong(&ok);
    return ok ? id : 0;
}

} // namespace

QString inventoryEndpointKey(const client::Config& config)
{
    const QString address = QString::fromStdU16String(config.address_or_id);
    const quint64 id = hostId(address);
    QJsonArray parts;
    if (id)
    {
        parts.append(QStringLiteral("router"));
        parts.append(config.router_config
                         ? QString::fromStdU16String(config.router_config->address).toLower()
                         : QString());
        parts.append(config.router_config ? config.router_config->port : 0);
        parts.append(QString::number(id));
    }
    else
    {
        parts.append(QStringLiteral("direct"));
        parts.append(address.toLower());
        parts.append(config.port);
    }
    return QString::fromLatin1(QCryptographicHash::hash(
        QJsonDocument(parts).toJson(QJsonDocument::Compact), QCryptographicHash::Sha256).toHex());
}

QVector<InventoryTarget> inventoryTargets(const proto::address_book::ComputerGroup& root,
                                         const std::optional<client::RouterConfig>& router,
                                         const std::string& display_name)
{
    QVector<InventoryTarget> result;
    std::function<void(const proto::address_book::ComputerGroup&, const QString&,
                       const std::string&, const std::string&)> visit;
    visit = [&](const proto::address_book::ComputerGroup& group, const QString& parent_path,
                const std::string& inherited_username, const std::string& inherited_password)
    {
        QString path = parent_path;
        if (!group.name().empty())
        {
            if (!path.isEmpty())
                path += QStringLiteral(" / ");
            path += QString::fromStdString(group.name());
        }
        const auto& group_config = group.config();
        const bool own_credentials = group.has_config() && !group_config.inherit().credentials();
        const std::string& username = own_credentials ? group_config.username() : inherited_username;
        const std::string& password = own_credentials ? group_config.password() : inherited_password;
        for (const auto& computer : group.computer())
        {
            InventoryTarget target;
            target.name = QString::fromStdString(computer.name());
            target.group = path;
            target.address = QString::fromStdString(computer.address());
            target.host_id = hostId(target.address);
            target.config.router_config = router;
            target.config.computer_name = target.name.toStdU16String();
            target.config.display_name = QString::fromStdString(display_name).toStdU16String();
            target.config.address_or_id = target.address.toStdU16String();
            target.config.port = static_cast<uint16_t>(computer.port());
            target.config.session_type = proto::SESSION_TYPE_SYSTEM_INFO;
            const bool inherit = computer.has_inherit() && computer.inherit().credentials();
            target.config.username = QString::fromStdString(
                inherit ? username : computer.username()).toStdU16String();
            target.config.password = QString::fromStdString(
                inherit ? password : computer.password()).toStdU16String();
            target.key = inventoryEndpointKey(target.config);
            result.append(std::move(target));
        }
        for (const auto& child : group.computer_group())
            visit(child, path, username, password);
    };
    visit(root, QString(), std::string(), std::string());
    return result;
}

QMap<quint64, QString> inventoryComputerAliases(
    const proto::address_book::ComputerGroup& root)
{
    QMap<quint64, QStringList> names;
    for (const auto& target : inventoryTargets(root, std::nullopt, std::string()))
    {
        if (!target.host_id)
            continue;
        const QString name = target.group.isEmpty() ? target.name
            : target.group + QStringLiteral(" / ") + target.name;
        if (!names[target.host_id].contains(name))
            names[target.host_id].append(name);
    }
    QMap<quint64, QString> result;
    for (auto it = names.cbegin(); it != names.cend(); ++it)
        result.insert(it.key(), it.value().join(QStringLiteral("; ")));
    return result;
}

QJsonObject inventorySummary(const proto::system_info::SystemInfo& info, qint64 collected_at)
{
    if (!info.has_computer() || !info.has_processor() ||
        info.memory().module_size() > 256 || info.logical_drives().drive_size() > 256)
        return {};

    QJsonObject result;
    result.insert(QStringLiteral("collected_at"), QString::number(collected_at));
    result.insert(QStringLiteral("computer_name"), QString::fromStdString(info.computer().name()));
    result.insert(QStringLiteral("domain"), QString::fromStdString(info.computer().domain()));
    result.insert(QStringLiteral("os_name"), QString::fromStdString(info.operating_system().name()));
    result.insert(QStringLiteral("os_version"), QString::fromStdString(info.operating_system().version()));
    result.insert(QStringLiteral("os_arch"), QString::fromStdString(info.operating_system().arch()));
    result.insert(QStringLiteral("cpu_model"), QString::fromStdString(info.processor().model()));
    result.insert(QStringLiteral("cpu_cores"), static_cast<double>(info.processor().cores()));
    result.insert(QStringLiteral("cpu_threads"), static_cast<double>(info.processor().threads()));
    result.insert(QStringLiteral("cpu_packages"), static_cast<double>(info.processor().packages()));
    result.insert(QStringLiteral("board_manufacturer"), QString::fromStdString(info.motherboard().manufacturer()));
    result.insert(QStringLiteral("board_model"), QString::fromStdString(info.motherboard().model()));

    quint64 memory = 0;
    for (const auto& module : info.memory().module())
    {
        if (!module.present())
            continue;
        if (module.size() > std::numeric_limits<quint64>::max() - memory)
            return {};
        memory += module.size();
    }
    result.insert(QStringLiteral("ram_bytes"), QString::number(memory));

    QJsonArray volumes;
    for (const auto& drive : info.logical_drives().drive())
    {
        QJsonObject volume;
        volume.insert(QStringLiteral("path"), QString::fromStdString(drive.path()));
        volume.insert(QStringLiteral("file_system"), QString::fromStdString(drive.file_system()));
        volume.insert(QStringLiteral("total_bytes"), QString::number(drive.total_size()));
        volume.insert(QStringLiteral("free_bytes"), QString::number(drive.free_size()));
        volumes.append(volume);
    }
    result.insert(QStringLiteral("logical_volumes"), volumes);
    return result;
}

QJsonObject inventorySummary(const proto::InventorySnapshot& info)
{
    QJsonObject result;
    result.insert(QStringLiteral("collected_at"), QString::number(info.collected_at()));
    result.insert(QStringLiteral("received_at"), QString::number(info.received_at()));
    result.insert(QStringLiteral("computer_name"), QString::fromStdString(info.computer_name()));
    result.insert(QStringLiteral("os_name"), QString::fromStdString(info.os_name()));
    result.insert(QStringLiteral("os_version"), QString::fromStdString(info.os_version()));
    result.insert(QStringLiteral("os_arch"), QString::fromStdString(info.os_arch()));
    result.insert(QStringLiteral("cpu_model"), QString::fromStdString(info.cpu_model()));
    result.insert(QStringLiteral("cpu_cores"), static_cast<double>(info.cpu_cores()));
    result.insert(QStringLiteral("cpu_threads"), static_cast<double>(info.cpu_threads()));
    result.insert(QStringLiteral("cpu_packages"), static_cast<double>(info.cpu_packages()));
    result.insert(QStringLiteral("cpu_clock_mhz"), static_cast<double>(info.cpu_clock_mhz()));
    result.insert(QStringLiteral("ram_bytes"), QString::number(info.ram_bytes()));
    result.insert(QStringLiteral("ram_source"), QString::fromStdString(info.ram_source()));
    result.insert(QStringLiteral("board_manufacturer"), QString::fromStdString(info.board_manufacturer()));
    result.insert(QStringLiteral("board_model"), QString::fromStdString(info.board_model()));
    result.insert(QStringLiteral("collection_note"), QString::fromStdString(info.collection_note()));
    QJsonArray volumes;
    for (const auto& item : info.volumes())
    {
        QJsonObject volume;
        volume.insert(QStringLiteral("path"), QString::fromStdString(item.path()));
        volume.insert(QStringLiteral("file_system"), QString::fromStdString(item.file_system()));
        volume.insert(QStringLiteral("total_bytes"), QString::number(item.total_bytes()));
        volume.insert(QStringLiteral("free_bytes"), QString::number(item.free_bytes()));
        volumes.append(volume);
    }
    result.insert(QStringLiteral("logical_volumes"), volumes);
    QJsonArray disks;
    for (const auto& item : info.disks())
    {
        QJsonObject disk;
        disk.insert(QStringLiteral("number"), static_cast<double>(item.device_number()));
        disk.insert(QStringLiteral("model"), QString::fromStdString(item.model()));
        disk.insert(QStringLiteral("size_bytes"), QString::number(item.size_bytes()));
        disk.insert(QStringLiteral("media"), static_cast<int>(item.media()));
        disk.insert(QStringLiteral("evidence"), QString::fromStdString(item.media_evidence()));
        disks.append(disk);
    }
    result.insert(QStringLiteral("physical_disks"), disks);
    return result;
}

QString inventoryCsvCell(QString value)
{
    // Spreadsheet applications interpret these leading characters as formulas, even in quotes.
    const QString trimmed = value.trimmed();
    if (!trimmed.isEmpty() && (QStringLiteral("=+-@").contains(trimmed.front()) ||
                              (!value.isEmpty() && (value.front() == QLatin1Char('\t') ||
                                                   value.front() == QLatin1Char('\r') ||
                                                   value.front() == QLatin1Char('\n')))))
        value.prepend(QLatin1Char('\''));
    value.replace(QLatin1String("\""), QLatin1String("\"\""));
    return QLatin1Char('"') + value + QLatin1Char('"');
}

QByteArray inventoryCsvRow(const QStringList& fields)
{
    QStringList escaped;
    escaped.reserve(fields.size());
    for (const auto& field : fields)
        escaped.append(inventoryCsvCell(field));
    return (escaped.join(QLatin1Char(';')) + QStringLiteral("\r\n")).toUtf8();
}

bool inventoryTimestampIsStale(qint64 timestamp, qint64 now, int days)
{
    // Missing/future timestamps are unknown, never proof that a computer is inactive.
    return timestamp > 0 && timestamp <= now && days > 0 &&
           now - timestamp >= static_cast<qint64>(days) * 24 * 60 * 60;
}

} // namespace console
