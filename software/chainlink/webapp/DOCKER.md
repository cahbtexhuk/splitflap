# Docker deployment

Build the image locally, transfer it as a file, and load it on the Linux host. No Docker Hub account or image registry is required. Building needs internet access for the Python base image and packages; the target can load and run the saved image without a registry.

## 1. Check the target architecture

On the Linux host, run:

```sh
uname -m
```

| Result | Build platform |
| --- | --- |
| `x86_64` | `linux/amd64` |
| `aarch64` | `linux/arm64` |
| `armv7l` | `linux/arm/v7` |

Build for the target's architecture, not necessarily the machine running the build. Cross-architecture builds require a Buildx builder with appropriate emulation support; see `docker buildx ls`. If unavailable, build on a machine matching the target architecture.

## 2. Build and save the image

From the repository root on the build machine, replace `linux/amd64` with the target platform:

```sh
docker buildx build --platform linux/amd64 --load -t splitflap-webapp:local -f software/chainlink/webapp/Dockerfile .
docker image save -o splitflap-webapp.tar splitflap-webapp:local
```

These commands also work in PowerShell. The Dockerfile-specific ignore file restricts the build context to application files and generated protobuf modules; it excludes the private firmware Wi-Fi configuration. The image tag is local and is not pushed anywhere.

## 3. Transfer and load

Copy `splitflap-webapp.tar` and [compose.yaml](compose.yaml) to the Linux host with a USB drive, `scp`, or another file-transfer method. For example, on a machine with SSH access, substitute the Linux username and host:

```sh
ssh USER@LINUX_HOST 'mkdir -p ~/splitflap-webapp'
scp splitflap-webapp.tar software/chainlink/webapp/compose.yaml USER@LINUX_HOST:~/splitflap-webapp/
```

On the Linux host:

```sh
cd ~/splitflap-webapp
docker image load -i splitflap-webapp.tar
docker image ls splitflap-webapp
```

The host needs Docker Engine and, for the Compose option, the Docker Compose plugin. The examples below are alternatives: stop one container before starting the other because both publish port 8765.

## 4. Run with Docker

Set `HOST_IP` to the Linux host's LAN IP address, not the ESP32's address. Docker must be able to bind that address. The `--allowed-host` value must match the IP address or hostname in the browser or REST client's URL.

```sh
HOST_IP=192.168.1.50
docker run -d --name splitflap-webapp --restart unless-stopped \
  -p "${HOST_IP}:8765:8765" \
  -v splitflap-settings:/data \
  splitflap-webapp:local \
  --host 0.0.0.0 --port 8765 --allowed-host "$HOST_IP"
```

Open `http://192.168.1.50:8765`, replacing the example address with `HOST_IP`. To also access the app using a DNS name, add another `--allowed-host YOUR_HOSTNAME` after the existing one. For local-only access, use `HOST_IP=127.0.0.1`; other machines will not be able to connect.

```sh
docker logs -f splitflap-webapp
docker stop splitflap-webapp
docker start splitflap-webapp
```

To replace the container after loading a new image, remove the stopped container and run the `docker run` command again. The named `splitflap-settings` volume preserves settings; do not remove it if you want to keep them.

```sh
docker stop splitflap-webapp
docker rm splitflap-webapp
```

## 5. Run with Docker Compose

From the directory containing the transferred `compose.yaml`, set the Linux host's LAN IP. The file defaults to binding `127.0.0.1` if `SPLITFLAP_BIND_IP` is unset, and requires `SPLITFLAP_ALLOWED_HOST`.

```sh
export SPLITFLAP_BIND_IP=192.168.1.50
export SPLITFLAP_ALLOWED_HOST=192.168.1.50
docker compose config
docker compose up -d --no-build
```

Open `http://192.168.1.50:8765` with your actual host IP. Edit the Compose `command` list to add another `--allowed-host` and hostname if clients use multiple addresses. The configuration uses `pull_policy: never`, so it runs only the locally loaded image.

```sh
docker compose logs -f
docker compose down
```

`docker compose down` keeps the named settings volume; do not add `-v` if you want to retain settings. To update, load the new archive and run `docker compose up -d --no-build --force-recreate` with the same environment variables.

## Device connections

Connect to the ESP32 from the app's Connection page using its IP or hostname and TCP port `23040`. If mDNS names do not resolve from the container, use the ESP32's IP address. Connections are manual; the app does not automatically reconnect. A new ESP32 TCP client displaces the previous one.

For Linux USB serial, grant the non-root container access to the actual device and its numeric group. For example, add these options to `docker run` before the image name:

```sh
--device=/dev/ttyUSB0:/dev/ttyUSB0 --group-add "$(stat -c '%g' /dev/ttyUSB0)"
```

Use the real device path; it may be `/dev/ttyACM0` instead. For Compose, add the following under the `splitflap` service and export the group ID before `docker compose up`:

```yaml
devices:
  - /dev/ttyUSB0:/dev/ttyUSB0
group_add:
  - "${SPLITFLAP_SERIAL_GID}"
```

```sh
export SPLITFLAP_SERIAL_GID="$(stat -c '%g' /dev/ttyUSB0)"
```

Device mapping and permissions depend on the Linux host and its USB driver. Opening a serial port can reset the ESP32 and home the drums. The `chainlink_wifi` firmware uses serial only for diagnostics; serial control requires the `chainlink` firmware target.

## Security and clock API

The app and ESP32 TCP control have no login or TLS. Anyone who can reach them can operate the display; the app can also connect to addresses on its host's network. Bind only to a trusted LAN address and restrict access with network firewall rules; do not expose or forward these ports to the internet. Docker-published ports can bypass some host firewall rules, so verify your Docker and firewall configuration.

For copy-paste clock requests, see [CLOCK_API.md](CLOCK_API.md). Requests go to the Python app's HTTP port `8765`, not the ESP32's TCP port `23040`.

## Optional Compose overrides

Set `SPLITFLAP_HTTP_PORT` to change the published host port from `8765`; include that port in the URL. Set `SPLITFLAP_SETTINGS_VOLUME` to use a different named settings volume instead of `splitflap-settings`. Export these variables before running Compose, along with `SPLITFLAP_BIND_IP` and `SPLITFLAP_ALLOWED_HOST`.
