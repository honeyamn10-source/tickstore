"""Resampling helpers.

Candles are aggregated into larger fixed buckets entirely from their
timestamps: a bucket is ``(ts // bucket_ms) * bucket_ms``. This means there is
no daylight-savings handling and weekly buckets are fixed seven-day windows
measured from the Unix epoch rather than ISO calendar weeks.
"""

from __future__ import annotations

from typing import List, Sequence

from .candle import Candle

BUCKETS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
    "1wk": 604_800_000,
}


class ResampleError(ValueError):
    """Raised for invalid resampling requests or inconsistent input."""


def resample(candles: Sequence[Candle], base: str = "1m", target: str = "1h") -> List[Candle]:
    """Aggregate candles into a larger fixed interval bucket.

    Open is the first candle's open, high the maximum, low the minimum, close
    the last candle's close and volume the sum. Each output candle's timestamp
    is the start of its target bucket.

    Args:
        candles: Candles ordered by ascending timestamp, on a fixed ``base``
            grid.
        base: Interval of the input candles (for example ``1m``).
        target: Interval to aggregate into (for example ``1h``).

    Returns:
        Resampled candles, ordered by ascending timestamp.

    Raises:
        ResampleError: If either interval is unknown, the target is not a
            whole multiple of the base, or the input is not sorted ascending.
    """

    if base not in BUCKETS:
        raise ResampleError(f"unknown base interval {base!r}")
    if target not in BUCKETS:
        raise ResampleError(f"unknown target interval {target!r}")
    base_ms = BUCKETS[base]
    target_ms = BUCKETS[target]
    if target_ms % base_ms != 0:
        raise ResampleError(
            f"cannot resample {base} into {target}: target is not a "
            "whole multiple of base"
        )
    if not candles:
        return []
    previous_ts = candles[0].ts
    for candle in candles[1:]:
        if candle.ts < previous_ts:
            raise ResampleError("candles must be sorted by ascending timestamp")
        previous_ts = candle.ts

    aggregated: List[Candle] = []
    bucket_open_ts: int | None = None
    bucket_start = 0
    bucket_open = 0.0
    bucket_high = 0.0
    bucket_low = 0.0
    bucket_close = 0.0
    bucket_volume = 0.0

    for candle in candles:
        bucket = (candle.ts // target_ms) * target_ms
        if bucket != bucket_open_ts:
            if bucket_open_ts is not None:
                aggregated.append(
                    Candle(
                        ts=bucket_start,
                        open=bucket_open,
                        high=bucket_high,
                        low=bucket_low,
                        close=bucket_close,
                        volume=bucket_volume,
                    )
                )
            bucket_open_ts = bucket
            bucket_start = bucket
            bucket_open = candle.open
            bucket_high = candle.high
            bucket_low = candle.low
            bucket_close = candle.close
            bucket_volume = candle.volume
        else:
            bucket_high = max(bucket_high, candle.high)
            bucket_low = min(bucket_low, candle.low)
            bucket_close = candle.close
            bucket_volume = bucket_volume + candle.volume
    if bucket_open_ts is not None:
        aggregated.append(
            Candle(
                ts=bucket_start,
                open=bucket_open,
                high=bucket_high,
                low=bucket_low,
                close=bucket_close,
                volume=bucket_volume,
            )
        )
    return aggregated