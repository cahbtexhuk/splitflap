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

Open http://127.0.0.1:8765 and select Serial or IP / hostname on the Connection page. The default network port is 23040. Only one process can own the device; stop other monitors and examples first. On Linux, grant the service user serial-device permission, commonly through the `dialout` group. Dependencies include an older protobuf runtime compatible with the checked-in generated files. Raspberry Pi Zero installation and performance have not yet been verified.

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

The optional `chainlink_wifi` PlatformIO environment adds Wi-Fi; the existing `chainlink` environment remains serial-only. Define `SPLITFLAP_SETUP_AP_NAME`, a private 8–63-character `SPLITFLAP_SETUP_AP_PASSWORD`, and optionally `SPLITFLAP_TCP_PORT` in the gitignored `firmware/esp32/splitflap/wifi_setup_config.h`, using [the example](../../../firmware/esp32/splitflap/wifi_setup_config.h.example) as the template. Do not commit credentials. Build and upload `chainlink_wifi` only when the mechanism is safe to home; flashing resets the ESP32.

At boot the ESP32 tries saved Wi-Fi credentials for 30 seconds, then starts the protected setup AP. Connect to the AP and open `http://192.168.4.1/wificonfig`; choose a network and save. Saving Wi-Fi settings reboots the ESP32. Without a successful network connection within five minutes of boot, it disables Wi-Fi and remains in serial mode until reboot.

Once connected to Wi-Fi, access `http://<device-ip>/wificonfig` to change network settings. The ESP32 reports its IP and `splitflap-<device-id>.local` name on serial output at connection time; using a serial monitor that sends bytes selects serial mode instead. Alternatively, find the device IP in the router's DHCP list. mDNS names may not resolve on every host; use the IP address if needed. The Python app connects to the device over TCP port 23040 by default.

**Any serial byte at any time disables Wi-Fi until the ESP32 reboots.** Serial auto-connect from the app can therefore interrupt Wi-Fi. Once Wi-Fi has connected, a subsequent network outage keeps the device in Wi-Fi mode and it retries the network rather than automatically switching to serial.

**Trusted LAN only:** TCP control and the station-mode configuration portal have no authentication or encryption. The setup AP password only restricts access to the setup AP; it does not protect the portal on your normal network. Anyone on the LAN who can reach the device can control it or change its Wi-Fi credentials. Do not expose these services to the internet.