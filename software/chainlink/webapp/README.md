# Splitflap web controller

A single Python process controls standard ESP32 Chainlink over USB. The dashboard provides text, clear, module status, homing, offsets and logs. Classic Arduino and Chainlink Base-specific controls are not supported.

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

Open http://127.0.0.1:8765 and select the serial port. Only one process can own it; stop other monitors and examples first. On Linux, grant the service user serial-device permission, commonly through the `dialout` group. Dependencies include an older protobuf runtime compatible with the checked-in generated files. Raspberry Pi Zero installation and performance have not yet been verified.

**Connecting may reset the ESP32 and cause automatic homing.** The app requests inactive DTR/RTS, but board and driver behavior can vary. Ensure the hardware is safe to move before connecting. Re-homing clears error counters. Offset adjustments move drums; saving is separate and must be confirmed by a firmware log. An ACK does not prove execution.

Sending text or clearing uses direct movement commands; a drum already at the requested flap can make a full revolution. A drum in an error state may ignore movement even when the command is acknowledged.

Older firmware can initially report default drum states when switching protocols. Upload current firmware containing the serial state-initialization fix before trusting initial readings. Uploading resets and may home the drums.

## LAN access

The listener defaults to loopback. For a trusted LAN, explicitly bind and allow the hostname or IP used by the browser:

```sh
.venv/bin/python software/chainlink/webapp/app.py --host 0.0.0.0 --allowed-host 192.168.1.50
```

Browse to `http://192.168.1.50:8765`. Repeat `--allowed-host` for each DNS name or address used. There is no login or TLS: anyone who can reach the service can operate the hardware. Restrict access with a firewall; use an authenticated HTTPS reverse proxy for wider access. Preserve the external Host and scheme and test origin checks. Do not expose directly to the internet.

## Verification

```sh
.venv/bin/python -m unittest discover -s software/chainlink/webapp/tests
```

Tests use a simulated device and do not move physical drums. Inspect reported errors and counters first, then test motion only when the mechanism can be observed. See [serial communication](../../../docs/SerialCommunication.md) for protocol and diagnostics.
## Offset display

Protocol version 2 firmware reports each drum's current offset in motor steps. Version 1 displays `--`; upload the current firmware to enable offset reporting. Offset adjustments are not persistent until explicitly saved.