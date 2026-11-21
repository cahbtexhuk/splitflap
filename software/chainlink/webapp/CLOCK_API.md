# Prop clock API

Use the Python web controller's HTTP address, for example `http://192.168.1.50:8765`, not the ESP32's TCP port `23040`. Replace the example address with the controller host's IP or hostname. The host must be included in `--allowed-host` when starting the app; see [DOCKER.md](DOCKER.md) for container setup.

The controller must be connected to the display and report fresh status before clock commands can be queued. Connect manually on the Connection page or use the connect request below. The API has no login or TLS; use only on a trusted LAN and do not expose it to the internet.

## Stream Deck request settings

For each button, configure an HTTP/REST action with the listed method, URL, and JSON body. Every POST requires both headers:

```text
Content-Type: application/json
X-Splitflap-Request: 1
```

Server-side REST clients can omit `Origin`. The app rejects a browser POST whose `Origin` does not match the request host.

| Button | Method | URL | JSON body |
| --- | --- | --- | --- |
| Clock state | GET | `http://192.168.1.50:8765/api/clock` | None |
| Set start | POST | `http://192.168.1.50:8765/api/clock/set-start` | `{"time":"21:46"}` |
| Reset to start | POST | `http://192.168.1.50:8765/api/clock/reset` | `{}` |
| +5 minutes | POST | `http://192.168.1.50:8765/api/clock/add-minutes` | `{"minutes":5}` |
| +10 minutes | POST | `http://192.168.1.50:8765/api/clock/add-minutes` | `{"minutes":10}` |
| +15 minutes | POST | `http://192.168.1.50:8765/api/clock/add-minutes` | `{"minutes":15}` |
| +20 minutes | POST | `http://192.168.1.50:8765/api/clock/add-minutes` | `{"minutes":20}` |
| +25 minutes | POST | `http://192.168.1.50:8765/api/clock/add-minutes` | `{"minutes":25}` |
| +30 minutes | POST | `http://192.168.1.50:8765/api/clock/add-minutes` | `{"minutes":30}` |
| +35 minutes | POST | `http://192.168.1.50:8765/api/clock/add-minutes` | `{"minutes":35}` |
| +40 minutes | POST | `http://192.168.1.50:8765/api/clock/add-minutes` | `{"minutes":40}` |
| +45 minutes | POST | `http://192.168.1.50:8765/api/clock/add-minutes` | `{"minutes":45}` |
| +50 minutes | POST | `http://192.168.1.50:8765/api/clock/add-minutes` | `{"minutes":50}` |
| +55 minutes | POST | `http://192.168.1.50:8765/api/clock/add-minutes` | `{"minutes":55}` |
| +1 hour | POST | `http://192.168.1.50:8765/api/clock/add-hours` | `{"hours":1}` |
| +2 hours | POST | `http://192.168.1.50:8765/api/clock/add-hours` | `{"hours":2}` |

Minute and hour values must be JSON integers, not strings. Only the values in the table are accepted.

## Copy-paste curl examples

These examples use a POSIX shell. Set `BASE` to the controller's address first. In Windows PowerShell, use `curl.exe` rather than the `curl` alias and replace `$BASE` in the URLs with the full address.

```sh
BASE=http://192.168.1.50:8765

curl "$BASE/api/clock"
curl "$BASE/api/status"
curl -X POST "$BASE/api/clock/set-start" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"time":"21:46"}'
curl -X POST "$BASE/api/clock/reset" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{}'
curl -X POST "$BASE/api/clock/add-minutes" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"minutes":5}'
curl -X POST "$BASE/api/clock/add-minutes" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"minutes":10}'
curl -X POST "$BASE/api/clock/add-minutes" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"minutes":15}'
curl -X POST "$BASE/api/clock/add-minutes" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"minutes":20}'
curl -X POST "$BASE/api/clock/add-minutes" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"minutes":25}'
curl -X POST "$BASE/api/clock/add-minutes" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"minutes":30}'
curl -X POST "$BASE/api/clock/add-minutes" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"minutes":35}'
curl -X POST "$BASE/api/clock/add-minutes" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"minutes":40}'
curl -X POST "$BASE/api/clock/add-minutes" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"minutes":45}'
curl -X POST "$BASE/api/clock/add-minutes" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"minutes":50}'
curl -X POST "$BASE/api/clock/add-minutes" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"minutes":55}'
curl -X POST "$BASE/api/clock/add-hours" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"hours":1}'
curl -X POST "$BASE/api/clock/add-hours" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"hours":2}'
```

To connect the app to the Wi-Fi firmware, substitute the ESP32's IP or hostname and its TCP port:

```sh
curl -X POST "$BASE/api/connect" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"transport":"network","host":"192.168.1.111","network_port":23040}'
```

A new ESP32 TCP connection closes its previous client. The app does not reconnect automatically. Opening a serial port can reset the ESP32 and home the drums.

## Clock behavior

Times use 24-hour `HH:MM` format. Set start changes the runtime start and current time for this session; it does not save a new default. Reset displays that runtime start. Minute and hour actions add exact amounts with no rounding and wrap across midnight: `21:46` plus 5 minutes becomes `21:51`.

The saved default prefills the time entry and initializes runtime state when the app restarts. To change it without moving the display:

```sh
curl -X POST "$BASE/api/settings" -H 'Content-Type: application/json' -H 'X-Splitflap-Request: 1' -d '{"default_prop_clock_time":"22:00"}'
```

`GET /api/clock` returns `start_time` and `current_time`. Clock POST responses also return an `operation` ID. The response means a target was accepted/queued, not that the physical movement completed. `GET /api/status` includes operation status and device state; an acknowledgement confirms receipt, not execution. The clock requires at least five configured drums.

Invalid values or an unready device return HTTP 400 with a JSON `error`. HTTP 403 usually means the URL's host is not allowed, the required POST header/content type is missing, or a browser origin is not allowed.