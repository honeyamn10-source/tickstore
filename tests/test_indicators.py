"""Tests for indicators with hand-computed reference values."""

import math

import pytest

from tickstore import Candle
from tickstore.indicators import atr, bollinger_bands, ema, rsi, sma, vwap


def _c(ts, open_=0.0, high=0.0, low=0.0, close=0.0, volume=1.0):
    return Candle(ts=ts, open=open_, high=high, low=low, close=close, volume=volume)


def test_sma_reference():
    assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2, 3, 4]


def test_sma_n_greater_than_length():
    assert sma([1, 2, 3], 5) == [None, None, None]


def test_sma_invalid_n_raises():
    with pytest.raises(ValueError):
        sma([1, 2, 3], 0)


def test_ema_reference_values():
    result = ema([1, 2, 3, 4, 5], 3)
    assert result == pytest.approx([None, None, 2.5, 3.25, 4.125], abs=1e-9)


def test_ema_warmup_len():
    result = ema([1, 2, 3, 4, 5], 3)
    assert result[:2] == [None, None]
    assert len(result) == 5


def test_ema_n_greater_than_length():
    assert ema([1, 2], 5) == [None, None]


def test_ema_n_1_mirrors_input():
    assert ema([1.0, 2.0, 3.0], 1) == [1.0, 2.0, 3.0]


def test_ema_invalid_n_raises():
    with pytest.raises(ValueError):
        ema([1, 2, 3], -1)


def test_rsi_strictly_up_is_100():
    closes = [float(i) for i in range(30)]
    result = rsi(closes, 14)
    assert result[:14] == [None] * 14
    assert all(abs(value - 100.0) < 1e-9 for value in result[14:])


def test_rsi_strictly_down_is_0():
    closes = [float(30 - i) for i in range(30)]
    result = rsi(closes, 14)
    assert all(abs(value - 0.0) < 1e-9 for value in result[14:])


def test_rsi_flat_is_50():
    closes = [100.0] * 30
    result = rsi(closes, 14)
    assert all(abs(value - 50.0) < 1e-9 for value in result[14:])


def test_rsi_hand_computed_mixed_series():
    closes = [50, 51, 50, 52, 53, 51, 54]
    result = rsi(closes, 3)
    assert result[:3] == [None] * 3
    assert result[3] == pytest.approx(75.0, abs=1e-9)
    assert result[4] == pytest.approx(900.0 / 11.0, abs=1e-9)
    assert result[5] == pytest.approx(45.0, abs=1e-9)
    assert result[6] == pytest.approx(11700.0 / 161.0, abs=1e-9)


def test_rsi_warmup_when_insufficient_data():
    assert rsi([1, 2], 14) == [None, None]


def test_atr_hand_computed():
    candles = [
        _c(0, high=10, low=9, close=9.5),
        _c(1, high=11, low=10, close=10.5),
        _c(2, high=12, low=10.5, close=11.5),
        _c(3, high=13, low=11, close=12),
    ]
    assert atr(candles, 2) == pytest.approx([None, None, 1.5, 1.75], abs=1e-9)


def test_atr_warmup_when_insufficient_data():
    candles = [_c(0, high=10, low=9, close=9.5)]
    assert atr(candles, 14) == [None]


def test_atr_invalid_n_raises():
    with pytest.raises(ValueError):
        atr([_c(0, high=1, low=0, close=0.5)], 0)


def test_vwap_hand_computed():
    candles = [
        _c(0, high=10, low=9, close=9.5, volume=2),
        _c(1, high=11, low=10, close=10.5, volume=2),
    ]
    assert vwap(candles) == pytest.approx([9.5, 10.0], abs=1e-9)


def test_vwap_zero_volume_yields_none():
    candles = [
        _c(0, high=10, low=9, close=9.5, volume=0),
        _c(1, high=11, low=10, close=10.5, volume=2),
    ]
    result = vwap(candles)
    assert result[0] is None
    assert result[1] == pytest.approx(10.5, abs=1e-9)


def test_vwap_aligned_and_length():
    candles = [_c(i, high=10 + i, low=9 + i, close=9.5 + i) for i in range(7)]
    result = vwap(candles)
    assert len(result) == 7


def test_bollinger_bands_reference():
    middle, upper, lower = bollinger_bands([1, 2, 3, 4, 5], 3)
    deviation = math.sqrt(2.0 / 3.0)
    assert middle == pytest.approx([None, None, 2, 3, 4], abs=1e-9)
    assert upper == pytest.approx(
        [None, None, 2 + 2 * deviation, 3 + 2 * deviation, 4 + 2 * deviation],
        abs=1e-9,
    )
    assert lower == pytest.approx(
        [None, None, 2 - 2 * deviation, 3 - 2 * deviation, 4 - 2 * deviation],
        abs=1e-9,
    )


def test_bollinger_bands_constant_series():
    middle, upper, lower = bollinger_bands([5.0, 5.0, 5.0], 2)
    assert middle == pytest.approx([None, 5.0, 5.0], abs=1e-9)
    assert upper == pytest.approx([None, 5.0, 5.0], abs=1e-9)
    assert lower == pytest.approx([None, 5.0, 5.0], abs=1e-9)


def test_bollinger_bands_invalid_n_raises():
    with pytest.raises(ValueError):
        bollinger_bands([1, 2, 3], -2)


def test_all_indicator_outputs_aligned_to_input():
    closes = [float(i % 7) for i in range(20)]
    candles = [_c(i, high=2.0, low=0.5, close=closes[i], volume=1.0) for i in range(20)]
    for result in (sma(closes, 5), ema(closes, 5), rsi(closes, 5), atr(candles, 5), vwap(candles)):
        assert len(result) == 20