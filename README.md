# Hassio-addons

------------------

## Add to Home Assistant

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fgfoiani%2Fhassio-addons%2F)

## Manual installation

Copy this link and paste in supervisor

```bash
https://github.com/gfoiani/hassio-addons
```

------------------

## Addons

* Duino coin miner

## Local build

docker build --platform=linux/amd64 --build-arg BUILD_FROM=python:3.12 -t duino-miner:latest

## Local run

docker run -d duino-miner --env .env --restart=no
