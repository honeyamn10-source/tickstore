"""Command line interface for tickstore.

Three subcommands are provided:

* ``tickstore fetch`` -- pull candles from a provider and either print them or
  persist them to a local store.
* ``tickstore status`` -- summarize coverage for a stored symbol.
* ``tickstore indicators`` -- print the latest indicator values for a stored
  series.

Everything uses only ``argparse`` plus the rest of tickstore.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sqlite3
import sys
from typing import List, Optional

from .candle import Candle, series
from .indicators import atr, bollinger_bands, ema, rsi, sma, vwap
from .providers import BaseProvider, BinanceProvider, ProviderError, YahooProvider
from .resample import BUCKETS
from .store import Store

DEFAULT_DB = "tickstore.db"


def build_parser() -> argparse.ArgumentParser:
    """Build the root argument parser with all subcommands.

    Returns:
        A fully configured ``ArgumentParser``.
    """

    parser = argparse.ArgumentParser(
        prog="tickstore",
        description="Dependency-free OHLCV market data for self-hosted trading "
        "research.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser(
        "fetch",
        help="fetch candles from a market data provider",
        description="Fetch candles from a market data provider and either "
        "print them as a table or store them in a local database.",
    )
    fetch.add_argument("symbol", help="market symbol, e.g. BTCUSDT or MSFT")
    fetch.add_argument(
        "--exchange",
        choices=("binance", "yahoo"),
        default="binance",
        help="provider to query (default: binance)",
    )
    fetch.add_argument(
        "--interval",
        default="1h",
        help="candle interval: 1m 5m 15m 30m 1h 4h 1d 1wk (default: 1h)",
    )
    fetch.add_argument(
        "--limit",
        type=int,
        default=500,
        help="maximum number of candles (default: 500)",
    )
    fetch.add_argument(
        "--start",
        default=None,
        help="start of the range: ISO-8601 date/datetime or epoch ms",
    )
    fetch.add_argument("--save", action="store_true", help="store into --db")
    fetch.add_argument("--db", default=DEFAULT_DB, help="database path")
    fetch.set_defaults(func=_command_fetch)

    status = subparsers.add_parser(
        "status",
        help="show stored coverage for a symbol",
        description="Show first/last timestamp, row count and gap count for a "
        "stored symbol.",
    )
    status.add_argument("symbol", help="market symbol")
    status.add_argument("--interval", default=None, help="restrict to one interval")
    status.add_argument("--db", default=DEFAULT_DB, help="database path")
    status.set_defaults(func=_command_status)

    indicators = subparsers.add_parser(
        "indicators",
        help="print latest indicator values",
        description="Print the most recent computed indicator values for a "
        "stored series.",
    )
    indicators.add_argument("symbol", help="market symbol")
    indicators.add_argument("--interval", default="1h", help="candle interval")
    indicators.add_argument(
        "--sma",
        type=int,
        action="append",
        default=[],
        help="simple moving average period (repeatable)",
    )
    indicators.add_argument(
        "--ema",
        type=int,
        action="append",
        default=[],
        help="exponential moving average period (repeatable)",
    )
    indicators.add_argument(
        "--rsi",
        type=int,
        action="append",
        default=[],
        help="RSI period (repeatable)",
    )
    indicators.add_argument(
        "--atr",
        type=int,
        action="append",
        default=[],
        help="ATR period (repeatable)",
    )
    indicators.add_argument(
        "--bands",
        type=int,
        default=20,
        help="Bollinger band period (default: 20)",
    )
    indicators.add_argument("--db", default=DEFAULT_DB, help="database path")
    indicators.set_defaults(func=_command_indicators)

    return parser


def main(argv: Optional[List[str]] = None, transport: object = None) -> int:
    """Entry point for the ``tickstore`` console script.

    Args:
        argv: Argument list; defaults to ``sys.argv[1:]``.
        transport: Optional provider transport hook for testing.

    Returns:
        Process exit code. 0 on success, 1 on a handled runtime error.
        Argument parsing errors call ``SystemExit(2)`` via argparse.
    """

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args, transport)
    except (ProviderError, OSError, sqlite3.Error, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _build_provider(exchange: str, transport: object = None) -> BaseProvider:
    """Instantiate the requested provider.

    Args:
        exchange: Provider name.
        transport: Transport hook forwarded to the provider.

    Returns:
        A ready provider instance.

    Raises:
        ValueError: If the exchange name is unknown.
    """

    if exchange == "binance":
        return BinanceProvider(transport) if transport else BinanceProvider()
    if exchange == "yahoo":
        return YahooProvider(transport) if transport else YahooProvider()
    raise ValueError(f"unknown exchange {exchange!r}")


def _command_fetch(args: argparse.Namespace, transport: object = None) -> int:
    """Handle the ``fetch`` subcommand.

    Args:
        args: Parsed namespace.
        transport: Transport hook (testing only).

    Returns:
        Exit code.
    """

    provider = _build_provider(args.exchange, transport)
    candles = provider.fetch(
        args.symbol,
        interval=args.interval,
        limit=args.limit,
        start=args.start,
    )
    if args.save:
        with Store(args.db) as store:
            store.save(candles, args.symbol, args.interval)
        print(f"saved {len(candles)} candles")
    else:
        _print_table(args.symbol, args.interval, candles)
    return 0


def _command_status(args: argparse.Namespace, transport: object = None) -> int:
    """Handle the ``status`` subcommand.

    Args:
        args: Parsed namespace.
        transport: Unused transport hook (testing symmetry).

    Returns:
        Exit code.
    """

    _ = transport
    with Store(args.db) as store:
        intervals = store.intervals(args.symbol)
        if args.interval is not None:
            intervals = [args.interval] if args.interval in intervals else []
    if not intervals:
        print(f"no data for {args.symbol}")
        return 0
    _print_row("{:<8} {:>26} {:>26} {:>8} {:>8}", "interval", "first", "last", "count", "gaps")
    for interval in intervals:
        with Store(args.db) as store:
            candles = store.load(args.symbol, interval)
        if not candles:
            continue
        first = _format_timestamp(candles[0].ts)
        last = _format_timestamp(candles[-1].ts)
        gaps = _count_gaps(candles, interval)
        _print_row("{:<8} {:>26} {:>26} {:>8} {:>8}", interval, first, last, len(candles), gaps)
    return 0


def _command_indicators(args: argparse.Namespace, transport: object = None) -> int:
    """Handle the ``indicators`` subcommand.

    Args:
        args: Parsed namespace.
        transport: Unused transport hook (testing symmetry).

    Returns:
        Exit code.
    """

    _ = transport
    with Store(args.db) as store:
        candles = store.load(args.symbol, args.interval)
    if not candles:
        print(f"no data for {args.symbol} {args.interval}")
        return 1
    closes = series(candles)
    for period in args.sma:
        print(f"sma({period})    = {_format_value(_latest(sma(closes, period)))}")
    for period in args.ema:
        print(f"ema({period})    = {_format_value(_latest(ema(closes, period)))}")
    for period in args.rsi:
        print(f"rsi({period})    = {_format_value(_latest(rsi(closes, period)))}")
    for period in args.atr:
        print(f"atr({period})    = {_format_value(_latest(atr(candles, period)))}")
    middle, upper, lower = bollinger_bands(closes, args.bands)
    print(f"vwap()    = {_format_value(_latest(vwap(candles)))}")
    print(
        f"bands({args.bands}) = "
        f"{_format_value(_latest(middle))}/{_format_value(_latest(upper))}/"
        f"{_format_value(_latest(lower))}"
    )
    return 0


def _latest(values: List[Optional[float]]) -> Optional[float]:
    """Return the last non-None value in a series.

    Args:
        values: Indicator output.

    Returns:
        The final computed value, or ``None`` when the series has none.
    """

    for value in reversed(values):
        if value is not None:
            return value
    return None


def _format_value(value: Optional[float]) -> str:
    """Format an indicator value for display.

    Args:
        value: Value to format.

    Returns:
        Fixed-width decimal string, or ``n/a`` when the value is None.
    """

    return f"{value:.6f}" if value is not None else "n/a"


def _format_timestamp(ts: int) -> str:
    """Format epoch milliseconds as an ISO-8601 UTC string.

    Args:
        ts: Epoch milliseconds.

    Returns:
        ISO-8601 UTC timestamp string.
    """

    return _dt.datetime.fromtimestamp(ts / 1000, tz=_dt.timezone.utc).isoformat()


def _count_gaps(candles: List[Candle], interval: str) -> int:
    """Count missing fixed grid buckets between the first and last candle.

    Args:
        candles: Stored candles for one pair.
        interval: Interval name used to derive the bucket size.

    Returns:
        Number of missing buckets, never negative.
    """

    step = BUCKETS[interval]
    expected = (candles[-1].ts - candles[0].ts) // step + 1
    return max(0, expected - len(candles))


def _print_table(symbol: str, interval: str, candles: List[Candle]) -> None:
    """Print candles as a fixed-width text table.

    Args:
        symbol: Symbol label for the caption.
        interval: Interval label for the caption.
        candles: Candles to render.
    """

    print(f"{symbol} {interval} ({len(candles)} candles)")
    row_format = "{:<16} {:>14} {:>14} {:>14} {:>14} {:>14}"
    _print_row(row_format, "ts", "open", "high", "low", "close", "volume")
    for candle in candles:
        _print_row(
            row_format,
            candle.ts,
            _format_value(candle.open),
            _format_value(candle.high),
            _format_value(candle.low),
            _format_value(candle.close),
            _format_value(candle.volume),
        )


def _print_row(fmt: str, *cells: object) -> None:
    """Print a row using a format string.

    Args:
        fmt: Column format string.
        cells: Cells to render.
    """

    print(fmt.format(*cells))