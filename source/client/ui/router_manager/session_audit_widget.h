// Aspia+ session journal. GPL-3.0-or-later; see LICENSE.md.
#ifndef CLIENT_UI_ROUTER_MANAGER_SESSION_AUDIT_WIDGET_H
#define CLIENT_UI_ROUTER_MANAGER_SESSION_AUDIT_WIDGET_H

#include "proto/session_audit.pb.h"
#include <QMap>
#include <QStringList>
#include <QWidget>
#include <vector>

class QComboBox;
class QDateEdit;
class QLabel;
class QLineEdit;
class QPushButton;
class QTimer;
class QTreeWidget;

namespace client {
class SessionAuditWidget final : public QWidget
{
    Q_OBJECT
public:
    explicit SessionAuditWidget(QWidget* parent = nullptr);
    void setConnectionState(bool connected, bool supported);
    void setComputerAliases(const QMap<quint64, QString>& aliases);
    void acceptList(const proto::SessionAuditList& list);

signals:
    void requestPage(const proto::SessionAuditRequest& request);

private:
    void request(bool next_page);
    void rebuild();
    void filtersChanged();
    void updateButtons();
    void exportCsv();
    QString groupText(int group) const;
    QStringList recordCells(const proto::SessionAuditRecord& record) const;
    QStringList headings() const;
    bool matchesSearch(const QStringList& cells) const;

    QDateEdit* from_;
    QDateEdit* to_;
    QComboBox* login_source_;
    QLineEdit* user_;
    QLineEdit* host_id_;
    QLineEdit* search_;
    QPushButton* refresh_;
    QPushButton* more_;
    QPushButton* export_;
    QLabel* status_;
    QTreeWidget* tree_;
    QTimer* timeout_;
    QMap<quint64, QString> aliases_;
    std::vector<proto::SessionAuditRecord> records_;
    proto::SessionAuditRequest filter_;
    quint64 request_id_ = 0;
    qint64 next_id_ = 0;
    qint64 next_started_ = 0;
    bool connected_ = false;
    bool supported_ = false;
    bool pending_ = false;
    bool append_ = false;
    bool ever_loaded_ = false;
};
} // namespace client
#endif
