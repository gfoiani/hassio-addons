# Changelog

## v1.2.0

- Feature: Localization support. Configuration panel now displays in English (en) and Italian (it) with detailed descriptions for each parameter. Helps users understand settings like odds thresholds, betting windows, risk management, and Telegram integration.

## v1.1.0

- Feature: Snipe window — bets are placed only when kick-off is within a
  configurable time range (`bet_window_hours` before KO and at least
  `min_time_to_ko_minutes` away). This lets the market mature and official
  line-ups be published before the bot acts. Default: 30 min – 2 h before KO.

## v1.0.0

- Feature: Initial release. Automatic football 1X2 BACK betting on Betfair.
  Supports Serie A, Premier League, La Liga, and Bundesliga (configurable).
  Risk management via fixed stake per bet, daily spend cap, and reserve
  percentage. Paper-trading mode for safe testing. SQLite bet history with
  Telegram `/status` and `/stats` commands.
