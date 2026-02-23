# Duino Coin Miner — Home Assistant Addon

Mine [Duino-Coin (DUCO)](https://duinocoin.com) directly on your Home Assistant server as a background addon.

Based on [MineCryptoOnWifiRouter](https://github.com/BastelPichi/MineCryptoOnWifiRouter) by BastelPichi.

---

## Supported architectures

| Architecture | Hardware |
| --- | --- |
| `aarch64` | Raspberry Pi 4 (64-bit), most modern SBCs |
| `armv7` | Raspberry Pi 3/4 (32-bit) |
| `armhf` | Raspberry Pi 2 |
| `amd64` | x86-64 servers and VMs |

> The C-accelerated hasher (`libducohasher`) is downloaded automatically at first start for all supported Linux architectures. Without it the miner falls back to pure-Python SHA1, which is significantly slower.

---

## Prerequisites

1. A [Duino-Coin account](https://duinocoin.com) — register at the website or via the Telegram bot `@DuinoCoinBot`.
2. Your **mining key** — retrieve it from your Duino-Coin wallet dashboard or via `@DuinoCoinBot` → `/key`.

---

## Installation (Home Assistant)

1. Add this repository to your HA addon store:

   [![Add repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgfoiani%2Fhassio-addons%2F)

2. Find **"Duino coin miner"** in the addon store and click **Install**.
3. Configure the addon (see section below).
4. Click **Start** and check the **Log** tab for output.

---

## Configuration

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `username` | string | `username` | Your Duino-Coin account name |
| `mining_key` | string | `None` | Your mining key. Use `None` if you have not set one |
| `efficiency` | string | `100` | CPU usage level. `100` = full speed; lower values add sleep between shares (see table below) |
| `threads_count` | string | `1` | Number of parallel mining processes. See note below |

### Efficiency levels

| Value | Sleep per share | Use case |
| --- | --- | --- |
| `100` | none (maximum speed) | Dedicated mining machine |
| `90–99` | 5 ms | Light throttle |
| `70–89` | 100 ms | Background use alongside other addons |
| `50–69` | 800 ms | Low-priority background |
| `30–49` | 1.8 s | Minimal CPU impact |
| `1–29` | 3 s | Barely-there mining |

### Threads

Each thread opens a separate connection to the DUCO server and mines independently. Good starting points:

- Raspberry Pi 4 (4 cores): `3–4`
- Raspberry Pi 3 (4 cores): `2–3`
- Raspberry Pi 2 (4 cores): `1–2`

Adding more threads than CPU cores does not increase hash rate and can cause throttling by the server.

---

## Local development

Use this flow to build and test the addon on your machine with Docker, without needing a full HA environment.

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your real values:

```bash
LOCAL_DEPLOY=true        # tells run.sh to skip bashio and use env vars directly
USERNAME=yourname        # your Duino-Coin username
MINING_KEY=yourkey       # your mining key (or leave as "None")
EFFICIENCY=100           # 100 = maximum speed
THREADS_COUNT=2          # number of parallel mining processes
```

### 2. Build and run

```bash
./deploy_local.sh
```

This script:

- Builds the Docker image for `linux/amd64`
- Removes any existing `duino-miner` container
- Starts a new container with `--env-file .env`

### 3. Watch logs

```bash
docker logs -f duino-miner
```

Expected output when working correctly:

```text
Hassio Duco-Miner.
processor: x86_64
Downloading fasthash
Fasthash downloaded: libducohashLinux.so
Fasthash available
12:34:56: Running Thread 1
12:34:56: Searching for fastest connection to the server
12:34:57: Fastest connection found
12:34:57: Server Version: 4.2
```

> **macOS note:** the pre-built `libducohasher` binary is not available for macOS. The miner will fall back to pure-Python hashing automatically — hash rate will be lower but otherwise fully functional.

### 4. Stop / restart

```bash
docker stop duino-miner    # stop
./deploy_local.sh          # rebuild and restart
```

### 5. Remove the container and image

```bash
docker rm -f duino-miner
docker rmi duino-miner:latest
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
