
# Duino coin miner Home Assistant addon

_____

## Based on [MineCryptoOnWifiRouter](https://github.com/BastelPichi/MineCryptoOnWifiRouter)

- Duino single-thread coin miner runs in docker as a HASSIO addon
- Supported architectures:
  - amd64
  - armv7
  - aarch64

## Installation

- Add a repository via MY button [![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgfoiani%2Fhassio-addons%2F)
- Install this add-on.
- Configure this add-on
- Start the addon and check the logs if any errors
- Enjoy mining!

## Configuration

- Set the desidered threads number with the option `threads_count`. Default is 1.
- Enter your `username` and `mining_key` in the appropriate fields.
- If you do not have a mining key, specify `None` in `mining_key` column
