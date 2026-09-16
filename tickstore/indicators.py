"""Pure, O(n) technical indicators.

Every function is deterministic, dependency free, and returns a list aligned
index-for-index with its input. Warmup periods are ``None`` so charts and
callers never have to manage window offsets themselves.

Unless stated otherwise all values are floats. Inputs may be any sequence of
floats (prices) or, for the candle-based indicators, candles.
"""

from __future__ import annotations

import statistics
from typing import List, Optional, Sequence, Tuple

from .candle import Candle


def sma(closes: Sequence[float], n: int) -> List[Optional[float]]:
    """Simple moving average with a period of ``n``.

    The first ``n - 1`` outputs are ``None``.

    Args:
        closes: Closing price series.
        n: Window length, must be positive.

    Returns:
        Moving averages aligned with the input.

    Raises:
        ValueError: If ``n`` is not positive.
    """

    _require_positive(n)
    values = [float(value) for value in closes]
    result: List[Optional[float]] = [None] * len(values)
    if len(values) < n:
        return result
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= n:
            running -= values[index - n]
        if index >= n - 1:
            result[index] = running / n
    return result


def ema(closes: Sequence[float], n: int) -> List[Optional[float]]:
    """Exponential moving average with a period of ``n``.

    Smoothing is ``2 / (n + 1)``. The first ``n - 1`` outputs are ``None``;
    the running value is seeded from the close immediately before the first
    output and then smoothed forward.

    Args:
        closes: Closing price series.
        n: Period (must be at least 1).

    Returns:
        Exponential moving averages aligned with the input.

    Raises:
        ValueError: If ``n`` is not positive.
    """

    _require_positive(n)
    values = [float(value) for value in closes]
    result: List[Optional[float]] = [None] * len(values)
    if len(values) < n:
        return result
    if n == 1:
        return values
    smoothing = 2.0 / (n + 1.0)
    previous = values[n - 2]
    for index in range(n - 1, len(values)):
        previous = smoothing * values[index] + (1.0 - smoothing) * previous
        result[index] = previous
    return result


def rsi(closes: Sequence[float], n: int = 14) -> List[Optional[float]]:
    """Relative Strength Index with Wilder smoothing.

    The first ``n`` outputs are ``None``. A strictly rising series tends to
    100, a strictly falling series to 0, and a flat series sits at 50.

    Args:
        closes: Closing price series.
        n: Lookback period.

    Returns:
        RSI values in ``[0, 100]`` aligned with the input.

    Raises:
        ValueError: If ``n`` is not positive.
    """

    _require_positive(n)
    values = [float(value) for value in closes]
    result: List[Optional[float]] = [None] * len(values)
    if len(values) <= n:
        return result

    gains = []
    losses = []
    for index in range(1, len(values)):
        change = values[index] - values[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    average_gain = sum(gains[:n]) / n
    average_loss = sum(losses[:n]) / n
    result[n] = _rsi_from_averages(average_gain, average_loss)
    for index in range(n + 1, len(values)):
        gain = gains[index - 1]
        loss = losses[index - 1]
        average_gain = (average_gain * (n - 1) + gain) / n
        average_loss = (average_loss * (n - 1) + loss) / n
        result[index] = _rsi_from_averages(average_gain, average_loss)
    return result


def atr(candles: Sequence[Candle], n: int = 14) -> List[Optional[float]]:
    """Average True Range with Wilder smoothing.

    True range is ``max(high - low, |high - prev_close|, |low - prev_close|)``
    and the first output appears at index ``n``.

    Args:
        candles: Candle series ordered by timestamp.
        n: Period.

    Returns:
        ATR values aligned with the input candles.

    Raises:
        ValueError: If ``n`` is not positive.
    """

    _require_positive(n)
    result: List[Optional[float]] = [None] * len(candles)
    if len(candles) <= n:
        return result
    previous_close = candles[0].close
    ranges = []
    for index in range(1, n + 1):
        ranges.append(_true_range(candles[index], previous_close))
        previous_close = candles[index].close
    value = sum(ranges) / n
    result[n] = value
    for index in range(n + 1, len(candles)):
        span = _true_range(candles[index], previous_close)
        value = (value * (n - 1) + span) / n
        result[index] = value
        previous_close = candles[index].close
    return result


def vwap(candles: Sequence[Candle]) -> List[Optional[float]]:
    """Cumulative volume-weighted average price anchored at the series start.

    A candle with zero cumulative volume (no volume traded yet) yields
    ``None``.

    Args:
        candles: Candle series in chronological order.

    Returns:
        VWAP values aligned with the input candles.
    """

    result: List[Optional[float]] = []
    price_volume = 0.0
    volume = 0.0
    for candle in candles:
        typical = (candle.high + candle.low + candle.close) / 3.0
        price_volume += typical * candle.volume
        volume += candle.volume
        result.append(price_volume / volume if volume > 0 else None)
    return result


def bollinger_bands(
    closes: Sequence[float], n: int = 20
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """Bollinger Bands computed with a population standard deviation.

    Args:
        closes: Closing price series.
        n: Window length.

    Returns:
        A ``(middle, upper, lower)`` tuple of aligned lists. Middle is the
        simple moving average, upper and lower sit two standard deviations
        away.

    Raises:
        ValueError: If ``n`` is not positive.
    """

    _require_positive(n)
    values = [float(value) for value in closes]
    middle = sma(values, n)
    upper: List[Optional[float]] = [None] * len(values)
    lower: List[Optional[float]] = [None] * len(values)
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= n:
            running -= values[index - n]
        if index >= n - 1:
            window = values[index - n + 1 : index + 1]
            deviation = statistics.pstdev(window)
            baseline = middle[index]
            upper[index] = baseline + 2.0 * deviation
            lower[index] = baseline - 2.0 * deviation
    return middle, upper, lower


def _rsi_from_averages(average_gain: float, average_loss: float) -> float:
    """Convert Wilder average gain/loss into an RSI value.

    Args:
        average_gain: Wilder-smoothed average gain.
        average_loss: Wilder-smoothed average loss.

    Returns:
        RSI in ``[0, 100]``. A flat series maps to 50, a strictly rising
        series to 100 and a strictly falling one to 0.
    """

    if average_loss == 0.0:
        return 100.0 if average_gain > 0.0 else 50.0
    if average_gain == 0.0:
        return 0.0
    relative_strength = average_gain / average_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def _true_range(candle: Candle, previous_close: float) -> float:
    """Compute a single true range value.

    Args:
        candle: The current candle.
        previous_close: Closing price of the previous candle.

    Returns:
        The true range, always non-negative.
    """

    return max(
        candle.high - candle.low,
        abs(candle.high - previous_close),
        abs(candle.low - previous_close),
    )


def _require_positive(n: int) -> None:
    """Validate a period argument.

    Args:
        n: The period to validate.

    Raises:
        ValueError: If the period is not positive.
    """

    if not isinstance(n, int) or n < 1:
        raise ValueError(f"period must be a positive int, got {n!r}")