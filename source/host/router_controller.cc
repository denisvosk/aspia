//
// Aspia Project
// Copyright (C) 2016-2024 Dmitry Chapyshev <dmitry@aspia.ru>
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program. If not, see <https://www.gnu.org/licenses/>.
//

#include "host/router_controller.h"

#include "base/logging.h"
#include "base/task_runner.h"
#include "base/crypto/generic_hash.h"
#include "base/files/base_paths.h"
#include "base/files/file_path.h"
#include "base/peer/client_authenticator.h"
#include "base/strings/unicode.h"
#include "host/host_key_storage.h"
#include "proto/router_peer.pb.h"

namespace host {

namespace {

const std::chrono::seconds kReconnectTimeout{ 10 };

} // namespace

//--------------------------------------------------------------------------------------------------
RouterController::RouterController(std::shared_ptr<base::TaskRunner> task_runner)
    : task_runner_(task_runner),
      peer_manager_(std::make_unique<base::RelayPeerManager>(task_runner, this)),
      reconnect_timer_(base::WaitableTimer::Type::SINGLE_SHOT, task_runner),
      audit_timer_(base::WaitableTimer::Type::REPEATED, task_runner),
      inventory_collector_(std::make_unique<InventoryCollector>(task_runner)),
      inventory_timer_(base::WaitableTimer::Type::REPEATED, task_runner)
{
    LOG(LS_INFO) << "Ctor";
}

//--------------------------------------------------------------------------------------------------
RouterController::~RouterController()
{
    inventory_timer_.stop();
    inventory_collector_.reset();
    audit_timer_.stop();
    LOG(LS_INFO) << "Dtor";
}

//--------------------------------------------------------------------------------------------------
void RouterController::start(const RouterInfo& router_info, Delegate* delegate)
{
    router_info_ = router_info;
    delegate_ = delegate;

    if (!delegate_)
    {
        LOG(LS_ERROR) << "Invalid parameters";
        return;
    }

    LOG(LS_INFO) << "Starting host controller for router: "
                 << router_info_.address << ":" << router_info_.port;

    std::filesystem::path audit_path;
    if (base::BasePaths::commonAppData(&audit_path))
    {
        audit_path /= "aspia";
        std::error_code error;
        std::filesystem::create_directories(audit_path, error);
        const std::string identity = base::utf8FromUtf16(router_info.address) + ":" +
            std::to_string(router_info.port) + ":" + base::toHex(router_info.public_key);
        audit_path /= "host-audit-" + base::toHex(base::GenericHash::hash(
            base::GenericHash::Type::BLAKE2s256, identity)) + ".db3";
        if (!error)
            audit_outbox_ = common::SessionAuditStore::open(base::utf8FromFilePath(audit_path));
        if (audit_outbox_ && !audit_outbox_->interruptOutbox())
            audit_outbox_.reset();
    }
    if (!audit_outbox_)
        LOG(LS_ERROR) << "Host session audit outbox unavailable";
    audit_timer_.start(std::chrono::seconds(30), [this]() { checkpointAudit(); });
    inventory_timer_.start(std::chrono::hours(1), [this]() { refreshInventory(); });

    connectToRouter();
}

//--------------------------------------------------------------------------------------------------
void RouterController::hostIdRequest(const std::string& session_name)
{
    LOG(LS_INFO) << "Started ID request for session '" << session_name << "'";

    if (!channel_ || !channel_->isConnected())
    {
        LOG(LS_INFO) << "No active connection to the router";
        return;
    }

    HostKeyStorage host_key_storage;
    base::ByteArray host_key = host_key_storage.key(session_name);

    pending_id_requests_.emplace(session_name);

    proto::PeerToRouter message;
    proto::HostIdRequest* host_id_request = message.mutable_host_id_request();

    if (host_key.empty())
    {
        LOG(LS_INFO) << "Host key is empty. Request for a new ID";
        host_id_request->set_type(proto::HostIdRequest::NEW_ID);
    }
    else
    {
        LOG(LS_INFO) << "Host key is present. Request for an existing ID";
        host_id_request->set_type(proto::HostIdRequest::EXISTING_ID);
        host_id_request->set_key(base::toStdString(host_key));
    }

    // Send host ID request.
    LOG(LS_INFO) << "Send ID request to router";
    channel_->send(proto::ROUTER_CHANNEL_ID_SESSION, base::serialize(message));
}

//--------------------------------------------------------------------------------------------------
void RouterController::resetHostId(base::HostId host_id)
{
    audit_host_ids_.erase(host_id);
    LOG(LS_INFO) << "ResetHostId request: " << host_id;

    if (!channel_ || !channel_->isConnected())
    {
        LOG(LS_INFO) << "No active connection to the router";
        return;
    }

    proto::PeerToRouter message;
    message.mutable_reset_host_id()->set_host_id(host_id);
    channel_->send(proto::ROUTER_CHANNEL_ID_SESSION, base::serialize(message));
}

//--------------------------------------------------------------------------------------------------
void RouterController::onTcpConnected()
{
    DCHECK(channel_);

    LOG(LS_INFO) << "Connection to the router is established";

    channel_->setKeepAlive(true);
    channel_->setNoDelay(true);

    authenticator_ = std::make_unique<base::ClientAuthenticator>(task_runner_);

    authenticator_->setIdentify(proto::IDENTIFY_ANONYMOUS);
    authenticator_->setPeerPublicKey(router_info_.public_key);
    authenticator_->setSessionType(proto::ROUTER_SESSION_HOST);

    authenticator_->start(std::move(channel_),
                          [this](base::ClientAuthenticator::ErrorCode error_code)
    {
        if (error_code == base::ClientAuthenticator::ErrorCode::SUCCESS)
        {
            // The authenticator takes the listener on itself, we return the receipt of
            // notifications.
            channel_ = authenticator_->takeChannel();
            channel_->setListener(this);

            if (authenticator_->peerVersion() >= base::Version::kVersion_2_6_0)
            {
                LOG(LS_INFO) << "Using channel id support";
                channel_->setChannelIdSupport(true);
            }

            LOG(LS_INFO) << "Router connected";
            routerStateChanged(proto::internal::RouterState::CONNECTED);

            // Now the session will receive incoming messages.
            channel_->resume();
        }
        else
        {
            LOG(LS_ERROR) << "Authentication failed: "
                          << base::ClientAuthenticator::errorToString(error_code);
            delayedConnectToRouter();
        }

        // Authenticator is no longer needed.
        task_runner_->deleteSoon(std::move(authenticator_));
    });
}

//--------------------------------------------------------------------------------------------------
void RouterController::onTcpDisconnected(base::NetworkChannel::ErrorCode error_code)
{
    audit_supported_ = false;
    inventory_supported_ = false;
    audit_host_ids_.clear();
    audit_in_flight_.clear();
    LOG(LS_INFO) << "Connection to the router is lost ("
                 << base::NetworkChannel::errorToString(error_code) << ")";

    routerStateChanged(proto::internal::RouterState::FAILED);
    delayedConnectToRouter();
}

//--------------------------------------------------------------------------------------------------
void RouterController::onTcpMessageReceived(uint8_t /* channel_id */, const base::ByteArray& buffer)
{
    proto::RouterToPeer in_message;
    if (!base::parse(buffer, &in_message))
    {
        LOG(LS_ERROR) << "Invalid message from router";
        return;
    }

    if (in_message.has_host_id_response())
    {
        if (pending_id_requests_.empty())
        {
            LOG(LS_ERROR) << "ID received, but no request was sent";
            return;
        }

        const proto::HostIdResponse& host_id_response = in_message.host_id_response();

        switch (host_id_response.error_code())
        {
            case proto::HostIdResponse::SUCCESS:
                break;

            // The specified host is not in the router's database.
            case proto::HostIdResponse::NO_HOST_FOUND:
            {
                LOG(LS_INFO) << "Host is not in the router's database. Reset ID";

                proto::PeerToRouter out_message;
                out_message.mutable_host_id_request()->set_type(proto::HostIdRequest::NEW_ID);

                // Send host ID request.
                LOG(LS_INFO) << "Send ID request to router";
                channel_->send(proto::ROUTER_CHANNEL_ID_SESSION, base::serialize(out_message));
                return;
            }

            default:
                LOG(LS_ERROR) << "Unknown error code: " << host_id_response.error_code();
                return;
        }

        base::HostId host_id = host_id_response.host_id();
        if (host_id == base::kInvalidHostId)
        {
            LOG(LS_ERROR) << "Invalid host ID received";
            return;
        }

        const std::string& session_name = pending_id_requests_.front();
        HostKeyStorage host_key_storage;

        base::ByteArray host_key = base::fromStdString(host_id_response.key());
        if (!host_key.empty())
        {
            LOG(LS_INFO) << "New host key received";
            host_key_storage.setKey(session_name, host_key);
        }

        LOG(LS_INFO) << "Host ID received: " << host_id << " session name: '" << session_name << "'";

        if (host_key_storage.lastHostId(session_name) != host_id)
            host_key_storage.setLastHostId(session_name, host_id);

        delegate_->onHostIdAssigned(session_name, host_id);
        pending_id_requests_.pop();
        audit_supported_ = host_id_response.session_audit_supported();
        inventory_supported_ = host_id_response.inventory_supported();
        audit_host_ids_.insert(host_id);
        flushAudit();
        refreshInventory();
    }
    else if (in_message.has_connection_offer())
    {
        LOG(LS_INFO) << "New connection offer";

        const proto::ConnectionOffer& connection_offer = in_message.connection_offer();

        if (connection_offer.error_code() == proto::ConnectionOffer::SUCCESS &&
            connection_offer.peer_role() == proto::ConnectionOffer::HOST)
        {
            peer_manager_->addConnectionOffer(connection_offer);
        }
        else
        {
            LOG(LS_ERROR) << "Invalid connection offer";
        }
    }
    else if (in_message.has_session_audit_ack())
    {
        const auto& ack = in_message.session_audit_ack();
        auto in_flight = audit_in_flight_.find(ack.event_id());
        if (in_flight != audit_in_flight_.end() && in_flight->second == ack.revision())
            audit_in_flight_.erase(in_flight);
        if (audit_outbox_ && ack.accepted())
        {
            if (!audit_outbox_->acknowledge(ack))
                LOG(LS_ERROR) << "Unable to persist session audit acknowledgement";
            else
                flushAudit();
        }
        else
        {
            LOG(LS_ERROR) << "Router did not acknowledge session audit; retained for retry";
            // A malformed or temporarily rejected entry must not starve subsequent entries.
            if (audit_outbox_ && audit_outbox_->defer(ack))
                flushAudit();
        }
    }
    else
    {
        LOG(LS_ERROR) << "Unhandled message from router";
    }
}

//--------------------------------------------------------------------------------------------------
void RouterController::onTcpMessageWritten(
    uint8_t /* channel_id */, base::ByteArray&& /* buffer */, size_t /* pending */)
{
    // Nothing
}

//--------------------------------------------------------------------------------------------------
void RouterController::onNewPeerConnected(std::unique_ptr<base::TcpChannel> channel)
{
    LOG(LS_INFO) << "New peer connected";

    if (delegate_)
    {
        delegate_->onClientConnected(std::move(channel));
    }
    else
    {
        LOG(LS_ERROR) << "Invalid delegate";
    }
}

//--------------------------------------------------------------------------------------------------
void RouterController::connectToRouter()
{
    audit_supported_ = false;
    inventory_supported_ = false;
    audit_host_ids_.clear();
    audit_in_flight_.clear();
    LOG(LS_INFO) << "Connecting to router...";

    routerStateChanged(proto::internal::RouterState::CONNECTING);

    channel_ = std::make_unique<base::TcpChannel>();
    channel_->setListener(this);
    channel_->connect(router_info_.address, router_info_.port);
}

//--------------------------------------------------------------------------------------------------
void RouterController::delayedConnectToRouter()
{
    LOG(LS_INFO) << "Reconnect after " << kReconnectTimeout.count() << " seconds";
    reconnect_timer_.start(kReconnectTimeout, std::bind(&RouterController::connectToRouter, this));
}

//--------------------------------------------------------------------------------------------------
void RouterController::routerStateChanged(proto::internal::RouterState::State state)
{
    LOG(LS_INFO) << "Router state changed: " << routerStateToString(state);

    if (!delegate_)
    {
        LOG(LS_INFO) << "Invalid delegate";
        return;
    }

    proto::internal::RouterState router_state;
    router_state.set_state(state);

    router_state.set_host_name(base::utf8FromUtf16(router_info_.address));
    router_state.set_host_port(router_info_.port);

    delegate_->onRouterStateChanged(router_state);
}

//--------------------------------------------------------------------------------------------------
// static
const char* RouterController::routerStateToString(proto::internal::RouterState::State state)
{
    switch (state)
    {
        case proto::internal::RouterState::DISABLED:
            return "DISABLED";

        case proto::internal::RouterState::CONNECTING:
            return "CONNECTING";

        case proto::internal::RouterState::CONNECTED:
            return "CONNECTED";

        case proto::internal::RouterState::FAILED:
            return "FAILED";

        default:
            return "UNKNOWN";
    }
}


//--------------------------------------------------------------------------------------------------
void RouterController::recordAudit(proto::SessionAuditRecord record)
{
    if (!audit_outbox_)
    {
        LOG(LS_ERROR) << "Unable to save session audit: outbox unavailable";
        return;
    }
    const std::string event_id = record.event_id();
    const auto checkpoint = std::chrono::steady_clock::now();
    const bool saved = audit_outbox_->queue(&record);
    if (!saved)
        LOG(LS_ERROR) << "Unable to commit session audit; retaining in memory for retry";
    if (record.state() == proto::SessionAuditRecord::ACTIVE || !saved)
        active_audits_[event_id] = ActiveAudit{std::move(record), checkpoint};
    else
        active_audits_.erase(event_id);
    flushAudit();
}

//--------------------------------------------------------------------------------------------------
void RouterController::checkpointAudit()
{
    if (!audit_outbox_)
        return;
    // Retry a lost ACK, with at most 16 records in flight. The Router de-duplicates revisions.
    audit_in_flight_.clear();
    const auto now = std::chrono::steady_clock::now();
    if (!audit_outbox_->retryDeferred())
        LOG(LS_ERROR) << "Unable to schedule deferred audit records for retry";
    for (auto it = active_audits_.begin(); it != active_audits_.end();)
    {
        proto::SessionAuditRecord record = it->second.record;
        if (record.state() == proto::SessionAuditRecord::ACTIVE)
        {
            const auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
                now - it->second.checkpoint).count();
            record.set_duration_seconds(record.duration_seconds() + static_cast<uint64_t>(elapsed));
        }
        if (!audit_outbox_->queue(&record))
        {
            LOG(LS_ERROR) << "Unable to persist session audit checkpoint";
            ++it;
            continue;
        }
        if (record.state() != proto::SessionAuditRecord::ACTIVE)
        {
            it = active_audits_.erase(it);
            continue;
        }
        it->second = ActiveAudit{std::move(record), now};
        ++it;
    }
    flushAudit();
}

//--------------------------------------------------------------------------------------------------
void RouterController::flushAudit()
{
    if (!audit_outbox_ || !audit_supported_ || !channel_ || !channel_->isConnected())
        return;
    for (const auto host_id : audit_host_ids_)
    {
        const auto records = audit_outbox_->pending(host_id, 32);
        for (const auto& record : records)
        {
            if (audit_in_flight_.size() >= 16)
                return;
            if (audit_in_flight_.count(record.event_id()))
                continue;
            proto::PeerToRouter message;
            *message.mutable_session_audit_event() = record;
            audit_in_flight_[record.event_id()] = record.revision();
            channel_->send(proto::ROUTER_CHANNEL_ID_SESSION, base::serialize(message));
        }
    }
}


//--------------------------------------------------------------------------------------------------
void RouterController::refreshInventory()
{
    if (!inventory_supported_ || audit_host_ids_.empty() || !channel_ || !channel_->isConnected())
        return;
    const auto now = std::chrono::steady_clock::now();
    if (!cached_inventory_ || now - inventory_collected_at_ >= std::chrono::hours(24))
    {
        inventory_collector_->collect(*audit_host_ids_.begin(), [this](proto::InventorySnapshot snapshot)
        {
            if (snapshot.collected_at() <= 0 || snapshot.computer_name().empty())
            {
                LOG(LS_ERROR) << "Automatic inventory failed; previous snapshot retained for retry";
                return;
            }
            cached_inventory_ = std::move(snapshot);
            inventory_collected_at_ = std::chrono::steady_clock::now();
            sendInventory();
        });
    }
    else
    {
        // Re-send the cached daily snapshot after reconnect and periodically. Its collection
        // time remains unchanged, so delayed/repeated receipt cannot make stale hardware fresh.
        sendInventory();
    }
}

//--------------------------------------------------------------------------------------------------
void RouterController::sendInventory()
{
    if (!inventory_supported_ || !cached_inventory_ || !channel_ || !channel_->isConnected())
        return;
    for (const auto host_id : audit_host_ids_)
    {
        proto::PeerToRouter message;
        *message.mutable_inventory_snapshot() = *cached_inventory_;
        message.mutable_inventory_snapshot()->set_host_id(host_id);
        channel_->send(proto::ROUTER_CHANNEL_ID_SESSION, base::serialize(message));
    }
}

} // namespace host
