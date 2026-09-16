"""Tests for the Binance and Yahoo providers (fully offline)."""

import pytest

from tickstore import ProviderError
from tickstore.providers import BinanceProvider, YahooProvider, default_transport, to_epoch_ms

from conftest import FakeTransport, load_fixture

BINANCE_ROWS = [
    (1767225600000, 50000.0, 50100.0, 49900.0, 50050.0, 12.5),
    (1767229200000, 50050.0, 50300.0, 49950.0, 50200.0, 18.2),
    (1767232800000, 50200.0, 50500.0, 50100.0, 50400.0, 9.75),
]

YAHOO_ROWS = [
    (1767225600000, 410.0, 412.0, 408.5, 411.25, 1200000.0),
    (1767232800000, 410.5, 415.0, 410.0, 414.75, 1500000.0),
]


def _assert_rows(candles, expected):
    assert len(candles) == len(expected)
    for candle, (ts, open_, high, low, close, volume) in zip(candles, expected):
        assert candle.ts == ts
        assert candle.open == pytest.approx(open_, abs=1e-9)
        assert candle.high == pytest.approx(high, abs=1e-9)
        assert candle.low == pytest.approx(low, abs=1e-9)
        assert candle.close == pytest.approx(close, abs=1e-9)
        assert candle.volume == pytest.approx(volume, abs=1e-9)


class TestBinance:
    def test_fetch_parses_fixture(self, binance_transport):
        provider = BinanceProvider(binance_transport)
        candles = provider.fetch("BTCUSDT", "1h")
        _assert_rows(candles, BINANCE_ROWS)

    def test_fetch_builds_full_url(self, binance_transport):
        provider = BinanceProvider(binance_transport)
        provider.fetch("btcusdt", "4h", limit=250, start="2026-01-01")
        url = binance_transport.requests[0]
        assert url.startswith("https://api.binance.com/api/v3/klines?")
        assert "symbol=BTCUSDT" in url
        assert "interval=4h" in url
        assert "limit=250" in url
        assert "startTime=1767225600000" in url

    def test_fetch_uppercases_symbol(self, binance_transport):
        provider = BinanceProvider(binance_transport)
        provider.fetch("btcusdt", "1h")
        assert "symbol=BTCUSDT" in binance_transport.requests[0]

    def test_fetch_end_time_param(self, binance_transport):
        provider = BinanceProvider(binance_transport)
        provider.fetch("BTCUSDT", "1h", end=1767232800000)
        assert "endTime=1767232800000" in binance_transport.requests[0]

    def test_fetch_unknown_interval_raises(self, binance_transport):
        provider = BinanceProvider(binance_transport)
        with pytest.raises(ProviderError):
            provider.fetch("BTCUSDT", "1h200")

    def test_fetch_http_error_raises(self):
        transport = FakeTransport({"/api/v3/klines": (418, b"teapot")})
        provider = BinanceProvider(transport)
        with pytest.raises(ProviderError):
            provider.fetch("BTCUSDT", "1h")

    def test_fetch_non_list_payload_raises(self):
        transport = FakeTransport({"/api/v3/klines": (200, b'{"oops": 1}')})
        provider = BinanceProvider(transport)
        with pytest.raises(ProviderError):
            provider.fetch("BTCUSDT", "1h")

    def test_fetch_malformed_row_raises(self):
        payload = b'[["1767225600000", "50000.00"]]'
        transport = FakeTransport({"/api/v3/klines": (200, payload)})
        provider = BinanceProvider(transport)
        with pytest.raises(ProviderError):
            provider.fetch("BTCUSDT", "1h")

    def test_decode_kline_types_all_twelve_fields(self):
        row = [
            "1767225600000",
            "50000.00",
            "50100.00",
            "49900.00",
            "50050.00",
            "12.50000000",
            "1767229199999",
            "626000.00",
            845,
            "6.25000000",
            "206.50000000",
            "0",
        ]
        fields = BinanceProvider.decode_kline(row)
        assert len(fields) == 12
        assert isinstance(fields[0], int)
        assert isinstance(fields[1], float)
        assert isinstance(fields[6], int)
        assert isinstance(fields[8], int)
        assert isinstance(fields[11], int)
        assert fields[0] == 1767225600000
        assert fields[6] == 1767229199999
        assert fields[11] == 0


class TestYahoo:
    def test_fetch_parses_and_drops_nulls(self, yahoo_transport):
        provider = YahooProvider(yahoo_transport)
        candles = provider.fetch("MSFT", "1h")
        _assert_rows(candles, YAHOO_ROWS)

    def test_fetch_defaults_to_range_5d(self, yahoo_transport):
        provider = YahooProvider(yahoo_transport)
        provider.fetch("MSFT", "1h")
        url = yahoo_transport.requests[0]
        assert url.startswith("https://query1.finance.yahoo.com/v8/finance/chart/MSFT?")
        assert "interval=1h" in url
        assert "range=5d" in url

    def test_fetch_uses_period1_when_start_given(self, yahoo_transport):
        provider = YahooProvider(yahoo_transport)
        provider.fetch("MSFT", "1d", start="2026-01-01")
        url = yahoo_transport.requests[0]
        assert "period1=1767225600" in url
        assert "range=" not in url

    def test_fetch_yearly_interval_map(self, yahoo_transport):
        provider = YahooProvider(yahoo_transport)
        provider.fetch("MSFT", "1wk")
        assert "interval=1wk" in yahoo_transport.requests[0]

    def test_fetch_unknown_interval_raises(self, yahoo_transport):
        provider = YahooProvider(yahoo_transport)
        with pytest.raises(ProviderError):
            provider.fetch("MSFT", "12h")

    def test_fetch_http_error_raises(self):
        transport = FakeTransport({"/v8/finance/chart/": (429, b"ratelimit")})
        provider = YahooProvider(transport)
        with pytest.raises(ProviderError):
            provider.fetch("MSFT", "1h")

    def test_fetch_empty_result_raises(self):
        payload = b'{"chart": {"result": [], "error": null}}'
        transport = FakeTransport({"/v8/finance/chart/": (200, payload)})
        provider = YahooProvider(transport)
        with pytest.raises(ProviderError):
            provider.fetch("MSFT", "1h")

    def test_fetch_api_error_raises(self):
        payload = b'{"chart": {"result": [], "error": {"code": "Not Found"}}}'
        transport = FakeTransport({"/v8/finance/chart/": (200, payload)})
        provider = YahooProvider(transport)
        with pytest.raises(ProviderError):
            provider.fetch("MSFT", "1h")

    def test_fetch_missing_quote_raises(self):
        payload = b'{"chart": {"result": [{"timestamp": [1, 2]}], "error": null}}'
        transport = FakeTransport({"/v8/finance/chart/": (200, payload)})
        provider = YahooProvider(transport)
        with pytest.raises(ProviderError):
            provider.fetch("MSFT", "1h")


class TestTransport:
    def test_default_transport_is_callable(self):
        provider = BinanceProvider()
        assert callable(provider.transport)
        assert provider.transport is default_transport

    def test_http_error_transport_closes_with_status(self):
        transport = FakeTransport({"/x": (503, b"down")})
        status, body = transport("https://example.com/x")
        assert status == 503
        assert body == b"down"

    def test_all_provider_requests_recorded(self, binance_transport, yahoo_transport):
        BinanceProvider(binance_transport).fetch("BTCUSDT", "1h")
        YahooProvider(yahoo_transport).fetch("MSFT", "1h")
        assert len(binance_transport.requests) == 1
        assert len(yahoo_transport.requests) == 1


class TestTimeParsing:
    def test_iso_date_and_datetime(self):
        assert to_epoch_ms("2026-01-01") == 1767225600000
        assert to_epoch_ms("2026-01-01T00:00:00Z") == 1767225600000

    def test_numeric_ms_and_numeric_string(self):
        assert to_epoch_ms(1767225600000) == 1767225600000
        assert to_epoch_ms("1767225600000") == 1767225600000

    def test_bool_rejected(self):
        with pytest.raises(TypeError):
            to_epoch_ms(True)


def test_fixture_files_available():
    for name in ("binance_klines.json", "yahoo_chart.json", "sample_1m.csv"):
        assert len(load_fixture(name)) > 0