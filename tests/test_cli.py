"""Tests for the CLI: in-process invocation, stdout and exit codes."""

import pytest

from conftest import FakeTransport, load_fixture
from tickstore import Candle, Store
from tickstore.cli import main


def _save(tmp_path, candles, symbol="BTCUSDT", interval="1m", dbname="t.db"):
    db = str(tmp_path / dbname)
    with Store(db) as store:
        store.save(candles, symbol, interval)
    return db


def test_fetch_prints_table_without_save(tmp_path, capsys, binance_transport):
    code = main(
        ["fetch", "BTCUSDT", "--interval", "1h", "--limit", "30"],
        transport=binance_transport,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "BTCUSDT 1h (3 candles)" in out
    assert "50200" in out
    assert "1767229200000" in out
    assert "saved" not in out


def test_fetch_save_stores_and_prints_count(tmp_path, capsys, binance_transport):
    db = str(tmp_path / "t.db")
    code = main(
        ["fetch", "BTCUSDT", "--interval", "1h", "--limit", "30", "--save", "--db", db],
        transport=binance_transport,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip() == "saved 3 candles"
    with Store(db) as store:
        assert store.total_rows() == 3


def test_fetch_yahoo_stores(tmp_path, capsys, yahoo_transport):
    db = str(tmp_path / "t.db")
    code = main(
        ["fetch", "MSFT", "--exchange", "yahoo", "--interval", "1h", "--save", "--db", db],
        transport=yahoo_transport,
    )
    assert code == 0
    assert capsys.readouterr().out.strip() == "saved 2 candles"
    with Store(db) as store:
        assert store.total_rows() == 2


def test_fetch_passes_start_in_query(tmp_path, capsys, binance_transport):
    db = str(tmp_path / "t.db")
    code = main(
        [
            "fetch",
            "BTCUSDT",
            "--interval",
            "1h",
            "--start",
            "2026-01-01",
            "--save",
            "--db",
            db,
        ],
        transport=binance_transport,
    )
    assert code == 0
    assert "startTime=1767225600000" in binance_transport.requests[0]


def test_fetch_http_error_returns_1(tmp_path, capsys):
    transport = FakeTransport({"/api/v3/klines": (500, b"boom")})
    code = main(
        ["fetch", "BTCUSDT", "--save", "--db", str(tmp_path / "t.db")],
        transport=transport,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "error:" in captured.err


def test_status_prints_coverage(tmp_path, capsys):
    candles = [
        Candle(ts=0, open=1, high=2, low=0.5, close=1.5, volume=10),
        Candle(ts=60_000, open=1, high=2, low=0.5, close=1.5, volume=10),
        Candle(ts=120_000, open=1, high=2, low=0.5, close=1.5, volume=10),
        Candle(ts=360_000, open=1, high=2, low=0.5, close=1.5, volume=10),
        Candle(ts=420_000, open=1, high=2, low=0.5, close=1.5, volume=10),
    ]
    db = _save(tmp_path, candles, interval="1m")
    code = main(["status", "BTCUSDT", "--db", db])
    out = capsys.readouterr().out
    assert code == 0
    assert "interval" in out
    assert "gaps" in out
    assert "1m" in out
    assert "3" in out
    assert "5" in out


def test_status_no_data(tmp_path, capsys):
    db = str(tmp_path / "empty.db")
    code = main(["status", "BTCUSDT", "--db", db])
    assert code == 0
    assert "no data for BTCUSDT" in capsys.readouterr().out


def test_status_single_interval_filter(tmp_path, capsys):
    db = _save(tmp_path, [Candle(0, 1, 2, 0.5, 1.5, 10)], interval="1d")
    code = main(["status", "BTCUSDT", "--interval", "1h", "--db", db])
    assert code == 0
    assert "no data for BTCUSDT" in capsys.readouterr().out


def test_indicators_prints_latest_values(tmp_path, capsys):
    candles = [
        Candle(ts=i * 60_000, open=i, high=i + 1, low=i - 1, close=i, volume=1)
        for i in range(21)
    ]
    db = _save(tmp_path, candles, interval="1m")
    code = main(
        ["indicators", "BTCUSDT", "--interval", "1m", "--sma", "3", "--rsi", "14", "--db", db]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "sma(3)    = 19.000000" in out
    assert "rsi(14)    = 100.000000" in out
    assert "vwap()    =" in out
    assert "bands(20)" in out


def test_indicators_no_data_returns_1(tmp_path, capsys):
    db = str(tmp_path / "t.db")
    code = main(["indicators", "BTCUSDT", "--db", db])
    captured = capsys.readouterr()
    assert code == 1
    assert "no data for BTCUSDT 1h" in captured.out


def test_unknown_command_exits_2():
    with pytest.raises(SystemExit) as exc_info:
        main(["bogus"])
    assert exc_info.value.code == 2


def test_missing_symbol_exits_2():
    with pytest.raises(SystemExit) as exc_info:
        main(["fetch"])
    assert exc_info.value.code == 2


def test_fetch_defaults_to_binance_and_tickstore_db(tmp_path, capsys, binance_transport):
    db = str(tmp_path / "tickstore.db")
    code = main(
        ["fetch", "BTCUSDT", "--limit", "5", "--save", "--db", db],
        transport=binance_transport,
    )
    assert code == 0
    with Store(db) as store:
        assert store.total_rows() == 3


def test_cli_offline_pipeline_end_to_end(tmp_path, capsys):
    db = str(tmp_path / "t.db")
    transport = FakeTransport(
        {
            "/api/v3/klines": (200, load_fixture("binance_klines.json")),
            "/v8/finance/chart/": (200, load_fixture("yahoo_chart.json")),
        }
    )
    assert (
        main(
            ["fetch", "BTCUSDT", "--save", "--interval", "1h", "--db", db],
            transport=transport,
        )
        == 0
    )
    assert (
        main(
            [
                "fetch",
                "MSFT",
                "--exchange",
                "yahoo",
                "--save",
                "--interval",
                "1h",
                "--db",
                db,
            ],
            transport=transport,
        )
        == 0
    )
    assert main(["status", "BTCUSDT", "--db", db]) == 0
    assert main(["indicators", "MSFT", "--interval", "1h", "--sma", "3", "--db", db]) == 0
    captured = capsys.readouterr()
    assert "saved 3 candles" in captured.out
    assert "saved 2 candles" in captured.out