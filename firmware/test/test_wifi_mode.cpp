#include "../esp32/splitflap/wifi_mode.h"

static_assert(WifiModeSelector::next(WifiMode::CONNECTING, 29999, false, false) == WifiMode::CONNECTING, "initial connection period");
static_assert(WifiModeSelector::next(WifiMode::CONNECTING, 1, true, false) == WifiMode::SERIAL_LOCKED, "serial during startup");
static_assert(WifiModeSelector::next(WifiMode::CONNECTING, 30000, false, false) == WifiMode::PROVISIONING, "AP after 30 seconds");
static_assert(WifiModeSelector::next(WifiMode::PROVISIONING, 40000, true, false) == WifiMode::SERIAL_LOCKED, "serial during provisioning");
static_assert(WifiModeSelector::next(WifiMode::PROVISIONING, 299999, false, true) == WifiMode::NETWORK, "connected before deadline");
static_assert(WifiModeSelector::next(WifiMode::PROVISIONING, 300000, false, true) == WifiMode::SERIAL_LOCKED, "absolute deadline");
static_assert(WifiModeSelector::next(WifiMode::NETWORK, 400000, false, false) == WifiMode::NETWORK, "network loss does not switch mode");
static_assert(WifiModeSelector::next(WifiMode::NETWORK, 1, true, true) == WifiMode::SERIAL_LOCKED, "serial takes priority");
static_assert(WifiModeSelector::next(WifiMode::SERIAL_LOCKED, 1, false, true) == WifiMode::SERIAL_LOCKED, "serial mode stays locked");