# Serial communication knowledge base

## Hardware and startup

The default `chainlink` PlatformIO environment is ESP32, six modules, 230400 baud, 8N1, without flow control. The selected character set has 45 flaps, but module count and alphabet are build-dependent and must be obtained from the device. See [platformio.ini](../platformio.ini), [config.h](../firmware/src/config.h), and [UART setup](../firmware/esp32/core/uart_stream.cpp).

Opening the serial port can reset the ESP32 via DTR/RTS. Startup automatically homes drums. The web controller requests inactive DTR/RTS, but driver and board behavior varies. Ensure the hardware is safe to move before connecting.

## Protocols

The [serial task](../firmware/esp32/splitflap/serial_task.cpp) starts in legacy mode. A zero byte switches it to protobuf without changing baud rate. Send an initial zero followed by a state request; tolerate startup text and a dropped first frame. If already in protobuf mode the extra zero may produce a harmless `Small packet` log.

### Protobuf

The canonical schema is [splitflap.proto](../proto/splitflap.proto); the firmware handler is [serial_proto_protocol.cpp](../firmware/esp32/splitflap/serial_proto_protocol.cpp). A packet is a serialized protobuf payload followed by its CRC32 in four little-endian bytes, COBS-encoded and terminated with zero.

`ToSplitflap.nonce` identifies a request. The firmware ACKs a valid decoded packet before dispatch and suppresses a repeat of the most recently handled nonce. Retry using the same nonce; use a different nonce for each new request. An ACK confirms receipt, not execution, completed motion, or a successful save.

`request_state` requests module and general state. State is sent on change, rate-limited to about 100 ms, and at least every five seconds; general state is sent approximately every two seconds. Protocol version 1 includes the device character set, build and uptime. Version 2 adds current per-module offsets in motor steps; version 1 does not report offsets.

Older firmware can report default values after switching to protobuf until a module changes state. Current source initializes the newly selected protocol with the current state. Build and upload the updated firmware before trusting the initial snapshot; uploading resets the device and may trigger homing.

| Message | Purpose |
| --- | --- |
| `SplitflapConfig` | Target indices and movement/reset nonces. Changing the movement nonce forces motion; changing the reset nonce clears counters and re-homes. |
| `SplitflapCommand` | Module actions or `save_all_offsets`, sent separately without a module list. |
| `SplitflapState` | State, flap index, moving and sensor flags, error counters, offsets (version 2), and Chainlink loopback state. |
| `GeneralState` | Protocol version, build, uptime and flap character set on standard Chainlink firmware. |
| `SupervisorState` | Power supervisor details for Chainlink Base, not standard Chainlink. |
| `Log` | Firmware messages, including offset save outcomes. |
| `Ack` | Receipt of a valid request with its nonce. |

`GO_TO_FLAP` takes a zero-based flap index. `RESET_AND_HOME` resets and re-homes addressed modules and clears their counters. `NO_OP` leaves an indexed module unchanged. Offset actions increase by one tenth or one half flap, wrapping forward; `SET_OFFSET` uses the current step. `save_all_offsets` is processed only if every module is stopped, with success or failure in logs. Clearing is not reset: command the reported blank flap on each module. Direct movement commands can cause a full revolution even when already at the target, and modules in error states may ignore them despite an ACK.

States are `NORMAL`, `LOOK_FOR_HOME`, `SENSOR_ERROR`, `PANIC`, and `STATE_DISABLED`. The counters record missed and unexpected home sensor events. The default Chainlink LED pattern uses the state number as the number of blinks, so two blinks suggest `SENSOR_ERROR`; confirm with reported state. `moving` and `home_state` report motor motion and sensor input.

### Legacy text protocol

The [legacy firmware handler](../firmware/esp32/splitflap/serial_legacy_json_protocol.cpp) accepts `=<text>\n` to display text, `@` to reset and home all drums, `#` for a no-op response, `%` to toggle sensor test, `>` and `<` to adjust the first module's offset, and `\` to save offsets. Responses are newline-delimited JSON; input is not JSON. `#` is not a full state request. Older Arduino examples used 38400 baud; ESP32 firmware uses 230400 even in legacy mode. See the [classic Python client](../software/classic/splitflap.py).

## Existing software

- [Python Chainlink client](../software/chainlink/splitflap_proto.py): framing, handlers, `set_text`, state requests and 250 ms retries. It uses an unbounded queue and waits indefinitely for startup/ACKs; `set_text` substitutes index zero for unsupported characters. Its requirements file omits some imported dependencies.
- [JavaScript protocol core](../software/chainlink/js/packages/splitflapjs-core/src/index.ts): equivalent framing and offset commands; its queue policy differs from Python.
- [Web controller](../software/chainlink/webapp/README.md): local-first Python host with bounded queue and connection errors, supporting text, clear, homing, offsets, status and logs.

## Troubleshooting

Check port and baud, close competing serial monitors, and allow time for startup after reset. On Linux, grant serial-device permissions. If compatible general state does not arrive, firmware may be older or a different build. Sensor errors, missed-home counters and loopback faults require hardware investigation. Re-homing clears counters, so record diagnostics first. Confirm offset saves using firmware logs rather than ACK alone.