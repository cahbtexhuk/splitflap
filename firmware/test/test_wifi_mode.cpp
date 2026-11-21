#include "../esp32/splitflap/wifi_mode.h"

static_assert(WifiModeSelector::next(WifiMode::CONNECTING, 29999, false) == WifiMode::CONNECTING, "initial connection period");
static_assert(WifiModeSelector::next(WifiMode::CONNECTING, 1, true) == WifiMode::NETWORK, "saved network connected");
static_assert(WifiModeSelector::next(WifiMode::CONNECTING, 30000, false) == WifiMode::PROVISIONING, "AP after 30 seconds");
static_assert(WifiModeSelector::next(WifiMode::PROVISIONING, 40000, false) == WifiMode::PROVISIONING, "provisioning remains active");
static_assert(WifiModeSelector::next(WifiMode::PROVISIONING, 299999, true) == WifiMode::NETWORK, "connected before five minutes");
static_assert(WifiModeSelector::next(WifiMode::PROVISIONING, 300000, false) == WifiMode::PROVISIONING, "AP remains available after five minutes");
static_assert(WifiModeSelector::next(WifiMode::PROVISIONING, 300000, true) == WifiMode::NETWORK, "connected after five minutes");
static_assert(WifiModeSelector::next(WifiMode::NETWORK, 400000, false) == WifiMode::NETWORK, "network loss does not switch mode");
static_assert(WifiModeSelector::next(WifiMode::NETWORK, 400001, true) == WifiMode::NETWORK, "network remains active after reconnect");
static_assert(WifiModeSelector::next(WifiMode::CONNECTING, uint32_t(10000) - uint32_t(0xffffb1e0), false) == WifiMode::PROVISIONING, "elapsed time wraps safely");