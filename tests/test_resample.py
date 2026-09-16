"""Tests for candle resampling and bucket geometry."""

import pytest

from tickstore import BUCKETS, Candle, ResampleError, resample

MINUTE = 60_000
HOUR = 3_600_000
DAY = 86_400_000
WEEK = 604_800_000
BASE = 1767225600000


def _candle(ts, open_=1.0, high=2.0, low=0.5, close=1.5, volume=10.0):
    return Candle(ts=ts, open=open_, high=high, low=low, close=close, volume=volume)


def test_1m_to_1h_aggregation():
    candles = [
        _candle(
            BASE + i * MINUTE,
            open_=1.0 + i,
            high=2.0 + i,
            low=0.5 + i,
            close=1.5 + i,
            volume=10.0 + i,
        )
        for i in range(180)
    ]
    result = resample(candles, base="1m", target="1h")
    assert len(result) == 3
    first = result[0]
    assert first.ts == BASE
    assert first.open == pytest.approx(1.0)
    assert first.high == pytest.approx(2.0 + 59)
    assert first.low == pytest.approx(0.5)
    assert first.close == pytest.approx(1.5 + 59)
    assert first.volume == pytest.approx(sum(10.0 + i for i in range(60)))
    third = result[2]
    assert third.ts == BASE + 2 * HOUR
    assert third.open == pytest.approx(121.0)
    assert third.close == pytest.approx(1.5 + 179)


def test_open_high_low_close_volume_semantics():
    candles = [
        _candle(BASE, open_=1.0, high=2.0, low=0.5, close=1.5, volume=10.0),
        _candle(BASE + MINUTE, open_=1.2, high=6.0, low=1.0, close=5.0, volume=20.0),
        _candle(BASE + 2 * MINUTE, open_=5.1, high=7.0, low=0.1, close=3.3, volume=30.0),
    ]
    [out] = resample(candles, base="1m", target="1h")
    assert (out.open, out.high, out.low, out.close, out.volume) == pytest.approx(
        (1.0, 7.0, 0.1, 3.3, 60.0), abs=1e-9
    )


def test_1h_to_1d():
    candles = [_candle(BASE + i * HOUR, volume=100.0) for i in range(72)]
    result = resample(candles, base="1h", target="1d")
    assert len(result) == 3
    assert [c.ts for c in result] == [BASE, BASE + DAY, BASE + 2 * DAY]
    assert all(c.volume == pytest.approx(2400.0) for c in result)


def test_1d_to_1wk_uses_fixed_windows():
    candles = [_candle(BASE + i * DAY, close=float(i)) for i in range(14)]
    result = resample(candles, base="1d", target="1wk")
    assert len(result) == 2
    assert result[0].ts == BASE
    assert result[1].ts == BASE + WEEK
    assert result[0].close == 6.0
    assert result[1].close == 13.0


def test_ts_is_start_of_bucket():
    mid_hour = BASE + 30 * MINUTE
    candles = [_candle(mid_hour)]
    [out] = resample(candles, base="1m", target="1h")
    assert out.ts == BASE


def test_empty_input():
    assert resample([], base="1m", target="1h") == []


def test_unknown_base_raises():
    with pytest.raises(ResampleError):
        resample([_candle(BASE)], base="7m", target="1h")


def test_unknown_target_raises():
    with pytest.raises(ResampleError):
        resample([_candle(BASE)], base="1m", target="13m")


def test_target_not_multiple_of_base_raises():
    with pytest.raises(ResampleError):
        resample([_candle(BASE + HOUR)], base="1h", target="30m")


def test_target_multiple_of_base_ok():
    candles = [_candle(BASE + i * HOUR) for i in range(4)]
    result = resample(candles, base="1h", target="4h")
    assert len(result) == 1
    assert result[0].ts == BASE


def test_single_candle_passthrough():
    [out] = resample([_candle(BASE + MINUTE * 3)], base="1m", target="1h")
    assert out.ts == BASE
    assert out.open == 1.0
    assert out.volume == 10.0


def test_identical_base_target_is_identity():
    candles = [_candle(BASE + i * HOUR) for i in range(4)]
    result = resample(candles, base="1h", target="1h")
    assert result == candles


def test_unsorted_input_raises():
    candles = [_candle(BASE + MINUTE), _candle(BASE)]
    with pytest.raises(ResampleError):
        resample(candles, base="1m", target="1h")


def test_bucket_table_has_all_supported_intervals():
    assert set(BUCKETS) == {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk"}