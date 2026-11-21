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
        bool new_client_ = false;
        bool listener_started_ = false;
        bool web_portal_started_ = false;
        bool provisioning_started_ = false;
        bool mdns_started_ = false;
        std::atomic<bool> reboot_requested_{false};

        void configurePortal();
        void serviceClient();
};
#endif