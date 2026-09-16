"""The OHLCV candle data model and lightweight validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

_EPSILON = 1e-9


@dataclass(frozen=True)
class Candle:
    """A single OHLCV candle.

    Attributes:
        ts: Opening timestamp of the candle in epoch milliseconds (UTC).
        open: Opening price.
        high: Highest traded price during the candle.
        low: Lowest traded price during the candle.
        close: Closing price.
        volume: Traded base-asset volume during the candle.

    Instances are immutable so they can be freely reused as cache keys or
    shared between threads for read-only indicator math.
    """

    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def series(candles: Sequence[Candle]) -> List[float]:
    """Return the conventional price series (closes) of a candle sequence.

    Args:
        candles: A sequence of candles, usually ordered by timestamp.

    Returns:
        A list of closing prices, one per candle, in input order.
    """

    return [candle.close for candle in candles]


def candle_issues(candle: Candle, *, check_volume: bool = True) -> List[str]:
    """Return a list of validation problems for a single candle.

    Checks the OHLCV invariants ``high >= max(open, close)`` and
    ``low <= min(open, close)``. Volume is never allowed to be negative; when
    ``check_volume`` is True a zero volume is also reported.

    Args:
        candle: The candle to validate.
        check_volume: Whether to treat a zero volume as an issue.

    Returns:
        A list of human-readable problem descriptions. Empty when the candle
        is consistent.
    """

    issues: List[str] = []
    upper = max(candle.open, candle.close)
    lower = min(candle.open, candle.close)
    if candle.high + _EPSILON < upper:
        issues.append(
            f"high {candle.high} is below max(open, close) {upper}"
        )
    if candle.low - _EPSILON > lower:
        issues.append(
            f"low {candle.low} is above min(open, close) {lower}"
        )
    if candle.volume is not None:
        if candle.volume < 0:
            issues.append(f"volume {candle.volume} is negative")
        elif check_volume and candle.volume == 0:
            issues.append("volume is zero")
    return issues


def validate(
    candles: Sequence[Candle],
    *,
    check_volume: bool = True,
    raise_on_error: bool = False,
) -> List[str]:
    """Validate a sequence of candles and collect all observed issues.

    Args:
        candles: The candles to validate.
        check_volume: Whether to report zero volumes as issues.
        raise_on_error: When True, raise ``ValueError`` on the first issue
            instead of returning the collected messages.

    Returns:
        A list of problem messages with the offending index and timestamp
        prefixed, empty when everything is consistent. When ``raise_on_error``
        is set a ``ValueError`` is raised instead and nothing is returned.
    """

    messages: List[str] = []
    for index, candle in enumerate(candles):
        for issue in candle_issues(candle, check_volume=check_volume):
            messages.append(
                f"candle #{index} (ts={candle.ts}): {issue}"
            )
    if raise_on_error and messages:
        raise ValueError(messages[0])
    return messages