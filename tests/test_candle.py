"""Tests for the candle data model and validation helpers."""

import pytest
from dataclasses import FrozenInstanceError

from tickstore.candle import Candle, candle_issues, series, validate


def _candle(**overrides) -> Candle:
    """Build a default sane candle with optional field overrides."""

    fields = dict(
        ts=1,
        open=10.0,
        high=12.0,
        low=9.0,
        close=11.0,
        volume=100.0,
    )
    fields.update(overrides)
    return Candle(**fields)


def test_series_returns_closes_in_order():
    candles = [
        _candle(ts=1, close=11.0),
        _candle(ts=2, close=12.0),
        _candle(ts=3, close=13.0),
    ]
    assert series(candles) == [11.0, 12.0, 13.0]


def test_candle_is_frozen():
    with pytest.raises(FrozenInstanceError):
        _candle().open = 99.0


def test_candle_issues_empty_for_sane_candle():
    assert candle_issues(_candle()) == []


def test_candle_issues_high_below_open_close_max():
    issues = candle_issues(_candle(open=10.0, close=11.0, high=10.5))
    assert any("high" in issue for issue in issues)


def test_candle_issues_low_above_open_close_min():
    issues = candle_issues(_candle(open=10.0, close=11.0, low=10.5))
    assert any("low" in issue for issue in issues)


def test_candle_issues_negative_volume_always_reported():
    assert any("volume" in i for i in candle_issues(_candle(volume=-5.0)))
    assert any("volume" in i for i in candle_issues(_candle(volume=-5.0), check_volume=False))


def test_candle_issues_zero_volume_optional():
    assert any("volume" in i for i in candle_issues(_candle(volume=0.0)))
    assert candle_issues(_candle(volume=0.0), check_volume=False) == []


def test_validate_reports_indices_and_can_raise():
    bad = [_candle(), _candle(high=10.0, open=10.0, close=11.0)]
    messages = validate(bad)
    assert len(messages) == 1
    assert "ts=1" in messages[0]
    with pytest.raises(ValueError):
        validate(bad, raise_on_error=True)


def test_validate_mixed_issues_labels_candle():
    candles = [_candle(), _candle(ts=7, low=20.0)]
    messages = validate(candles)
    assert len(messages) == 1
    assert "ts=7" in messages[0]