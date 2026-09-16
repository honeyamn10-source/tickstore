#!/usr/bin/env python3
"""quantlab.py - a fully offline pipeline demo for tickstore.

Runs the whole research workflow against the bundled sample fixture:

    1. Import a raw 1-minute CSV into a local store.
    2. Resample it to hourly, 4-hourly and daily candles.
    3. Export the hourly series back to CSV.
    4. Print an indicator summary (SMA / RSI / ATR / VWAP / Bollinger).

Nothing here touches the network: the input is ``tests/fixtures/sample_1m.csv``
(5 days of synthetic 1m data generated with a fixed seed), so the example
reproduces identical output on any machine.

Run with:

    python examples/quantlab.py
"""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tickstore import Store, resample, series
from tickstore.indicators import atr, bollinger_bands, rsi, sma, vwap

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "sample_1m.csv")
EXPORT = os.path.join(tempfile.gettempdir(), "quantlab_hourly.csv")


def _fmt(value):
    """Format an indicator value for the report.

    Args:
        value: The value to format.

    Returns:
        Fixed-width decimal, or ``n/a``.
    """

    return f"{value:.4f}" if value is not None else "n/a"


def _latest(values):
    """Return the last computed (non-None) value of a series.

    Args:
        values: Indicator output list.

    Returns:
        The final computed value or None.
    """

    return next((v for v in reversed(values) if v is not None), None)


def _table(candles):
    """Render the last few candles as text.

    Args:
        candles: Candles to render.

    Returns:
        A ready-to-print string.
    """

    rows = []
    header = f"{'ts':<16} {'open':>12} {'high':>12} {'low':>12} {'close':>12} {'volume':>12}"
    rows.append(header)
    rows.append("-" * len(header))
    for candle in candles[-5:]:
        rows.append(
            f"{candle.ts:<16} {candle.open:>12.2f} {candle.high:>12.2f} "
            f"{candle.low:>12.2f} {candle.close:>12.2f} {candle.volume:>12.1f}"
        )
    return "\n".join(rows)


def main() -> int:
    """Run the demo pipeline.

    Returns:
        Exit code: 0 on success, 1 when the fixture is unavailable.
    """

    if not os.path.exists(FIXTURE):
        print(f"fixture not found: {FIXTURE}")
        print("run this from the repository checkout: python examples/quantlab.py")
        return 1

    print("=" * 72)
    print("quantlab.py - tickstore offline research pipeline")
    print("=" * 72)

    with Store(":memory:") as store:
        raw = store.load_csv(FIXTURE, "SAMPLE", "1m")
        store.save(raw, "SAMPLE", "1m")

        print("\n[1] ingested fixture")
        print(f"    source : {FIXTURE}")
        print(f"    candles: {len(raw)} x 1m")

        hourly = resample(raw, base="1m", target="1h")
        four_hour = resample(raw, base="1m", target="4h")
        daily = resample(raw, base="1m", target="1d")
        store.save(hourly, "SAMPLE", "1h")

        print("\n[2] resampled")
        print(f"    1h  : {len(hourly)} candles")
        print(f"    4h  : {len(four_hour)} candles")
        print(f"    1d  : {len(daily)} candles")

        print("\n[3] exported hourly series")
        rows = store.export_csv(EXPORT, "SAMPLE", "1h")
        print(f"    csv  : {EXPORT}")
        print(f"    rows : {rows}")

        closes = series(hourly)
        mid, upper, lower = bollinger_bands(closes, 20)

        print("\n[4] indicator summary (latest, hourly series)")
        print(f"    sma(20)     = {_fmt(_latest(sma(closes, 20)))}")
        print(f"    rsi(14)     = {_fmt(_latest(rsi(closes, 14)))}")
        print(f"    atr(14)     = {_fmt(_latest(atr(hourly, 14)))}")
        print(f"    vwap()      = {_fmt(_latest(vwap(hourly)))}")
        print(
            f"    bands(20)   = {_fmt(_latest(mid))} / {_fmt(_latest(upper))} / "
            f"{_fmt(_latest(lower))}"
        )

        print("\n[5] last candles (hourly)")
        print(_table(hourly))

    print("\ndone - the full pipeline ran offline with zero dependencies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())