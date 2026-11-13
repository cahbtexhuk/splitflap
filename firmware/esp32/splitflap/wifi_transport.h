#pragma once

#if SPLITFLAP_WIFI
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include <atomic>

#include "../core/logger.h"
#include "../core/task.h"
#if !__has_include("wifi_setup_config.h")
#error "Create firmware/esp32/splitflap/wifi_setup_config.h from wifi_setup_config.h.example"
#endif
#include "wifi_setup_config.h"

class WifiTransport : public Stream, public Task<WifiTransport> {
    friend class Task<WifiTransport>;

    public:
        WifiTransport(Logger& logger, uint8_t task_core);
        void selectSerial();
        bool serialSelected() const;
        bool takeNewClient();
        bool hasClient();
        int available() override;
        int read() override;
        int peek() override;
        void flush() override;
        size_t write(uint8_t value) override;
        size_t write(const uint8_t* data, size_t size) override;

    protected:
        void run();

    private:
        Logger& logger_;
        WiFiManager manager_;
        WiFiServer server_;
        WiFiClient client_;
        SemaphoreHandle_t client_mutex_;
        std::atomic<bool> serial_selected_{false};
        bool new_client_ = false;
        bool listener_started_ = false;
        bool web_portal_started_ = false;
        bool provisioning_started_ = false;
        bool mdns_started_ = false;
        std::atomic<bool> reboot_requested_{false};

        void configurePortal();
        void stopNetwork();
        void serviceClient();
};

class ProtocolStream : public Stream {
    public:
        ProtocolStream(Stream& serial, Stream& network) : serial_(serial), network_(network) {}
        void useSerial(bool enabled) { serial_active_ = enabled; }
        int available() override { return !serial_active_ && serial_.available() ? 0 : current().available(); }
        int read() override { return current().read(); }
        int peek() override { return current().peek(); }
        void flush() override { current().flush(); }
        size_t write(uint8_t value) override { return !serial_active_ && serial_.available() ? 0 : current().write(value); }
        size_t write(const uint8_t* data, size_t size) override { return !serial_active_ && serial_.available() ? 0 : current().write(data, size); }

    private:
        Stream& current() { return serial_active_ ? serial_ : network_; }
        Stream& serial_;
        Stream& network_;
        bool serial_active_ = false;
};
#endif