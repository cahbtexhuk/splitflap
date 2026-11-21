#pragma once

#include <stdint.h>

enum class WifiMode {
    CONNECTING,
    PROVISIONING,
    NETWORK,
};

class WifiModeSelector {
    public:
        explicit WifiModeSelector(uint32_t start) : start_(start) {}

        static constexpr WifiMode next(WifiMode mode, uint32_t elapsed, bool station_connected) {
            return mode == WifiMode::NETWORK ? WifiMode::NETWORK :
                   station_connected ? WifiMode::NETWORK :
                   elapsed >= 30000 ? WifiMode::PROVISIONING : mode;
        }

        WifiMode update(uint32_t now, bool station_connected) {
            return mode_ = next(mode_, now - start_, station_connected);
        }

    private:
        uint32_t start_;
        WifiMode mode_ = WifiMode::CONNECTING;
};