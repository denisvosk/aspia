// Aspia Project
// SPDX-License-Identifier: GPL-3.0-or-later

#ifndef CONSOLE_INVENTORY_DIALOG_H
#define CONSOLE_INVENTORY_DIALOG_H

#include "client/router_window.h"
#include "console/inventory_report.h"

#include <QDialog>
#include <QHash>
#include <QElapsedTimer>
#include <QPointer>

class QComboBox;
class QLabel;
class QLineEdit;
class QPushButton;
class QTimer;
class QTreeWidget;
class QSpinBox;

namespace client {
class RouterProxy;
class RouterWindowProxy;
} // namespace client

namespace console {

class InventoryDialog final : public QDialog, public client::RouterWindow
{
    Q_OBJECT

public:
    InventoryDialog(const proto::address_book::ComputerGroup& root, const QString& book_guid,
                    const QString& book_name,
                    const std::string& display_name,
                    const std::optional<client::RouterConfig>& router_config,
                    QWidget* parent = nullptr);
    ~InventoryDialog() final;

    void onConnecting() final;
    void onConnected(const base::Version& peer_version) final;
    void onDisconnected(base::TcpChannel::ErrorCode error_code) final;
    void onWaitForRouter() final;
    void onWaitForRouterTimeout() final;
    void onVersionMismatch(const base::Version& router, const base::Version& client) final;
    void onAccessDenied(base::ClientAuthenticator::ErrorCode error_code) final;
    void onSessionList(std::shared_ptr<proto::SessionList> session_list) final;
    void onSessionResult(std::shared_ptr<proto::SessionResult>) final {}
    void onUserList(std::shared_ptr<proto::UserList>) final {}
    void onUserResult(std::shared_ptr<proto::UserResult>) final {}
    void onHostPresenceList(std::shared_ptr<proto::HostPresenceList> presence) final;
    void onInventoryList(std::shared_ptr<proto::InventoryList> inventory) final;

private:
    void refreshPresence();
    void finishPresence(const QString& result);
    void requestInventory();
    void rebuildTable();
    void exportCsv();
    void exportHtml();
    QString groupSummary(const QVector<const InventoryTarget*>& targets) const;
    void loadCache();
    void saveCache();
    QStringList reportRow(const InventoryTarget& target, bool utc) const;
    QString activity(const InventoryTarget& target) const;
    QString reviewReasons(const QJsonObject& summary) const;

    QVector<InventoryTarget> targets_;
    std::optional<client::RouterConfig> router_config_;
    QString book_name_;
    QString cache_path_;
    QHash<QString, QJsonObject> snapshots_;
    QHash<QString, QJsonObject> presence_;
    QHash<quint64, bool> live_online_;
    bool presence_loading_ = false;
    bool presence_supported_ = false;
    bool inventory_supported_ = false;
    qint64 inventory_cursor_ = 0;
    int inventory_count_ = 0;
    qint64 presence_cursor_ = 0;
    int presence_count_ = 0;
    qint64 presence_observed_at_ = 0;
    QElapsedTimer request_elapsed_;

    std::shared_ptr<client::RouterWindowProxy> router_window_proxy_;
    std::unique_ptr<client::RouterProxy> router_proxy_;
    QTimer* presence_timer_ = nullptr;
    QComboBox* age_ = nullptr;
    QSpinBox* ram_min_ = nullptr;
    QSpinBox* cores_min_ = nullptr;
    QSpinBox* free_min_ = nullptr;
    QLineEdit* search_ = nullptr;
    QTreeWidget* table_ = nullptr;
    QLabel* counts_ = nullptr;
    QLabel* presence_status_ = nullptr;
    QLabel* cache_status_ = nullptr;
    QPushButton* presence_button_ = nullptr;
};

} // namespace console

#endif // CONSOLE_INVENTORY_DIALOG_H
