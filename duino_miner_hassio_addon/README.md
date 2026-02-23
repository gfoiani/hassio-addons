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
| `log_level` | string | `minimal` | Controls share logging verbosity: `minimal` logs only rejections, `verbose` logs every accepted share |

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

### Log level

| Value | What is logged |
| --- | --- |
| `minimal` *(default)* | Connection events, rejected shares (with rejection reason if provided), errors |
| `verbose` | Everything above, plus every accepted share with hashrate and difficulty |

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
LOG_LEVEL=verbose        # verbose = log all accepted/rejected shares
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

Expected output with `LOG_LEVEL=verbose`:

```text
Hassio Duco-Miner.
processor: x86_64
Downloading fasthash
Fasthash downloaded: libducohashLinux.so
Fasthash available
12:34:56: Running Thread 1
12:34:56: Searching for fastest connection to the server
12:34:56: Running Thread 2
12:34:57: Fastest connection found
12:34:57: Server Version: 4.3
12:34:58: Thread 1 | Accepted | result=4321 | 12kH/s | diff=5
12:34:58: Thread 2 | Accepted | result=8765 | 11kH/s | diff=5
```

With `LOG_LEVEL=minimal` only rejections appear:

```text
12:34:58: Thread 1 | Rejected | result=4321 | 12kH/s | diff=5 | reason=Too low difficulty
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

## Updating libducohasher

The `libducohasher` C extension is downloaded automatically from the Duino-Coin server on first container start. Since the filename never changes (no version suffix), a cached file is reused on subsequent starts even if a newer binary is available on the server.

To force a re-download of the latest binary:

```bash
# Local Docker
docker rm -f duino-miner
docker volume prune -f
./deploy_local.sh
```

On Home Assistant: **Stop addon → Uninstall → Reinstall**.

The library is written in Rust. To compile it yourself for a custom architecture, see the [official guide](https://github.com/revoxhere/duino-coin/wiki/How-to-compile-fasthash-accelerations). The source is also available at `https://server.duinocoin.com/fasthash/libducohash.tar.gz`.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
