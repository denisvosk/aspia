// Aspia Web Gateway prototype. GPL-3.0-or-later, same license as Aspia.
// One process per remote session. Only the parent service can access its stdio.
#include "client/client.h"
#include "client/status_window_proxy.h"
#include "base/logging.h"
#include "base/message_loop/message_loop.h"
#include "base/codec/video_decoder.h"
#include "base/desktop/frame_simple.h"
#include "base/desktop/pixel_format.h"
#include "proto/desktop.pb.h"

#include <QCoreApplication>
#include <QBuffer>
#include <QImage>
#include <QJsonDocument>
#include <QJsonObject>
#include <algorithm>
#include <iostream>
#include <set>
#include <thread>
#include <fcntl.h>
#include <io.h>

namespace {
void output(const QJsonObject& value)
{
    const QByteArray bytes = QJsonDocument(value).toJson(QJsonDocument::Compact);
    std::cout.write(bytes.constData(), bytes.size());
    std::cout << '\n' << std::flush;
}
void status(const char* state)
{
    output({{"type", "status"}, {"state", state}});
}

class Bridge final : public client::Client, public client::StatusWindow
{
public:
    Bridge(std::shared_ptr<base::TaskRunner> runner, const QJsonObject& json)
        : Client(runner), runner_(runner)
    {
        client::Config config;
        config.router_config.emplace();
        config.router_config->address = json["routerAddress"].toString().toStdU16String();
        config.router_config->port = static_cast<uint16_t>(json["routerPort"].toInt());
        config.router_config->username = json["routerUser"].toString().toStdU16String();
        config.router_config->password = json["routerPassword"].toString().toStdU16String();
        config.address_or_id = json["hostId"].toString().toStdU16String();
        config.username = json["hostUser"].toString().toStdU16String();
        config.password = json["hostPassword"].toString().toStdU16String();
        config.display_name = json["displayName"].toString().toStdU16String();
        config.session_type = proto::SESSION_TYPE_DESKTOP_MANAGE;
        setSessionState(std::make_shared<client::SessionState>(config));
        proxy_ = std::make_shared<client::StatusWindowProxy>(runner, this);
        setStatusWindow(proxy_);
    }
    ~Bridge() final { stop(); proxy_->dettach(); }

    void command(const QJsonObject& json)
    {
        const QString type = json["type"].toString();
        if (type == "stop") { releaseInput(); stop(); runner_->postQuit(); return; }
        if (type == "frame") { frame(); return; }
        if (!connected_) return;
        if (type == "release") { releaseInput(); return; }
        proto::ClientToHost msg;
        if (type == "mouse" && frame_)
        {
            auto* mouse = msg.mutable_mouse_event();
            mouse_x_ = std::clamp(json["x"].toInt(), 0, screen_width_ - 1);
            mouse_y_ = std::clamp(json["y"].toInt(), 0, screen_height_ - 1);
            mouse->set_x(mouse_x_); mouse->set_y(mouse_y_);
            mouse->set_mask(static_cast<uint32_t>(json["mask"].toInt()) & 127);
        }
        else if (type == "key")
        {
            uint32_t code = static_cast<uint32_t>(json["code"].toInt());
            if (code < 0x070004 || code > 0x0700e7) return;
            const bool down = json["down"].toBool();
            if (down) keys_.insert(code); else keys_.erase(code);
            auto* key = msg.mutable_key_event();
            key->set_usb_keycode(code);
            key->set_flags(down ? proto::KeyEvent::PRESSED : 0);
        }
        else if (type == "text")
        {
            const QByteArray text = json["text"].toString().toUtf8();
            if (text.isEmpty() || text.size() > 8192) return;
            msg.mutable_text_event()->set_text(text.constData(), text.size());
        }
        else return;
        sendMessage(proto::HOST_CHANNEL_ID_SESSION, msg);
    }

private:
    void releaseInput()
    {
        if (!connected_) return;
        for (const auto key : keys_)
        {
            proto::ClientToHost msg;
            msg.mutable_key_event()->set_usb_keycode(key);
            sendMessage(proto::HOST_CHANNEL_ID_SESSION, msg);
        }
        keys_.clear();
        proto::ClientToHost msg;
        msg.mutable_mouse_event()->set_x(mouse_x_);
        msg.mutable_mouse_event()->set_y(mouse_y_);
        sendMessage(proto::HOST_CHANNEL_ID_SESSION, msg);
    }
    void frame()
    {
        if (!frame_ || !dirty_) { output({{"type", "idle"}}); return; }
        QImage view(frame_->frameData(), frame_->size().width(), frame_->size().height(),
                    frame_->stride(), QImage::Format_RGB32);
        QByteArray png;
        QBuffer buffer(&png);
        buffer.open(QIODevice::WriteOnly);
        if (!view.save(&buffer, "PNG") || png.size() > 24 * 1024 * 1024)
        { status("frame_error"); return; }
        output({{"type", "frame"}, {"png", QString::fromLatin1(png.toBase64())},
                {"width", frame_->size().width()}, {"height", frame_->size().height()},
                {"screenWidth", screen_width_}, {"screenHeight", screen_height_}});
        dirty_ = false;
    }
    void onSessionStarted() final { connected_ = true; status("connected"); }
    void onSessionMessageWritten(uint8_t, size_t) final {}
    void onSessionMessageReceived(uint8_t, const base::ByteArray& data) final
    {
        proto::HostToClient msg;
        if (!base::parse(data, &msg)) { status("protocol_error"); return; }
        if (msg.has_capabilities())
        {
            if (!(msg.capabilities().video_encodings() & proto::VIDEO_ENCODING_ZSTD))
            { status("codec_error"); return; }
            proto::ClientToHost reply;
            auto* config = reply.mutable_config();
            // Lossless office image; no server clipboard, audio, wallpaper or input blocking.
            config->set_flags(0);
            config->set_video_encoding(proto::VIDEO_ENCODING_ZSTD);
            config->set_audio_encoding(proto::AUDIO_ENCODING_UNKNOWN);
            config->set_compress_ratio(3);
            config->set_scale_factor(100);
            config->set_update_interval(30);
            auto* format = config->mutable_pixel_format();
            format->set_bits_per_pixel(32);
            format->set_red_max(255); format->set_green_max(255); format->set_blue_max(255);
            format->set_red_shift(16); format->set_green_shift(8); format->set_blue_shift(0);
            sendMessage(proto::HOST_CHANNEL_ID_SESSION, reply);
        }
        if (!msg.has_video_packet()) return;
        const auto& packet = msg.video_packet();
        if (packet.error_code() != proto::VIDEO_ERROR_CODE_OK)
        { output({{"type", "videoStatus"}, {"code", int(packet.error_code())}}); return; }
        if (packet.encoding() != proto::VIDEO_ENCODING_ZSTD)
        { status("codec_error"); return; }
        if (packet.has_format())
        {
            const auto& f = packet.format();
            const int w = f.video_rect().width(), h = f.video_rect().height();
            if (w <= 0 || h <= 0 || w > 8192 || h > 8192 || int64_t(w) * h > 16000000)
            { status("screen_too_large"); return; }
            screen_width_ = f.has_screen_size() ? f.screen_size().width() : w;
            screen_height_ = f.has_screen_size() ? f.screen_size().height() : h;
            if (screen_width_ <= 0 || screen_height_ <= 0 ||
                screen_width_ > 32768 || screen_height_ > 32768)
            { status("protocol_error"); return; }
            frame_ = base::FrameSimple::create(base::Size(w, h), base::PixelFormat::ARGB());
            decoder_ = base::VideoDecoder::create(proto::VIDEO_ENCODING_ZSTD);
        }
        if (!frame_ || !decoder_) return;
        if (!decoder_->decode(packet, frame_.get())) { status("decode_error"); return; }
        dirty_ = true;
    }
    void onStarted() final { status("starting"); }
    void onStopped() final { connected_ = false; status("stopped"); }
    void onRouterConnecting() final { status("router_connecting"); }
    void onRouterConnected() final { status("router_connected"); }
    void onHostConnecting() final { status("host_connecting"); }
    void onHostConnected() final {}
    void onHostDisconnected(base::TcpChannel::ErrorCode) final
        { connected_ = false; status("disconnected"); }
    void onWaitForRouter() final { status("waiting_router"); }
    void onWaitForHost() final { status("waiting_host"); }
    void onWaitForRouterTimeout() final { status("timeout"); }
    void onWaitForHostTimeout() final { status("timeout"); }
    void onVersionMismatch() final { status("version_mismatch"); }
    void onAccessDenied(base::ClientAuthenticator::ErrorCode) final { status("host_auth_error"); }
    void onRouterError(const client::RouterController::Error&) final { status("router_error"); }

    std::shared_ptr<base::TaskRunner> runner_;
    std::shared_ptr<client::StatusWindowProxy> proxy_;
    std::unique_ptr<base::FrameSimple> frame_;
    std::unique_ptr<base::VideoDecoder> decoder_;
    std::set<uint32_t> keys_;
    int screen_width_ = 1, screen_height_ = 1, mouse_x_ = 0, mouse_y_ = 0;
    bool dirty_ = false, connected_ = false;
};
} // namespace

int main(int argc, char** argv)
{
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
    base::LoggingSettings logging;
    logging.destination = base::LOG_NONE;
    logging.min_log_level = base::LOG_LS_FATAL;
    base::initLogging(logging); // stdout is a protocol, never a log or a crash dump.
    QCoreApplication app(argc, argv);
    if (argc == 2 && std::string(argv[1]) == "--self-test")
    {
        QImage image(2, 2, QImage::Format_RGB32);
        image.fill(0xff123456);
        QByteArray bytes; QBuffer buffer(&bytes); buffer.open(QIODevice::WriteOnly);
        if (!image.save(&buffer, "PNG")) return 1;
        output({{"type", "self-test"}, {"pngBytes", bytes.size()}});
        return 0;
    }
    // Credentials arrive only through the private anonymous pipe, never argv or disk.
    char initial[65536];
    if (!std::cin.getline(initial, sizeof(initial))) return 2;
    QJsonParseError error;
    QJsonDocument doc = QJsonDocument::fromJson(QByteArray(initial), &error);
    if (error.error != QJsonParseError::NoError || !doc.isObject()) return 2;
    base::MessageLoop loop(base::MessageLoop::Type::ASIO);
    auto runner = loop.taskRunner();
    auto bridge = std::make_unique<Bridge>(runner, doc.object());
    doc = QJsonDocument();
    std::fill(std::begin(initial), std::end(initial), 0);
    bridge->start();
    std::thread reader([runner, ptr = bridge.get()]()
    {
        char line[65536];
        while (std::cin.getline(line, sizeof(line)))
        {
            const QJsonDocument input = QJsonDocument::fromJson(QByteArray(line));
            if (!input.isObject()) break;
            QJsonObject command = input.object();
            runner->postTask([ptr, command]() { ptr->command(command); });
            if (command["type"].toString() == "stop") return;
        }
        runner->postTask([ptr, runner]() { ptr->stop(); runner->postQuit(); });
    });
    loop.run();
    reader.join();
    bridge.reset();
    return 0;
}
