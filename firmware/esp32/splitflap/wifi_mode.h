#pragma once

#include <stdint.h>

enum class WifiMode {
    CONNECTING,
    PROVISIONING,
    NETWORK,
    SERIAL_LOCKED,
};

class WifiModeSelector {
    public:
        explicit WifiModeSelector(uint32_t start) : start_(start) {}

        static constexpr WifiMode next(WifiMode mode, uint32_t elapsed, bool serial_available,
                                       bool station_connected) {
            return mode == WifiMode::SERIAL_LOCKED || serial_available ? WifiMode::SERIAL_LOCKED :
                   mode == WifiMode::NETWORK ? WifiMode::NETWORK :
                   elapsed >= 300000 ? WifiMode::SERIAL_LOCKED :
                   station_connected ? WifiMode::NETWORK :
                   elapsed >= 30000 ? WifiMode::PROVISIONING : mode;
        }

        WifiMode update(uint32_t now, bool serial_available, bool station_connected) {
            return mode_ = next(mode_, now - start_, serial_available, station_connected);
        }

    private:
        uint32_t start_;
        WifiMode mode_ = WifiMode::CONNECTING;
};