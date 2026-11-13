#if SPLITFLAP_WIFI
#include "wifi_transport.h"

#include <ESPmDNS.h>

#include "../core/semaphore_guard.h"
#include "wifi_mode.h"

constexpr bool validPasswordCharacters(const char* value) {
    return *value == '\0' || (*value >= 32 && *value <= 126 && validPasswordCharacters(value + 1));
}

static_assert(sizeof(SPLITFLAP_SETUP_AP_NAME) > 1, "Configure a setup AP name");
static_assert(sizeof(SPLITFLAP_SETUP_AP_PASSWORD) >= 9 && sizeof(SPLITFLAP_SETUP_AP_PASSWORD) <= 64,
              "Setup AP password must have 8 to 63 characters");
static_assert(validPasswordCharacters(SPLITFLAP_SETUP_AP_PASSWORD), "Setup AP password must use printable ASCII");
static_assert(SPLITFLAP_TCP_PORT > 0 && SPLITFLAP_TCP_PORT <= 65535, "Invalid TCP port");

WifiTransport::WifiTransport(Logger& logger, uint8_t task_core) :
        Task<WifiTransport>("WiFi", 12000, 1, task_core), logger_(logger),
        server_(SPLITFLAP_TCP_PORT, 2), client_mutex_(xSemaphoreCreateMutex()) {
    assert(client_mutex_ != nullptr);
}

void WifiTransport::selectSerial() {
    serial_selected_.store(true);
    {
        SemaphoreGuard lock(client_mutex_);
        client_.stop();
        new_client_ = false;
    }
    WiFi.mode(WIFI_OFF);
}

bool WifiTransport::serialSelected() const {
    return serial_selected_.load();
}

bool WifiTransport::takeNewClient() {
    SemaphoreGuard lock(client_mutex_);
    bool result = new_client_;
    new_client_ = false;
    return result;
}

bool WifiTransport::hasClient() {
    SemaphoreGuard lock(client_mutex_);
    return !serial_selected_.load() && client_.connected();
}

int WifiTransport::available() {
    SemaphoreGuard lock(client_mutex_);
    return serial_selected_.load() ? 0 : client_.available();
}

int WifiTransport::read() {
    SemaphoreGuard lock(client_mutex_);
    return serial_selected_.load() ? -1 : client_.read();
}

int WifiTransport::peek() {
    SemaphoreGuard lock(client_mutex_);
    return serial_selected_.load() ? -1 : client_.peek();
}

void WifiTransport::flush() {}

size_t WifiTransport::write(uint8_t value) {
    return write(&value, 1);
}

size_t WifiTransport::write(const uint8_t* data, size_t size) {
    SemaphoreGuard lock(client_mutex_);
    return serial_selected_.load() || !client_.connected() ? 0 : client_.write(data, size);
}

void WifiTransport::configurePortal() {
    manager_.setDebugOutput(false);
    manager_.setConfigPortalBlocking(false);
    manager_.setSaveConnect(false);
    manager_.setSaveConnectTimeout(1);
    manager_.setBreakAfterConfig(true);
    manager_.setShowPassword(false);
    manager_.setShowInfoErase(false);
    manager_.setShowInfoUpdate(false);
    manager_.setWebServerCallback([this]() {
        manager_.server->on("/wificonfig", HTTP_GET, [this]() {
            manager_.server->sendHeader("Location", "/wifi");
            manager_.server->send(302, "text/plain", "");
        });
        for (const char* path : {"/update", "/u", "/erase", "/restart", "/exit", "/close"}) {
            manager_.server->on(path, [this]() {
                manager_.server->send(403, "text/plain", "Disabled");
            });
        }
    });
    manager_.setSaveConfigCallback([this]() { reboot_requested_.store(true); });
}

void WifiTransport::stopNetwork() {
    if (listener_started_) {
        server_.stop();
        listener_started_ = false;
    }
    {
        SemaphoreGuard lock(client_mutex_);
        client_.stop();
        new_client_ = false;
    }
    if (manager_.getConfigPortalActive()) manager_.stopConfigPortal();
    if (manager_.getWebPortalActive()) manager_.stopWebPortal();
    if (mdns_started_) MDNS.end();
    WiFi.mode(WIFI_OFF);
}

void WifiTransport::serviceClient() {
    if (!listener_started_ || serial_selected_.load()) return;
    WiFiClient incoming = server_.available();
    if (!incoming) return;
    SemaphoreGuard lock(client_mutex_);
    if (serial_selected_.load() || client_.connected()) {
        incoming.stop();
        return;
    }
    client_.stop();
    client_ = incoming;
    client_.setNoDelay(true);
    client_.setTimeout(1);
    new_client_ = true;
}

void WifiTransport::run() {
    configurePortal();
    WifiModeSelector selector(millis());
    if (serial_selected_.load()) {
        stopNetwork();
        vTaskDelete(nullptr);
        return;
    }
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(WIFI_PS_NONE);
    WiFi.setAutoReconnect(true);
    WiFi.begin();
    uint32_t last_retry = millis();
    bool network_started = false;
    while (!serial_selected_.load()) {
        WifiMode mode = selector.update(millis(), serial_selected_.load(), WiFi.status() == WL_CONNECTED);
        if (mode == WifiMode::SERIAL_LOCKED) {
            serial_selected_.store(true);
            break;
        }
        if (mode == WifiMode::PROVISIONING && !provisioning_started_) {
            provisioning_started_ = true;
            manager_.startConfigPortal(SPLITFLAP_SETUP_AP_NAME, SPLITFLAP_SETUP_AP_PASSWORD);
            if (serial_selected_.load()) break;
            logger_.log("Wi-Fi setup access point started");
            WiFi.enableSTA(true);
            WiFi.begin();
            last_retry = millis();
        }
        if (mode == WifiMode::NETWORK && !network_started) {
            network_started = true;
            if (manager_.getConfigPortalActive()) manager_.stopConfigPortal();
            if (serial_selected_.load()) break;
            manager_.startWebPortal();
            web_portal_started_ = true;
            char hostname[32];
            snprintf(hostname, sizeof(hostname), "splitflap-%06x", (uint32_t)(ESP.getEfuseMac() & 0xFFFFFF));
            mdns_started_ = MDNS.begin(hostname);
            char message[96];
            if (mdns_started_) {
                snprintf(message, sizeof(message), "Wi-Fi connected: %s (%s.local)", WiFi.localIP().toString().c_str(), hostname);
            } else {
                snprintf(message, sizeof(message), "Wi-Fi connected: %s (mDNS unavailable)", WiFi.localIP().toString().c_str());
            }
            logger_.log(message);
        }
        if (mode == WifiMode::NETWORK && WiFi.status() == WL_CONNECTED) {
            if (!listener_started_) {
                server_.begin();
                listener_started_ = true;
            }
            serviceClient();
        } else if (network_started && listener_started_) {
            server_.stop();
            listener_started_ = false;
            SemaphoreGuard lock(client_mutex_);
            client_.stop();
        }
        if (manager_.getConfigPortalActive() || web_portal_started_) manager_.process();
        if (serial_selected_.load()) break;
        if (reboot_requested_.load() && !serial_selected_.load()) {
            delay(200);
            if (!serial_selected_.load()) ESP.restart();
        }
        if ((mode == WifiMode::PROVISIONING || mode == WifiMode::NETWORK)
                && WiFi.status() != WL_CONNECTED && millis() - last_retry >= 15000
                && !serial_selected_.load()) {
            if (!WiFi.reconnect() && !serial_selected_.load()) WiFi.begin();
            last_retry = millis();
        }
        delay(10);
    }
    stopNetwork();
    vTaskDelete(nullptr);
}
#endif