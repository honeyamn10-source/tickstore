# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Nothing yet.

## [0.1.0] - 2026-01-01

### Added

- `Candle` frozen dataclass, `series()` and candle validation helpers.
- `BaseProvider` ABC with an injectable `transport` hook; default stdlib
  `urllib` transport.
- `BinanceProvider` for public spot klines (`/api/v3/klines`) with typed
  12-field row decoding and `startTime`/`endTime` support.
- `YahooProvider` for `v8/finance/chart` with interval/range mapping and null
  row dropping.
- `Store` SQLite cache with `INSERT OR REPLACE` upserts, time-range loads,
  incremental `refresh()` with pagination, and CSV import/export.
- Fixed-bucket `resample()` across 1m through 1wk with OHLCV aggregation.
- O(n) indicators: `sma`, `ema`, `rsi`, `atr`, `vwap`, `bollinger_bands`.
- `tickstore` CLI with `fetch`, `status` and `indicators` subcommands.
- Fully offline test suite (104 tests) with canned Binance/Yahoo fixtures and
  a sample 1m CSV.
- `examples/quantlab.py` offline pipeline demo.