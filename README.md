# Home Assistant Add-ons Collection

A collection of custom Home Assistant add-ons for automation, trading, and mining applications.

---

## 🚀 Quick Start

### Add Repository to Home Assistant

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgfoiani%2Fhassio-addons%2F)

### Manual Installation

Copy this URL in Home Assistant Supervisor → Add-on Store → Repositories:

```text
https://github.com/gfoiani/hassio-addons
```

---

## 📦 Available Add-ons

### 🤖 Trading Bots

#### **Crypto Trading Bot (Binance)**

- Automated trading on Binance
- Multi-strategy support
- Real-time risk management
- Telegram notifications
- Docker support: `aarch64`, `amd64`

#### **Day Trading Bot**

- Day trading on Italian exchanges (DirectaBank, XTB)
- Position management
- Trade database logging
- Risk management
- Docker support: `aarch64`, `amd64`

### 💰 Betting

#### **Bet Sniper Bot**

- Automated betting analysis
- Multi-broker support
- Risk and odds management
- Telegram notifications
- Docker support: `aarch64`, `amd64`

### ⛏️ Mining

#### **Duino Coin Miner**

- CPU mining for Duino Coin
- Optimized for various architectures
- Docker support: `aarch64`, `amd64`, `armv7`, `armhf`

### 💬 Utilities

#### **Telegram Bot**

- General-purpose Telegram bot interface
- Message routing and webhooks

---

## 🏗️ Development

### Repository Structure

```text
.
├── bet_sniper_bot_hassio_addon/      # Betting automation bot
├── crypto_trading_bot_hassio_addon/  # Binance trading bot
├── trading_bot_hassio_addon/         # Day trading bot
├── duino_miner_hassio_addon/         # Duino Coin miner
├── telegram_bot/                     # Telegram interface
└── .github/workflows/                # CI/CD pipelines
```

### Local Development

#### Build an add-on locally

```bash
# Build Duino Miner for amd64
docker build --platform=linux/amd64 \
  --build-arg BUILD_FROM=python:3.12 \
  -t duino-miner:latest \
  duino_miner_hassio_addon/
```

#### Run an add-on locally

**Using deployment scripts** (Recommended)

Each add-on includes a `deploy_local.sh` script for easy local deployment:

```bash
cd duino_miner_hassio_addon/
./deploy_local.sh
```

**Manual Docker run**

```bash
# Run with environment file
docker run -d \
  --name duino-miner \
  --env-file .env \
  --restart=no \
  duino-miner:latest
```

### Automated Builds

This repository uses GitHub Actions to automatically build and push Docker images to GitHub Container Registry (GHCR):

- **Trigger**: Automatic on push to `main` (path-filtered per add-on)
- **Manual trigger**: Workflow dispatch available in Actions tab
- **Architectures**: Automatically built for supported platforms
- **Registry**: `ghcr.io/gfoiani/*`

---

## 🔧 Configuration

Each add-on includes:

- `config.yaml` - Home Assistant configuration schema
- `build.yaml` - Docker build configuration
- `requirements.txt` - Python dependencies
- `README.md` - Specific documentation

See individual add-on directories for detailed configuration options.

---

## 📝 Requirements

- Home Assistant OS or Supervised installation
- Docker support (for local development)
- Python 3.12+ (for local development)

---

## 📄 License

Each add-on may have its own license. Check individual add-on directories.

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Create a feature branch
2. Make your changes
3. Submit a pull request

---

## 📧 Support

For issues, questions, or suggestions, please open a GitHub issue.
