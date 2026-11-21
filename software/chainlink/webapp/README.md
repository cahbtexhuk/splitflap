# Splitflap web controller

A single Python process controls standard ESP32 Chainlink over USB or TCP/IP with the optional Wi-Fi firmware. The dashboard provides text, clear, module status, homing, offsets and logs. Classic Arduino and Chainlink Base-specific controls are not supported.

## Setup

Install Python 3.10 or 3.11. From the repository root on Windows:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r software\chainlink\webapp\requirements.txt
.\.venv\Scripts\python software\chainlink\webapp\app.py
```

On Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r software/chainlink/webapp/requirements.txt
.venv/bin/python software/chainlink/webapp/app.py
```

Open http://127.0.0.1:8765 and select Serial or IP / hostname on the Connection page. The default network port is 23040. Only one TCP client can control the device; a new connection closes the previous one. The app does not reconnect automatically, so use Connect after a disconnect. Only one process can own a serial port; stop other monitors and examples first. On Linux, grant the service user serial-device permission, commonly through the `dialout` group. Dependencies include an older protobuf runtime compatible with the checked-in generated files. Raspberry Pi Zero installation and performance have not yet been verified.

**Connecting may reset the ESP32 and cause automatic homing.** The app requests inactive DTR/RTS, but board and driver behavior can vary. Ensure the hardware is safe to move before connecting. Re-homing clears error counters. Offset adjustments move drums; saving is separate and must be confirmed by a firmware log. An ACK does not prove execution.

Sending text or clearing uses direct movement commands; a drum already at the requested flap can make a full revolution. A drum in an error state may ignore movement even when the command is acknowledged.

Older firmware can initially report default drum states when switching protocols. Upload current firmware containing the serial state-initialization fix before trusting initial readings. Uploading resets and may home the drums.

## LAN access

The listener defaults to loopback. For a trusted LAN, explicitly bind and allow the hostname or IP used by the browser:

```sh
.venv/bin/python software/chainlink/webapp/app.py --host 0.0.0.0 --allowed-host 192.168.1.50
```

Browse to `http://192.168.1.50:8765`. Repeat `--allowed-host` for each DNS name or address used. There is no login or TLS: anyone who can reach the service can operate the hardware. Restrict access with a firewall; use an authenticated HTTPS reverse proxy for wider access. Preserve the external Host and scheme and test origin checks. Do not expose directly to the internet. The app can connect to addresses on its host's network, so restrict who can access it.

## Verification

```sh
.venv/bin/python -m unittest discover -s software/chainlink/webapp/tests
```

Tests use a simulated device and do not move physical drums. Inspect reported errors and counters first, then test motion only when the mechanism can be observed. See [serial communication](../../../docs/SerialCommunication.md) for protocol and diagnostics.
## Offset display

Protocol version 2 firmware reports each drum's current offset in motor steps. Version 1 displays `--`; upload the current firmware to enable offset reporting. Offset adjustments are not persistent until explicitly saved.
## Display workflow

The dashboard has **Display Control**, **Config**, and **Connection** pages. Connection status stays in the header, and command/device logs remain visible on every page. Display Control provides left, center, and right alignment; short text is padded with blank flaps. By default, sends move only drums whose target flap changed. Enable **Flip all** to force every configured drum to rotate on each send. Clearing targets blanks across the configured display.

Config's drum count defaults to 10 and is saved as a host setting shared by browser clients. It may be lower than the firmware's detected driver capacity, such as 10 configured drums on a 12-output setup, but cannot exceed it. Extra outputs remain visible in hardware status and are not moved by display messages or included in drum selection.

The controller keeps message targets in memory only for the current serial session. It initializes them from fresh device status after connect and resets its baseline after reconnect or re-homing. No firmware or protocol changes are needed for changed-only movement.

## ESP32 Wi-Fi setup

The optional `chainlink_wifi` PlatformIO environment adds Wi-Fi; the existing `chainlink` environment remains serial-only. Define `SPLITFLAP_SETUP_AP_NAME`, a private 8-63-character `SPLITFLAP_SETUP_AP_PASSWORD`, and optionally `SPLITFLAP_TCP_PORT` in the gitignored `firmware/esp32/splitflap/wifi_setup_config.h`, using [the example](../../../firmware/esp32/splitflap/wifi_setup_config.h.example) as the template. Do not commit credentials. Build and upload `chainlink_wifi` only when the mechanism is safe to home; flashing resets the ESP32.

At boot the ESP32 tries saved Wi-Fi credentials for 30 seconds, then starts the protected setup AP. Connect to the AP and open `http://192.168.4.1/wificonfig`; choose a network and save. The setup AP remains available until configured. Saving Wi-Fi settings reboots the ESP32.

Once connected to Wi-Fi, access `http://<device-ip>/wificonfig` to change network settings. Find the device IP in the router's DHCP list, or use `splitflap-<device-id>.local` if mDNS resolves. The Python app connects to the device over TCP port 23040 by default.

The `chainlink_wifi` build accepts control commands only over TCP. Its serial port remains available for diagnostics at 230400 baud, and received serial bytes do not disable Wi-Fi. A serial monitor may still reset the ESP32 when it opens the port. Use the `chainlink` build for serial control. After a network outage, the Wi-Fi build retries the network.

**Trusted LAN only:** TCP control and the station-mode configuration portal have no authentication or encryption. The setup AP password only restricts access to the setup AP; it does not protect the portal on your normal network. Anyone on the LAN who can reach the device can control it or change its Wi-Fi credentials. Do not expose these services to the internet.

## Prop Clock

The Prop Clock tab sends explicit `HH:MM` targets through the connected controller; it does not advance automatically. The configured default time (initially `22:00`) prefills the time entry. **Set time** establishes a temporary runtime start/current time, **Reset to start** returns to that runtime start, and minute/hour buttons add exact time without rounding or persistently changing the default. Runtime state resets to the configured default when the app restarts. Clock output is centered regardless of the Display Control alignment setting.

The clock API can be used by Home Assistant, Stream Deck software, or another REST client on the LAN. For remote access, start the controller with a LAN bind and allowlist the address clients use, for example:

```bash
python software/chainlink/webapp/app.py --host 0.0.0.0 --allowed-host 192.168.1.50
```

Replace `192.168.1.50` with the controller's LAN address and use it in the request URL. POST requests require `Content-Type: application/json` and `X-Splitflap-Request: 1`; non-browser clients may omit `Origin`.

```bash
curl http://192.168.1.50:8765/api/clock

curl -X POST http://192.168.1.50:8765/api/clock/set-start \
  -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' \
  -d '{"time":"21:46"}'

curl -X POST http://192.168.1.50:8765/api/clock/add-minutes \
  -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' \
  -d '{"minutes":5}'

curl -X POST http://192.168.1.50:8765/api/clock/add-hours \
  -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' \
  -d '{"hours":1}'

curl -X POST http://192.168.1.50:8765/api/clock/reset \
  -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' \
  -d '{}'
```

`GET /api/clock` returns `start_time` and `current_time`. Mutation responses include those fields and the queued `operation` ID. `/api/clock/add-minutes` accepts 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, or 55; `/api/clock/add-hours` accepts 1 or 2. `/api/clock/set-start` accepts `{"time":"HH:MM"}`. Add-minute/hour routes accept `{"minutes":N}` or `{"hours":N}` respectively; reset accepts `{}`. Set the persistent form default through Config or `POST /api/settings` with `{"default_prop_clock_time":"22:00"}`.

Clock actions require the device to be connected, ready, and reporting fresh status. Responses confirm a command was queued, not that drum motion has completed. The LAN service has no login or TLS: restrict it to a trusted network/firewall and do not expose or port-forward it to the internet.