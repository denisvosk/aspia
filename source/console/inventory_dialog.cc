// Aspia Project
// SPDX-License-Identifier: GPL-3.0-or-later

#include "console/inventory_dialog.h"

#include "client/router.h"
#include "client/router_proxy.h"
#include "client/router_window_proxy.h"
#include "qt_base/application.h"

#include <QComboBox>
#include <QCryptographicHash>
#include <QDateTime>
#include <QDialogButtonBox>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QHeaderView>
#include <QJsonArray>
#include <QJsonDocument>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPushButton>
#include <QSaveFile>
#include <QSet>
#include <QStandardPaths>
#include <QSpinBox>
#include <QTimer>
#include <QTreeWidget>
#include <QVBoxLayout>

#include <functional>

namespace console {

namespace {

constexpr qint64 kGiB = 1024LL * 1024 * 1024;
constexpr qint64 kMaxCacheBytes = 16LL * 1024 * 1024;

QString dateText(qint64 seconds, bool utc)
{
    if (seconds <= 0)
        return QString();
    const QDateTime time = QDateTime::fromSecsSinceEpoch(seconds, Qt::UTC);
    return utc ? time.toString(Qt::ISODate) : time.toLocalTime().toString(QStringLiteral("dd.MM.yyyy HH:mm:ss"));
}

quint64 bytesValue(const QJsonObject& object, const char* field)
{
    return object.value(QLatin1String(field)).toString().toULongLong();
}

qint64 timeValue(const QJsonObject& object, const char* field)
{
    return object.value(QLatin1String(field)).toString().toLongLong();
}

QString gibText(quint64 bytes)
{
    return QString::number(static_cast<double>(bytes) / static_cast<double>(kGiB), 'f', 1);
}

QStringList reportHeaders(bool utc)
{
    const QString suffix = utc ? QStringLiteral(" (UTC)") : QString();
    return {
        InventoryDialog::tr("Book name"), InventoryDialog::tr("Group"),
        InventoryDialog::tr("Address / ID"), InventoryDialog::tr("System name"),
        InventoryDialog::tr("Activity evidence"), InventoryDialog::tr("Last seen by Router") + suffix,
        InventoryDialog::tr("Inventory collected") + suffix, InventoryDialog::tr("Received by Router") + suffix,
        InventoryDialog::tr("Processor"),
        InventoryDialog::tr("Cores"), InventoryDialog::tr("Threads"),
        InventoryDialog::tr("CPU clock, MHz"), InventoryDialog::tr("RAM, GiB"),
        InventoryDialog::tr("Physical disks: model, type, GiB"),
        InventoryDialog::tr("Logical volumes, total / free GiB"),
        InventoryDialog::tr("Operating system"), InventoryDialog::tr("Review reasons"),
        InventoryDialog::tr("Collection notes")
    };
}

} // namespace

InventoryDialog::InventoryDialog(const proto::address_book::ComputerGroup& root,
                                 const QString& book_guid, const QString& book_name,
                                 const std::string& display_name,
                                 const std::optional<client::RouterConfig>& router_config,
                                 QWidget* parent)
    : QDialog(parent), targets_(inventoryTargets(root, router_config, display_name)),
      router_config_(router_config), book_name_(book_name)
{
    setWindowTitle(tr("Equipment report") + QStringLiteral(" — ") + book_name_);
    resize(1320, 760);
    auto layout = new QVBoxLayout(this);
    auto note = new QLabel(tr("A snapshot of this address book. Router activity and hardware collection "
        "are separate observations. Missing data is not proof that a computer was retired. "
        "Times are local on screen and UTC in CSV."), this);
    note->setWordWrap(true);
    layout->addWidget(note);

    auto controls = new QHBoxLayout;
    presence_button_ = new QPushButton(tr("Refresh report"), this);
    controls->addWidget(presence_button_);
    controls->addStretch();
    controls->addWidget(new QLabel(tr("Review after:"), this));
    age_ = new QComboBox(this);
    for (int days : {30, 60, 90})
        age_->addItem(tr("%1 days").arg(days), days);
    controls->addWidget(age_);
    search_ = new QLineEdit(this);
    search_->setPlaceholderText(tr("Find computer, group, processor..."));
    controls->addWidget(search_);
    layout->addLayout(controls);
    auto criteria = new QHBoxLayout;
    criteria->addWidget(new QLabel(tr("Review criteria:"), this));
    criteria->addWidget(new QLabel(tr("RAM below, GiB"), this));
    ram_min_ = new QSpinBox(this);
    ram_min_->setRange(1, 1024); ram_min_->setValue(8);
    criteria->addWidget(ram_min_);
    criteria->addWidget(new QLabel(tr("Fewer CPU cores than"), this));
    cores_min_ = new QSpinBox(this);
    cores_min_->setRange(1, 256); cores_min_->setValue(4);
    criteria->addWidget(cores_min_);
    criteria->addWidget(new QLabel(tr("Volume free space below, %"), this));
    free_min_ = new QSpinBox(this);
    free_min_->setRange(1, 99); free_min_->setValue(10);
    criteria->addWidget(free_min_);
    criteria->addStretch();
    layout->addLayout(criteria);

    counts_ = new QLabel(this);
    presence_status_ = new QLabel(this);
    cache_status_ = new QLabel(this);
    cache_status_->setWordWrap(true);
    layout->addWidget(counts_);
    layout->addWidget(presence_status_);
    layout->addWidget(cache_status_);
    table_ = new QTreeWidget(this);
    table_->setHeaderLabels(reportHeaders(false));
    table_->setRootIsDecorated(true);
    table_->setUniformRowHeights(true);
    table_->setAlternatingRowColors(true);
    table_->setSelectionMode(QAbstractItemView::ExtendedSelection);
    table_->header()->setStretchLastSection(false);
    layout->addWidget(table_);

    auto limits = new QLabel(tr("Updated Hosts send a summary automatically at startup and daily; "
        "the Console does not have to remain open. Old Hosts and direct addresses without a Router ID "
        "can have no central inventory. SSD/HDD is reported by the storage driver; unknown types stay unknown. "
        "Physical disks and logical volumes are separate. Review flags are not replacement decisions."), this);
    limits->setWordWrap(true);
    layout->addWidget(limits);
    auto buttons = new QDialogButtonBox(QDialogButtonBox::Close, this);
    auto export_button = buttons->addButton(tr("Export visible rows to CSV"), QDialogButtonBox::ActionRole);
    auto html_button = buttons->addButton(tr("Export management report"), QDialogButtonBox::ActionRole);
    layout->addWidget(buttons);
    connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
    connect(export_button, &QPushButton::clicked, this, &InventoryDialog::exportCsv);
    connect(html_button, &QPushButton::clicked, this, &InventoryDialog::exportHtml);
    connect(presence_button_, &QPushButton::clicked, this, &InventoryDialog::refreshPresence);
    connect(search_, &QLineEdit::textChanged, this, &InventoryDialog::rebuildTable);
    connect(age_, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &InventoryDialog::rebuildTable);
    for (auto field : {ram_min_, cores_min_, free_min_})
        connect(field, QOverload<int>::of(&QSpinBox::valueChanged), this, &InventoryDialog::rebuildTable);

    if (!book_guid.isEmpty())
    {
        const QString folder = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
        if (!folder.isEmpty())
        {
            const QString digest = QString::fromLatin1(QCryptographicHash::hash(
                book_guid.toUtf8(), QCryptographicHash::Sha256).toHex());
            cache_path_ = QDir(folder).filePath(QStringLiteral("inventory/") + digest + QStringLiteral(".json"));
        }
    }
    loadCache();
    rebuildTable();
    table_->expandAll();
    table_->setColumnWidth(0, 210);
    for (int column : {1, 3, 4, 5, 6, 7, 8, 13, 14, 15, 16, 17})
        table_->setColumnWidth(column, 190);
    for (int column : {9, 10, 11, 12})
        table_->setColumnWidth(column, 85);

    presence_timer_ = new QTimer(this);
    presence_timer_->setSingleShot(true);
    connect(presence_timer_, &QTimer::timeout, this, [this]()
    {
        finishPresence(tr("Router did not respond within 20 seconds. Cached data is retained."));
    });
    QTimer::singleShot(0, this, &InventoryDialog::refreshPresence);
}

InventoryDialog::~InventoryDialog()
{
    if (router_window_proxy_)
        router_window_proxy_->dettach();
    router_proxy_.reset();
}

void InventoryDialog::loadCache()
{
    if (cache_path_.isEmpty())
    {
        cache_status_->setText(tr("This book has no stable ID; inventory will remain in this window only."));
        return;
    }
    QFile file(cache_path_);
    if (!file.exists())
        return;
    if (!file.open(QIODevice::ReadOnly) || file.size() > kMaxCacheBytes)
    {
        cache_status_->setText(tr("Saved inventory could not be read. No data was discarded."));
        return;
    }
    QJsonParseError error;
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &error);
    if (error.error != QJsonParseError::NoError || !document.isObject() ||
        document.object().value(QStringLiteral("version")).toInt() != 1)
    {
        cache_status_->setText(tr("Saved inventory is invalid or uses an unsupported format."));
        return;
    }
    const QJsonObject entries = document.object().value(QStringLiteral("entries")).toObject();
    for (const auto& target : targets_)
    {
        const QJsonObject entry = entries.value(target.key).toObject();
        if (entry.contains(QStringLiteral("summary")))
            snapshots_.insert(target.key, entry.value(QStringLiteral("summary")).toObject());
        if (entry.contains(QStringLiteral("presence")))
            presence_.insert(target.key, entry.value(QStringLiteral("presence")).toObject());
    }
}

void InventoryDialog::saveCache()
{
    if (cache_path_.isEmpty())
        return;
    QJsonObject entries;
    for (const auto& target : targets_)
    {
        QJsonObject entry;
        if (snapshots_.contains(target.key))
            entry.insert(QStringLiteral("summary"), snapshots_.value(target.key));
        if (presence_.contains(target.key))
            entry.insert(QStringLiteral("presence"), presence_.value(target.key));
        if (!entry.isEmpty())
            entries.insert(target.key, entry);
    }
    QJsonObject root;
    root.insert(QStringLiteral("version"), 1);
    root.insert(QStringLiteral("entries"), entries);
    const QByteArray bytes = QJsonDocument(root).toJson(QJsonDocument::Compact);
    if (bytes.size() > kMaxCacheBytes || !QDir().mkpath(QFileInfo(cache_path_).absolutePath()))
    {
        cache_status_->setText(tr("Could not save inventory. The previous saved snapshot is unchanged."));
        return;
    }
    QSaveFile file(cache_path_);
    if (!file.open(QIODevice::WriteOnly))
    {
        cache_status_->setText(tr("Could not save inventory. The previous saved snapshot is unchanged."));
        return;
    }
    file.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
    if (file.write(bytes) != bytes.size() || !file.commit())
    {
        cache_status_->setText(tr("Could not save inventory. The previous saved snapshot is unchanged."));
        return;
    }
    cache_status_->clear();
}

void InventoryDialog::refreshPresence()
{
    if (presence_loading_)
        return;
    if (!router_config_ || !router_config_->isValid())
    {
        presence_status_->setText(tr("No Router credentials. Configure the Router in this address book to load automatic reports."));
        return;
    }
    presence_loading_ = true;
    request_elapsed_.start();
    presence_supported_ = false;
    inventory_supported_ = false;
    inventory_cursor_ = 0;
    inventory_count_ = 0;
    presence_cursor_ = 0;
    presence_count_ = 0;
    live_online_.clear();
    presence_observed_at_ = 0;
    presence_button_->setEnabled(false);
    if (router_window_proxy_)
        router_window_proxy_->dettach();
    router_window_proxy_ = std::make_shared<client::RouterWindowProxy>(
        qt_base::Application::uiTaskRunner(), this);
    auto router = std::make_unique<client::Router>(
        router_window_proxy_, qt_base::Application::ioTaskRunner());
    router->setUserName(router_config_->username);
    router->setPassword(router_config_->password);
    router->setAutoReconnect(false);
    router_proxy_ = std::make_unique<client::RouterProxy>(
        qt_base::Application::ioTaskRunner(), std::move(router));
    presence_timer_->start(20000);
    router_proxy_->connectToRouter(router_config_->address, router_config_->port);
}

void InventoryDialog::finishPresence(const QString& result)
{
    if (!presence_loading_)
        return;
    presence_loading_ = false;
    presence_timer_->stop();
    presence_button_->setEnabled(true);
    presence_status_->setText(result);
    if (router_window_proxy_)
        router_window_proxy_->dettach();
    router_proxy_.reset();
    saveCache();
    rebuildTable();
}

void InventoryDialog::onConnecting()
{
    presence_status_->setText(tr("Requesting central activity history..."));
}

void InventoryDialog::onConnected(const base::Version&)
{
    if (router_proxy_ && presence_loading_)
        router_proxy_->refreshSessionList();
}

void InventoryDialog::onSessionList(std::shared_ptr<proto::SessionList> list)
{
    if (!presence_loading_ || !router_proxy_)
        return;
    presence_timer_->start(20000);
    if (list->error_code() != proto::SessionList::SUCCESS)
    {
        finishPresence(tr("Router could not read activity history."));
        return;
    }
    presence_supported_ = list->host_presence_supported();
    inventory_supported_ = list->inventory_supported();
    if (presence_supported_)
    {
        proto::HostPresenceRequest request;
        request.set_limit(500);
        request.set_request_id(1);
        router_proxy_->refreshHostPresence(request);
    }
    else
    {
        requestInventory();
    }
}

void InventoryDialog::onHostPresenceList(std::shared_ptr<proto::HostPresenceList> list)
{
    if (!presence_loading_ || !presence_supported_ || !router_proxy_ || list->request_id() != 1)
        return;
    if (request_elapsed_.elapsed() > 120000)
    {
        finishPresence(tr("Central report exceeded the two-minute time limit; refresh to try again."));
        return;
    }
    presence_timer_->start(20000);
    if (list->error_code() != proto::HostPresenceList::SUCCESS)
    {
        finishPresence(tr("Router could not read activity history."));
        return;
    }
    const qint64 now = QDateTime::currentSecsSinceEpoch();
    for (const auto& host : list->host())
    {
        ++presence_count_;
        for (const auto& target : targets_)
        {
            if (!target.host_id || target.host_id != host.host_id())
                continue;
            QJsonObject entry;
            entry.insert(QStringLiteral("last_seen"), QString::number(host.last_seen()));
            entry.insert(QStringLiteral("first_seen"), QString::number(host.first_seen()));
            entry.insert(QStringLiteral("computer_name"), QString::fromStdString(host.computer_name()));
            presence_.insert(target.key, entry);
            live_online_.insert(target.host_id, host.online());
        }
    }
    const qint64 next = list->next_after_host_id();
    if (next > 0)
    {
        if (next <= presence_cursor_ || presence_count_ > 100000)
        {
            finishPresence(tr("Router returned invalid activity pagination."));
            return;
        }
        presence_cursor_ = next;
        proto::HostPresenceRequest request;
        request.set_limit(500);
        request.set_after_host_id(next);
        request.set_request_id(1);
        router_proxy_->refreshHostPresence(request);
        return;
    }
    presence_observed_at_ = now;
    requestInventory();
}

void InventoryDialog::requestInventory()
{
    if (!inventory_supported_)
    {
        finishPresence(tr("This Router does not provide automatic inventory. Update Router and Hosts to use it."));
        return;
    }
    proto::InventoryRequest request;
    request.set_limit(100);
    request.set_after_host_id(inventory_cursor_);
    request.set_request_id(2);
    router_proxy_->refreshInventory(request);
}

void InventoryDialog::onInventoryList(std::shared_ptr<proto::InventoryList> list)
{
    if (!presence_loading_ || !router_proxy_ || !inventory_supported_ || list->request_id() != 2)
        return;
    if (request_elapsed_.elapsed() > 120000)
    {
        finishPresence(tr("Central report exceeded the two-minute time limit; refresh to try again."));
        return;
    }
    presence_timer_->start(20000);
    if (list->error_code() != proto::InventoryList::SUCCESS)
    {
        finishPresence(tr("Router could not read automatic inventory. Cached summaries are retained."));
        return;
    }
    for (const auto& snapshot : list->inventory())
    {
        ++inventory_count_;
        for (const auto& target : targets_)
        {
            if (target.host_id && target.host_id == snapshot.host_id())
                snapshots_.insert(target.key, inventorySummary(snapshot));
        }
    }
    const qint64 next = list->next_after_host_id();
    if (next > 0)
    {
        if (next <= inventory_cursor_ || inventory_count_ > 100000)
        {
            finishPresence(tr("Router returned invalid inventory pagination."));
            return;
        }
        inventory_cursor_ = next;
        requestInventory();
        return;
    }
    finishPresence(tr("Central report loaded at %1. Hosts collect it automatically; no per-computer connection is needed.")
        .arg(dateText(QDateTime::currentSecsSinceEpoch(), false)));
}

void InventoryDialog::onDisconnected(base::TcpChannel::ErrorCode code)
{
    finishPresence(tr("Router connection ended (code %1). Cached evidence is retained.").arg(static_cast<int>(code)));
}
void InventoryDialog::onWaitForRouter() {}
void InventoryDialog::onWaitForRouterTimeout() { finishPresence(tr("Router timeout. Cached evidence is retained.")); }
void InventoryDialog::onVersionMismatch(const base::Version&, const base::Version&)
{
    finishPresence(tr("Incompatible Router version."));
}
void InventoryDialog::onAccessDenied(base::ClientAuthenticator::ErrorCode code)
{
    finishPresence(tr("Router administrator access denied (code %1). Use an administrator account in the address-book Router settings.")
                       .arg(static_cast<int>(code)));
}

QString InventoryDialog::activity(const InventoryTarget& target) const
{
    const qint64 now = QDateTime::currentSecsSinceEpoch();
    if (presence_observed_at_ > 0 && now - presence_observed_at_ < 60 &&
        live_online_.contains(target.host_id) && live_online_.value(target.host_id))
        return tr("Online at last Router check");
    const qint64 last_seen = timeValue(presence_.value(target.key), "last_seen");
    if (last_seen > now || last_seen < 0)
        return tr("Router clock differs; check time");
    if (last_seen == 0)
        return tr("No Router history");
    if (inventoryTimestampIsStale(last_seen, now, age_->currentData().toInt()))
        return tr("Not observed for at least %1 days").arg(age_->currentData().toInt());
    return tr("Observed within %1 days").arg(age_->currentData().toInt());
}

QString InventoryDialog::reviewReasons(const QJsonObject& summary) const
{
    if (summary.isEmpty())
        return tr("No hardware summary");
    QStringList reasons;
    const qint64 collected = timeValue(summary, "collected_at");
    const qint64 received = timeValue(summary, "received_at");
    const qint64 now = QDateTime::currentSecsSinceEpoch();
    if (collected > received + 300 || (received && collected < received - 24 * 60 * 60))
        reasons.append(tr("Check Host clock or collection delay"));
    if (inventoryTimestampIsStale(received ? received : collected, now, age_->currentData().toInt()))
        reasons.append(tr("Inventory is stale"));
    const quint64 ram = bytesValue(summary, "ram_bytes");
    if (ram && ram < static_cast<quint64>(ram_min_->value() * kGiB))
        reasons.append(tr("RAM below %1 GiB").arg(ram_min_->value()));
    else if (!ram)
        reasons.append(tr("RAM unknown"));
    const int cores = summary.value(QStringLiteral("cpu_cores")).toInt();
    if (cores > 0 && cores < cores_min_->value())
        reasons.append(tr("Fewer than %1 CPU cores").arg(cores_min_->value()));
    else if (!cores)
        reasons.append(tr("CPU core count unknown"));
    bool hdd = false;
    bool unknown_disk = summary.value(QStringLiteral("physical_disks")).toArray().isEmpty();
    for (const auto& value : summary.value(QStringLiteral("physical_disks")).toArray())
    {
        const int media = value.toObject().value(QStringLiteral("media")).toInt();
        hdd |= media == proto::InventoryDisk::HDD;
        unknown_disk |= media == proto::InventoryDisk::UNKNOWN;
    }
    if (hdd) reasons.append(tr("HDD present; review system-disk workload"));
    if (unknown_disk) reasons.append(tr("Disk media type is unknown"));
    for (const auto& value : summary.value(QStringLiteral("logical_volumes")).toArray())
    {
        const QJsonObject volume = value.toObject();
        const quint64 total = bytesValue(volume, "total_bytes");
        const quint64 free = bytesValue(volume, "free_bytes");
        if (total && free <= total && static_cast<double>(free) / static_cast<double>(total) * 100 < free_min_->value())
            reasons.append(tr("%1: below %2% free").arg(volume.value(QStringLiteral("path")).toString())
                .arg(free_min_->value()));
    }
    return reasons.join(QStringLiteral("; "));
}

QStringList InventoryDialog::reportRow(const InventoryTarget& target, bool utc) const
{
    const QJsonObject summary = snapshots_.value(target.key);
    const QJsonObject presence = presence_.value(target.key);
    QStringList volumes;
    for (const auto& value : summary.value(QStringLiteral("logical_volumes")).toArray())
    {
        const QJsonObject volume = value.toObject();
        const quint64 total = bytesValue(volume, "total_bytes");
        volumes.append(QStringLiteral("%1 %2 / %3 (%4)")
            .arg(volume.value(QStringLiteral("path")).toString(),
                 total ? gibText(total) : tr("unknown"),
                 total ? gibText(bytesValue(volume, "free_bytes")) : tr("unknown"),
                 volume.value(QStringLiteral("file_system")).toString()));
    }
    const quint64 ram = bytesValue(summary, "ram_bytes");
    QStringList disks;
    for (const auto& value : summary.value(QStringLiteral("physical_disks")).toArray())
    {
        const QJsonObject disk = value.toObject();
        const int media = disk.value(QStringLiteral("media")).toInt();
        const QString type = media == proto::InventoryDisk::SSD ? QStringLiteral("SSD")
            : (media == proto::InventoryDisk::HDD ? QStringLiteral("HDD") : tr("unknown"));
        const quint64 size = bytesValue(disk, "size_bytes");
        disks.append(QStringLiteral("#%1 %2 — %3 — %4")
            .arg(disk.value(QStringLiteral("number")).toInt())
            .arg(disk.value(QStringLiteral("model")).toString(), type, size ? gibText(size) : tr("unknown")));
    }
    auto number = [&](const char* key)
    {
        const int value = summary.value(QLatin1String(key)).toInt();
        return value ? QString::number(value) : QString();
    };
    QString system_name = summary.value(QStringLiteral("computer_name")).toString();
    if (system_name.isEmpty())
        system_name = presence.value(QStringLiteral("computer_name")).toString();
    QString address = target.address;
    if (!target.host_id)
        address += QStringLiteral(":%1").arg(target.config.port);
    return {
        target.name, target.group, address, system_name, activity(target),
        dateText(timeValue(presence, "last_seen"), utc),
        dateText(timeValue(summary, "collected_at"), utc),
        dateText(timeValue(summary, "received_at"), utc),
        summary.value(QStringLiteral("cpu_model")).toString(), number("cpu_cores"),
        number("cpu_threads"), number("cpu_clock_mhz"), ram ? gibText(ram) : QString(),
        disks.join(QStringLiteral("; ")), volumes.join(QStringLiteral("; ")),
        QStringLiteral("%1 %2 %3").arg(summary.value(QStringLiteral("os_name")).toString(),
            summary.value(QStringLiteral("os_version")).toString(),
            summary.value(QStringLiteral("os_arch")).toString()).trimmed(),
        reviewReasons(summary), summary.value(QStringLiteral("collection_note")).toString() +
            (summary.value(QStringLiteral("ram_source")).toString() == QStringLiteral("usable_physical_memory")
                ? tr(" RAM is usable memory; installed capacity was unavailable.") : QString())
    };
}

void InventoryDialog::rebuildTable()
{
    QSet<QString> collapsed;
    for (int i = 0; i < table_->topLevelItemCount(); ++i)
    {
        auto item = table_->topLevelItem(i);
        if (!item->isExpanded())
            collapsed.insert(item->data(0, Qt::UserRole).toString());
    }
    table_->clear();
    QMap<QString, QTreeWidgetItem*> groups;
    QMap<QString, QVector<const InventoryTarget*>> group_targets;
    QSet<QString> unique;
    QSet<QString> recent;
    QSet<QString> stale;
    QSet<QString> unknown;
    QSet<QString> hardware;
    const QString query = search_->text().trimmed();
    const qint64 now = QDateTime::currentSecsSinceEpoch();
    int visible = 0;
    for (const auto& target : targets_)
    {
        const QStringList row = reportRow(target, false);
        if (!query.isEmpty() && !row.join(QLatin1Char('\n')).contains(query, Qt::CaseInsensitive))
            continue;
        ++visible;
        unique.insert(target.key);
        const qint64 seen = timeValue(presence_.value(target.key), "last_seen");
        if (seen <= 0 || seen > now)
            unknown.insert(target.key);
        else if (inventoryTimestampIsStale(seen, now, age_->currentData().toInt()))
            stale.insert(target.key);
        else
            recent.insert(target.key);
        if (snapshots_.contains(target.key))
            hardware.insert(target.key);
        const QString group = target.group.isEmpty() ? tr("Root Group") : target.group;
        group_targets[group].append(&target);
        auto parent = groups.value(group, nullptr);
        if (!parent)
        {
            parent = new QTreeWidgetItem(table_);
            parent->setData(0, Qt::UserRole, group);
            parent->setFirstColumnSpanned(true);
            groups.insert(group, parent);
        }
        auto item = new QTreeWidgetItem(parent, row);
        item->setData(0, Qt::UserRole, target.key);
        for (int column = 0; column < row.size(); ++column)
            item->setToolTip(column, row[column]);
    }
    for (auto it = groups.cbegin(); it != groups.cend(); ++it)
    {
        it.value()->setText(0, it.key() + QStringLiteral(" — ") + groupSummary(group_targets.value(it.key())));
        it.value()->setExpanded(!collapsed.contains(it.key()));
    }
    counts_->setText(tr("Visible book entries: %1 / %2; unique endpoints: %3; Router observed recently: %4; "
        "not observed for %5 days: %6; unknown: %7; hardware summaries: %8.")
        .arg(visible).arg(targets_.size()).arg(unique.size()).arg(recent.size())
        .arg(age_->currentData().toInt()).arg(stale.size()).arg(unknown.size()).arg(hardware.size()));
}

QString InventoryDialog::groupSummary(const QVector<const InventoryTarget*>& targets) const
{
    QSet<QString> unique;
    int recent = 0;
    int stale = 0;
    int unknown = 0;
    int surveyed = 0;
    int low_ram = 0;
    int low_cores = 0;
    const qint64 now = QDateTime::currentSecsSinceEpoch();
    for (const auto target : targets)
    {
        if (unique.contains(target->key))
            continue;
        unique.insert(target->key);
        const qint64 seen = timeValue(presence_.value(target->key), "last_seen");
        if (seen <= 0 || seen > now) ++unknown;
        else if (inventoryTimestampIsStale(seen, now, age_->currentData().toInt())) ++stale;
        else ++recent;
        const auto summary = snapshots_.value(target->key);
        if (!summary.isEmpty()) ++surveyed;
        const auto ram = bytesValue(summary, "ram_bytes");
        const auto cores = summary.value(QStringLiteral("cpu_cores")).toInt();
        if (ram && ram < static_cast<quint64>(ram_min_->value() * kGiB)) ++low_ram;
        if (cores > 0 && cores < cores_min_->value()) ++low_cores;
    }
    return tr("%1 entries / %2 endpoints; recent %3; not observed %4; unknown %5; "
              "inventoried %6; low RAM %7; few cores %8")
        .arg(targets.size()).arg(unique.size()).arg(recent).arg(stale).arg(unknown)
        .arg(surveyed).arg(low_ram).arg(low_cores);
}

void InventoryDialog::exportHtml()
{
    const QString path = QFileDialog::getSaveFileName(this, tr("Export management report"),
        QStringLiteral("aspia-equipment-report-%1.html").arg(QDate::currentDate().toString(Qt::ISODate)),
        tr("HTML reports (*.html)"));
    if (path.isEmpty())
        return;
    QMap<QString, QVector<const InventoryTarget*>> groups;
    QVector<const InventoryTarget*> all;
    const QString query = search_->text().trimmed();
    for (const auto& target : targets_)
    {
        if (!query.isEmpty() && !reportRow(target, false).join(QLatin1Char('\n')).contains(query, Qt::CaseInsensitive))
            continue;
        groups[target.group.isEmpty() ? tr("Root Group") : target.group].append(&target);
        all.append(&target);
    }
    struct Metrics
    {
        int entries = 0, endpoints = 0, recent = 0, inactive = 0, unknown_activity = 0;
        int surveyed = 0, fresh = 0, low_ram = 0, low_cores = 0, hdd = 0, low_space = 0;
        int review = 0, data_gaps = 0;
    };
    const qint64 now = QDateTime::currentSecsSinceEpoch();
    const int days = age_->currentData().toInt();
    const auto metrics = [&](const QVector<const InventoryTarget*>& targets)
    {
        Metrics m;
        m.entries = targets.size();
        QSet<QString> counted;
        for (const auto* target : targets)
        {
            if (counted.contains(target->key))
                continue;
            counted.insert(target->key);
            ++m.endpoints;
            const qint64 seen = timeValue(presence_.value(target->key), "last_seen");
            if (seen <= 0 || seen > now) ++m.unknown_activity;
            else if (inventoryTimestampIsStale(seen, now, days)) ++m.inactive;
            else ++m.recent;
            const QJsonObject summary = snapshots_.value(target->key);
            if (summary.isEmpty())
            {
                ++m.data_gaps;
                continue;
            }
            ++m.surveyed;
            const qint64 received = timeValue(summary, "received_at");
            if (received > 0 && received <= now && !inventoryTimestampIsStale(received, now, days)) ++m.fresh;
            const quint64 ram = bytesValue(summary, "ram_bytes");
            const int cores = summary.value(QStringLiteral("cpu_cores")).toInt();
            const bool low_ram = ram && ram < static_cast<quint64>(ram_min_->value()) * kGiB;
            const bool low_cores = cores > 0 && cores < cores_min_->value();
            bool hdd = false, low_space = false;
            bool gap = !ram || !cores || summary.value(QStringLiteral("cpu_model")).toString().isEmpty();
            const QJsonArray disks = summary.value(QStringLiteral("physical_disks")).toArray();
            gap |= disks.isEmpty();
            for (const auto& value : disks)
            {
                const QJsonObject disk = value.toObject();
                hdd |= disk.value(QStringLiteral("media")).toInt() == proto::InventoryDisk::HDD;
                gap |= disk.value(QStringLiteral("media")).toInt() == proto::InventoryDisk::UNKNOWN ||
                    !bytesValue(disk, "size_bytes");
            }
            for (const auto& value : summary.value(QStringLiteral("logical_volumes")).toArray())
            {
                const QJsonObject volume = value.toObject();
                const quint64 total = bytesValue(volume, "total_bytes");
                const quint64 free = bytesValue(volume, "free_bytes");
                low_space |= total && free <= total && static_cast<double>(free) / total * 100.0 < free_min_->value();
            }
            m.low_ram += low_ram; m.low_cores += low_cores; m.hdd += hdd; m.low_space += low_space;
            m.review += low_ram || low_cores || hdd || low_space;
            m.data_gaps += gap;
        }
        return m;
    };
    const Metrics total = metrics(all);
    const auto e = [](const QString& value) { return value.toHtmlEscaped(); };
    const auto cell = [&](const QString& value) -> QString { return QStringLiteral("<td>") + e(value) + QStringLiteral("</td>"); };
    const auto numeric = [&](int value) -> QString { return QStringLiteral("<td class=\"num\">") + QString::number(value) + QStringLiteral("</td>"); };
    const auto th = [&](const QString& value) -> QString { return QStringLiteral("<th>") + e(value) + QStringLiteral("</th>"); };
    const auto available = [&](const QString& value) { return value.isEmpty() ? tr("unknown") : value; };
    QString html = QStringLiteral("<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>") +
        e(tr("IT equipment inventory")) + QStringLiteral("</title><style>"
        "*{box-sizing:border-box}body{font:14px/1.5 'Segoe UI',Arial,sans-serif;color:#20324a;background:#fff;max-width:1320px;margin:36px auto;padding:0 32px}"
        "header{border-top:6px solid #214761;padding:24px 0 20px;border-bottom:1px solid #bdcbd5}h1{font-size:32px;line-height:1.2;margin:4px 0 12px;font-weight:650}"
        "h2{font-size:21px;margin:32px 0 12px;padding-bottom:7px;border-bottom:2px solid #ccd8e0}h3{font-size:17px;margin:24px 0 10px}p{margin:10px 0}.meta{color:#52687a;font-size:13px}"
        ".kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}.kpi{border:1px solid #cfdae2;padding:16px;background:#f6f9fb}.kpi strong{display:block;font-size:30px;line-height:1.2;font-weight:650}.kpi span{display:block;margin-top:8px;color:#52687a;font-size:13px}"
        ".scope,.method{padding:14px 18px;background:#f4f7f9;border-left:3px solid #59768b}.status{padding:10px 14px;border:1px solid #c9d6df;background:#f8fafb;overflow-wrap:anywhere}"
        "table{border-collapse:collapse;width:100%;font-size:12px;line-height:1.45;table-layout:fixed;margin:12px 0 20px}td,th{border:1px solid #d5dfe5;padding:9px 8px;vertical-align:top;overflow-wrap:anywhere}"
        "th{background:#e9f0f5;text-align:left;font-weight:650}tbody tr:nth-child(even){background:#f8fafb}.num{text-align:right;font-variant-numeric:tabular-nums}.muted{display:block;font-size:11px;color:#52687a;margin-top:5px}.review{color:#714a0b}.appendix td{font-size:11px}"
        "footer{margin-top:30px;padding-top:14px;border-top:1px solid #bdcbd5;color:#52687a;font-size:12px}.group{break-inside:auto}"
        "@media(max-width:800px){body{padding:0 16px}.kpis{grid-template-columns:repeat(2,1fr)}.table-scroll{overflow-x:auto}table{min-width:800px}}"
        "@media print{@page{size:A4 landscape;margin:12mm}body{margin:0;padding:0;max-width:none;font-size:10pt}header{padding-top:10px}h1{font-size:23pt}h2{font-size:15pt}h3{font-size:12pt}"
        ".kpis{gap:8px;margin:16px 0}.kpi{padding:10px}.kpi strong{font-size:22pt}.kpi span{font-size:9pt}.meta,.muted{font-size:8pt}"
        "table{font-size:9pt;min-width:0}.appendix td{font-size:8pt}td,th{padding:6px}thead{display:table-header-group}tr{break-inside:avoid}h2,h3{break-after:avoid}.appendix{break-before:page}"
        "footer{font-size:8pt}.method,.status{break-inside:avoid}.table-scroll{overflow:visible}}"
        "</style></head><body><header><div class=\"meta\">ASPIA+</div><h1>") + e(tr("IT equipment inventory")) +
        QStringLiteral("</h1><p>") + e(tr("Management summary and technical register")) + QStringLiteral("</p><div class=\"meta\">") +
        e(tr("Created: %1 (UTC). Scope: all groups in the open address book.").arg(dateText(now, true))) + QStringLiteral("</div></header>");
    html += QStringLiteral("<p class=\"scope\">") + e(tr("Address book: %1").arg(book_name_)) + QStringLiteral("</p>");
    if (!query.isEmpty())
        html += QStringLiteral("<p class=\"scope\">") + e(tr("Active filter: %1").arg(query)) + QStringLiteral("</p>");
    html += QStringLiteral("<p class=\"status\">") + e(presence_status_->text()) + QStringLiteral("</p>");
    const auto kpi = [&](int value, const QString& label) -> QString
    {
        return QStringLiteral("<div class=\"kpi\"><strong>") + QString::number(value) +
            QStringLiteral("</strong><span>") + e(label) + QStringLiteral("</span></div>");
    };
    html += QStringLiteral("<section class=\"kpis\">") + kpi(total.endpoints, tr("Unique endpoints in scope")) +
        kpi(total.recent, tr("Observed within %1 days").arg(days)) +
        kpi(total.surveyed, tr("Endpoints with hardware data")) +
        kpi(total.review, tr("Endpoints meeting review criteria")) + QStringLiteral("</section>");
    html += QStringLiteral("<p>") + e(tr("The report covers %1 book entries in %2 groups. %3 endpoints have no recent activity evidence; "
        "%4 have no activity history. %5 endpoints have missing or incomplete hardware fields. These categories are shown separately and may overlap.")
        .arg(total.entries).arg(groups.size()).arg(total.inactive).arg(total.unknown_activity).arg(total.data_gaps)) + QStringLiteral("</p>");
    html += QStringLiteral("<h2>") + e(tr("1. Coverage by group")) + QStringLiteral("</h2><div class=\"table-scroll\"><table><colgroup><col style=\"width:27%\"><col span=\"7\"></colgroup><thead><tr>") +
        th(tr("Group")) + th(tr("Book entries")) + th(tr("Unique endpoints")) + th(tr("Recent activity")) + th(tr("No recent activity")) +
        th(tr("Activity unknown")) + th(tr("Hardware available")) + th(tr("Recent hardware")) + QStringLiteral("</tr></thead><tbody>");
    for (auto it = groups.cbegin(); it != groups.cend(); ++it)
    {
        const Metrics m = metrics(it.value());
        html += QStringLiteral("<tr>") + cell(it.key()) + numeric(m.entries) + numeric(m.endpoints) + numeric(m.recent) +
            numeric(m.inactive) + numeric(m.unknown_activity) + numeric(m.surveyed) + numeric(m.fresh) + QStringLiteral("</tr>");
    }
    html += QStringLiteral("<tr><th>") + e(tr("Entire selected scope")) + QStringLiteral("</th>") + numeric(total.entries) + numeric(total.endpoints) + numeric(total.recent) +
        numeric(total.inactive) + numeric(total.unknown_activity) + numeric(total.surveyed) + numeric(total.fresh) + QStringLiteral("</tr></tbody></table></div><p class=\"meta\">") +
        e(tr("Recent activity and recent hardware use the selected %1-day window. Hardware age is measured from the first server receipt of that collection. "
             "Totals remove duplicate endpoints across groups; group subtotals may overlap." ).arg(days)) + QStringLiteral("</p>");
    html += QStringLiteral("<h2>") + e(tr("2. Grounds for technical review")) + QStringLiteral("</h2><div class=\"table-scroll\"><table><colgroup><col style=\"width:28%\"><col span=\"5\"></colgroup><thead><tr>") +
        th(tr("Group")) + th(tr("RAM below %1 GiB").arg(ram_min_->value())) + th(tr("Fewer than %1 CPU cores").arg(cores_min_->value())) +
        th(tr("HDD present")) + th(tr("Low volume free space")) + th(tr("Any review criterion")) + QStringLiteral("</tr></thead><tbody>");
    for (auto it = groups.cbegin(); it != groups.cend(); ++it)
    {
        const Metrics m = metrics(it.value());
        html += QStringLiteral("<tr>") + cell(it.key()) + numeric(m.low_ram) + numeric(m.low_cores) + numeric(m.hdd) +
            numeric(m.low_space) + numeric(m.review) + QStringLiteral("</tr>");
    }
    html += QStringLiteral("<tr><th>") + e(tr("Entire selected scope")) + QStringLiteral("</th>") + numeric(total.low_ram) + numeric(total.low_cores) + numeric(total.hdd) +
        numeric(total.low_space) + numeric(total.review) + QStringLiteral("</tr></tbody></table></div><div class=\"method\"><p>") +
        e(tr("Criteria: activity within %1 days; RAM below %2 GiB; fewer than %3 CPU cores; volume free space below %4%. "
             "HDD presence is a reason to review the workload, not an automatic replacement decision.")
            .arg(days).arg(ram_min_->value()).arg(cores_min_->value()).arg(free_min_->value())) + QStringLiteral("</p><p>") +
        e(tr("Review counts use the latest available hardware even when its collection is old. Missing data is not a healthy result. "
             "Confirm the workload and current configuration before purchasing or retiring equipment.")) + QStringLiteral("</p></div>");
    html += QStringLiteral("<section class=\"appendix\"><h2>") + e(tr("3. Technical register by group")) + QStringLiteral("</h2><p class=\"meta\">") +
        e(tr("One row per address-book entry. Processor frequency is in MHz; memory and drive capacity are in GiB. Times below are UTC.")) + QStringLiteral("</p>");
    for (auto group = groups.cbegin(); group != groups.cend(); ++group)
    {
        html += QStringLiteral("<section class=\"group\"><h3>") + e(group.key()) + QStringLiteral("</h3><div class=\"table-scroll\"><table><colgroup>") +
            QStringLiteral("<col style=\"width:15%\"><col style=\"width:18%\"><col style=\"width:6%\"><col style=\"width:20%\"><col style=\"width:12%\"><col style=\"width:14%\"><col style=\"width:15%\"></colgroup><thead><tr>") +
            th(tr("Workplace / identity")) + th(tr("Processor")) + th(tr("RAM, GiB")) + th(tr("Physical storage")) + th(tr("Operating system")) +
            th(tr("Activity and collection")) + th(tr("Review reasons")) + QStringLiteral("</tr></thead><tbody>");
        for (const auto* target : group.value())
        {
            const QStringList row = reportRow(*target, true);
            const auto small = [&](const QString& value) -> QString { return QStringLiteral("<span class=\"muted\">") + e(value) + QStringLiteral("</span>"); };
            html += QStringLiteral("<tr><td><strong>") + e(available(row[0])) + QStringLiteral("</strong>") + small(available(row[3])) +
                small(tr("Address / ID") + QStringLiteral(": ") + row[2]) + QStringLiteral("</td><td>") + e(available(row[8])) +
                small(tr("%1 cores / %2 threads / %3 MHz").arg(available(row[9]), available(row[10]), available(row[11]))) + QStringLiteral("</td>") +
                cell(available(row[12])) + cell(available(row[13])) + cell(available(row[15])) + QStringLiteral("<td>") + e(available(row[4])) +
                small(tr("Last seen: %1").arg(available(row[5]))) + small(tr("Collected: %1").arg(available(row[6]))) +
                QStringLiteral("</td><td class=\"review\">") + e(row[16].isEmpty() ? tr("No selected hardware criteria were detected") : row[16]) +
                (row[17].isEmpty() ? QString() : small(row[17])) + QStringLiteral("</td></tr>");
        }
        html += QStringLiteral("</tbody></table></div></section>");
    }
    html += QStringLiteral("</section><footer><p>") + e(tr("Source: automatic Host summaries stored by Router. "
        "CPU frequency is the value reported by Windows, not a live performance measurement. "
        "Disk media type is reported by the storage driver; RAID, USB bridges and unsupported devices "
        "may remain unknown. The detailed CSV also includes logical volumes, receipt times and collection notes.")) + QStringLiteral("</p><p>") +
        e(tr("Counts refer to address-book records and unique addresses / Host IDs. Several IDs can belong to one physical computer. "
             "Computers not observed recently need checking; vacation, spare equipment and retired equipment cannot be distinguished automatically. "
             "Missing hardware or activity is shown as unknown. No purchase age is inferred.")) + QStringLiteral("</p></footer></body></html>");
    QSaveFile file(path);
    const QByteArray bytes = html.toUtf8();
    if (!file.open(QIODevice::WriteOnly) || file.write(bytes) != bytes.size() || !file.commit())
        QMessageBox::warning(this, tr("Export management report"), tr("Could not write the complete report."));
}

void InventoryDialog::exportCsv()
{
    const QString path = QFileDialog::getSaveFileName(this, tr("Export equipment report"),
        QStringLiteral("aspia-equipment-%1.csv").arg(QDate::currentDate().toString(Qt::ISODate)),
        tr("CSV files (*.csv)"));
    if (path.isEmpty())
        return;
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly))
    {
        QMessageBox::warning(this, tr("Export equipment report"), file.errorString());
        return;
    }
    bool ok = file.write("\xEF\xBB\xBF", 3) == 3;
    const auto write_row = [&](const QStringList& row)
    {
        const QByteArray bytes = inventoryCsvRow(row);
        return file.write(bytes) == bytes.size();
    };
    ok = ok && write_row(reportHeaders(true));
    const QString query = search_->text().trimmed();
    for (const auto& target : targets_)
    {
        if (!query.isEmpty() && !reportRow(target, false).join(QLatin1Char('\n')).contains(query, Qt::CaseInsensitive))
            continue;
        ok = ok && write_row(reportRow(target, true));
    }
    if (!ok || !file.commit())
        QMessageBox::warning(this, tr("Export equipment report"), tr("Could not write the complete report."));
}

} // namespace console
