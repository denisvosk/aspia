// Aspia+ session journal. GPL-3.0-or-later; see LICENSE.md.
#include "client/ui/router_manager/session_audit_widget.h"
#include "client/ui/router_manager/session_audit_helpers.h"
#include "common/ui/session_type.h"

#include <QDateEdit>
#include <QDateTime>
#include <QFileDialog>
#include <QHeaderView>
#include <QLabel>
#include <QLineEdit>
#include <QLocale>
#include <QMessageBox>
#include <QPushButton>
#include <QSaveFile>
#include <QTimer>
#include <QTreeWidget>
#include <QVBoxLayout>
#include <algorithm>
#include <set>

namespace client {
namespace {
constexpr size_t kMaxLoadedRecords = 10000;
QString timeText(qint64 timestamp)
{
    return timestamp > 0 ? QDateTime::fromSecsSinceEpoch(timestamp).toLocalTime()
        .toString(QStringLiteral("yyyy-MM-dd HH:mm:ss")) : QString();
}
}

SessionAuditWidget::SessionAuditWidget(QWidget* parent) : QWidget(parent)
{
    auto* layout = new QVBoxLayout(this);
    auto* note = new QLabel(tr("Confirmed Host logins. Times are shown in this computer's local time zone. "
                              "Computer aliases come from the current address book; the recorded Host name is retained."), this);
    note->setWordWrap(true);
    layout->addWidget(note);

    auto* filters = new QHBoxLayout();
    from_ = new QDateEdit(QDate::currentDate().addDays(-30), this);
    to_ = new QDateEdit(QDate::currentDate(), this);
    for (QDateEdit* field : {from_, to_})
    {
        field->setCalendarPopup(true);
        field->setDisplayFormat(QStringLiteral("dd.MM.yyyy"));
    }
    filters->addWidget(new QLabel(tr("From"), this));
    filters->addWidget(from_);
    filters->addWidget(new QLabel(tr("Through"), this));
    filters->addWidget(to_);
    user_ = new QLineEdit(this);
    user_->setPlaceholderText(tr("Host login (exact), or all users"));
    user_->setMaxLength(256);
    host_id_ = new QLineEdit(this);
    host_id_->setPlaceholderText(tr("Host ID, or all computers"));
    host_id_->setMaxLength(20);
    filters->addWidget(user_, 1);
    filters->addWidget(host_id_, 1);
    refresh_ = new QPushButton(tr("Refresh journal"), this);
    filters->addWidget(refresh_);
    layout->addLayout(filters);

    search_ = new QLineEdit(this);
    search_->setPlaceholderText(tr("Search loaded sessions: user, computer, group, ID or address"));
    layout->addWidget(search_);
    tree_ = new QTreeWidget(this);
    tree_->setObjectName(QStringLiteral("sessionAuditTree"));
    tree_->setHeaderLabels(headings());
    tree_->setAlternatingRowColors(true);
    tree_->setSelectionMode(QAbstractItemView::ExtendedSelection);
    tree_->setUniformRowHeights(true);
    tree_->header()->setStretchLastSection(false);
    tree_->header()->setSectionResizeMode(QHeaderView::Interactive);
    tree_->setColumnWidth(0, 200);
    tree_->setColumnWidth(1, 145);
    tree_->setColumnWidth(2, 240);
    layout->addWidget(tree_, 1);
    auto* buttons = new QHBoxLayout();
    status_ = new QLabel(this);
    status_->setWordWrap(true);
    buttons->addWidget(status_, 1);
    more_ = new QPushButton(tr("Load older sessions"), this);
    export_ = new QPushButton(tr("Export loaded sessions..."), this);
    buttons->addWidget(more_);
    buttons->addWidget(export_);
    layout->addLayout(buttons);

    timeout_ = new QTimer(this);
    timeout_->setSingleShot(true);
    timeout_->setInterval(20000);
    connect(timeout_, &QTimer::timeout, this, [this]() {
        pending_ = false;
        ++request_id_; // A late response must not replace a subsequent query.
        status_->setText(tr("The journal request timed out. Loaded records are retained; try Refresh."));
        updateButtons();
    });
    connect(refresh_, &QPushButton::clicked, this, [this]() { request(false); });
    connect(more_, &QPushButton::clicked, this, [this]() { request(true); });
    connect(export_, &QPushButton::clicked, this, &SessionAuditWidget::exportCsv);
    connect(search_, &QLineEdit::textChanged, this, [this]() { rebuild(); });
    connect(user_, &QLineEdit::textChanged, this, [this]() { filtersChanged(); });
    connect(host_id_, &QLineEdit::textChanged, this, [this]() { filtersChanged(); });
    connect(from_, &QDateEdit::dateChanged, this, [this]() { filtersChanged(); });
    connect(to_, &QDateEdit::dateChanged, this, [this]() { filtersChanged(); });
    setConnectionState(false, false);
}

QStringList SessionAuditWidget::headings() const
{
    return {tr("Started"), tr("Host login"), tr("Computer / book alias"), tr("Host ID"),
            tr("Session type"), tr("Ended"), tr("Duration (h:mm:ss)"), tr("Status"),
            tr("Client computer (reported)"), tr("Transport peer"), tr("Recorded Host name"),
            tr("Host address"), tr("Last server confirmation")};
}

void SessionAuditWidget::setConnectionState(bool connected, bool supported)
{
    const bool newly_available = connected && supported && (!connected_ || !supported_);
    connected_ = connected;
    supported_ = supported;
    if (!connected_ || !supported_)
    {
        timeout_->stop();
        pending_ = false;
        ++request_id_;
        status_->setText(!connected_ ? tr("Router disconnected. Any displayed rows are the last loaded snapshot.")
            : tr("This Router does not advertise the session journal. Upgrade Router and Hosts to Aspia+ 2.7.2."));
    }
    updateButtons();
    if (newly_available)
        request(false);
}

void SessionAuditWidget::setComputerAliases(const QMap<quint64, QString>& aliases)
{
    aliases_ = aliases;
    rebuild();
}

void SessionAuditWidget::filtersChanged()
{
    timeout_->stop();
    ++request_id_;
    pending_ = false;
    next_id_ = 0;
    next_started_ = 0;
    records_.clear();
    ever_loaded_ = false;
    tree_->clear();
    status_->setText(tr("Filters changed. Press Refresh journal to load this period."));
    updateButtons();
}

void SessionAuditWidget::request(bool next_page)
{
    if (!connected_ || !supported_ || pending_)
        return;
    if (next_page && (!next_id_ || records_.size() >= kMaxLoadedRecords))
        return;
    if (!next_page)
    {
        if (from_->date() > to_->date())
        {
            status_->setText(tr("The start date must not be after the end date."));
            return;
        }
        bool valid_id = true;
        const QString id_text = host_id_->text().trimmed();
        const quint64 id = id_text.isEmpty() ? 0 : id_text.toULongLong(&valid_id);
        if (!valid_id || (!id_text.isEmpty() && id == 0))
        {
            status_->setText(tr("Enter a valid numeric Host ID, or leave it empty."));
            return;
        }
        filter_.Clear();
        filter_.set_from_time(QDateTime(from_->date(), QTime(0, 0), Qt::LocalTime).toSecsSinceEpoch());
        filter_.set_to_time(QDateTime(to_->date().addDays(1), QTime(0, 0), Qt::LocalTime).toSecsSinceEpoch());
        filter_.set_host_id(id);
        filter_.set_user_name(user_->text().trimmed().toStdString());
        // Keep the previous successful snapshot until its replacement arrives.
        // A filter edit already clears rows that belonged to a different scope.
    }
    proto::SessionAuditRequest query(filter_);
    query.set_limit(500);
    query.set_before_id(next_page ? next_id_ : 0);
    query.set_before_started_at(next_page ? next_started_ : 0);
    query.set_request_id(++request_id_);
    append_ = next_page;
    pending_ = true;
    status_->setText(tr("Loading journal from Router..."));
    updateButtons();
    timeout_->start();
    emit requestPage(query);
}

void SessionAuditWidget::acceptList(const proto::SessionAuditList& list)
{
    if (!pending_ || list.request_id() != request_id_)
        return;
    timeout_->stop();
    pending_ = false;
    if (list.error_code() != proto::SessionAuditList::SUCCESS)
    {
        status_->setText(tr("Router could not read the journal (error %1).").arg(list.error_code()));
        updateButtons();
        return;
    }
    if (!append_)
        records_.clear();
    std::set<qint64> ids;
    for (const auto& record : records_)
        ids.insert(record.id());
    for (const auto& record : list.record())
    {
        if (records_.size() >= kMaxLoadedRecords)
            break;
        if (ids.insert(record.id()).second)
            records_.push_back(record);
    }
    next_id_ = list.next_before_id();
    next_started_ = list.next_before_started_at();
    ever_loaded_ = true;
    rebuild();
}

QString SessionAuditWidget::groupText(int group) const
{
    switch (static_cast<AuditDateGroup>(group))
    {
        case AuditDateGroup::FUTURE: return tr("Future dates — check the Host clock");
        case AuditDateGroup::TODAY: return tr("Today");
        case AuditDateGroup::YESTERDAY: return tr("Yesterday");
        case AuditDateGroup::THIS_WEEK: return tr("This week");
        case AuditDateGroup::LAST_WEEK: return tr("Last week");
        default: return tr("Earlier");
    }
}

QStringList SessionAuditWidget::recordCells(const proto::SessionAuditRecord& record) const
{
    const QString name = QString::fromStdString(record.host_name());
    const QString alias = aliases_.value(record.host_id());
    QString state;
    QString duration = auditDuration(record.duration_seconds());
    switch (record.state())
    {
        case proto::SessionAuditRecord::ACTIVE:
            state = tr("Active at last confirmation");
            duration.prepend(QStringLiteral(">= "));
            break;
        case proto::SessionAuditRecord::FINISHED:
            state = tr("Finished");
            break;
        case proto::SessionAuditRecord::INTERRUPTED:
            state = tr("End not confirmed");
            duration.prepend(QStringLiteral(">= "));
            break;
        default: state = tr("Unknown"); break;
    }
    return {timeText(record.started_at()), QString::fromStdString(record.user_name()),
        alias.isEmpty() ? name : alias, QString::number(record.host_id()),
        common::sessionTypeToLocalizedString(static_cast<proto::SessionType>(record.session_type())),
        timeText(record.ended_at()), duration, state,
        QString::fromStdString(record.client_computer()), QString::fromStdString(record.peer_address()),
        name, QString::fromStdString(record.host_address()), timeText(record.last_seen())};
}

bool SessionAuditWidget::matchesSearch(const QStringList& cells) const
{
    const QString search = search_->text().trimmed();
    return search.isEmpty() || cells.join(QLatin1Char(' ')).contains(search, Qt::CaseInsensitive);
}

void SessionAuditWidget::rebuild()
{
    tree_->clear();
    std::sort(records_.begin(), records_.end(), [](const auto& a, const auto& b) {
        if (a.started_at() != b.started_at())
            return a.started_at() > b.started_at();
        return a.id() > b.id();
    });
    QMap<int, QTreeWidgetItem*> groups;
    QMap<QDate, QTreeWidgetItem*> days;
    int shown = 0;
    for (const auto& record : records_)
    {
        const QStringList cells = recordCells(record);
        if (!matchesSearch(cells))
            continue;
        const QDate date = QDateTime::fromSecsSinceEpoch(record.started_at()).toLocalTime().date();
        const int group = static_cast<int>(auditDateGroup(date, QDate::currentDate()));
        QTreeWidgetItem* parent = groups.value(group);
        if (!parent)
        {
            parent = new QTreeWidgetItem(tree_, {groupText(group)});
            parent->setFirstColumnSpanned(true);
            parent->setExpanded(true);
            groups.insert(group, parent);
        }
        QTreeWidgetItem* day = days.value(date);
        if (!day)
        {
            day = new QTreeWidgetItem(parent, {QLocale().toString(date, QLocale::LongFormat)});
            day->setFirstColumnSpanned(true);
            day->setExpanded(true);
            days.insert(date, day);
        }
        auto* row = new QTreeWidgetItem(day, cells);
        row->setToolTip(1, tr("Account authenticated by the Host. A shared login cannot identify individual people."));
        row->setToolTip(9, tr("The actual transport peer; for relayed sessions this may be the Relay address."));
        ++shown;
    }
    for (auto it = days.begin(); it != days.end(); ++it)
        it.value()->setText(0, QStringLiteral("%1 (%2)")
            .arg(QLocale().toString(it.key(), QLocale::LongFormat)).arg(it.value()->childCount()));
    if (ever_loaded_ && !pending_)
    {
        QString status = tr("Shown: %1. Loaded: %2. Group counts and export cover loaded sessions only.")
            .arg(shown).arg(static_cast<qulonglong>(records_.size()));
        if (next_id_)
            status += records_.size() >= kMaxLoadedRecords ? tr(" Narrow the period to load more than 10,000 rows.")
                                                         : tr(" Older sessions are available.");
        if (!connected_)
            status += tr(" Router disconnected; this is the last loaded snapshot.");
        status_->setText(status);
    }
    updateButtons();
}

void SessionAuditWidget::updateButtons()
{
    refresh_->setEnabled(connected_ && supported_ && !pending_);
    more_->setEnabled(connected_ && supported_ && !pending_ && next_id_ && records_.size() < kMaxLoadedRecords);
    export_->setEnabled(!records_.empty() && !pending_);
}

void SessionAuditWidget::exportCsv()
{
    const QString path = QFileDialog::getSaveFileName(this, tr("Export loaded sessions"),
        QStringLiteral("aspia-sessions-%1.csv").arg(QDate::currentDate().toString(Qt::ISODate)),
        tr("CSV files (*.csv)"));
    if (path.isEmpty())
        return;
    QSaveFile file(path);
    if (!file.open(QIODevice::WriteOnly))
    {
        QMessageBox::warning(this, tr("Export failed"), file.errorString());
        return;
    }
    auto encode = [](const QStringList& cells) {
        QStringList quoted;
        for (const QString& value : cells)
            quoted.append(auditCsvCell(value));
        return (quoted.join(QLatin1Char(';')) + QStringLiteral("\r\n")).toUtf8();
    };
    QByteArray output("\xef\xbb\xbf");
    QStringList csv_headings = headings();
    for (int column : {0, 5, 12})
        csv_headings[column] += QStringLiteral(" (UTC)");
    output += encode(csv_headings);
    for (const auto& record : records_)
    {
        QStringList cells = recordCells(record);
        if (!matchesSearch(cells))
            continue;
        const auto utc_time = [](qint64 seconds) {
            return seconds > 0 ? QDateTime::fromSecsSinceEpoch(seconds, Qt::UTC).toString(Qt::ISODate)
                               : QString();
        };
        cells[0] = utc_time(record.started_at());
        cells[5] = utc_time(record.ended_at());
        cells[12] = utc_time(record.last_seen());
        output += encode(cells);
    }
    if (file.write(output) != output.size() || !file.commit())
        QMessageBox::warning(this, tr("Export failed"), file.errorString());
}
} // namespace client
