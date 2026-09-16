"""Tests for the SQLite store: upserts, CSV, refresh logic."""

import time

import pytest

from tickstore import Store
from tickstore.candle import Candle


def _candle(ts: int, close: float, volume: float = 10.0) -> Candle:
    return Candle(
        ts=ts,
        open=close - 1.0,
        high=close + 1.0,
        low=close - 2.0,
        close=close,
        volume=volume,
    )


def _csv_text(rows) -> str:
    lines = ["ts,open,high,low,close,volume"]
    for row in rows:
        lines.append(",".join(str(cell) for cell in row))
    return "\n".join(lines) + "\n"


class TestBasic:
    def test_in_memory_store_roundtrip(self, make_candles):
        with Store() as store:
            candles = make_candles(3)
            saved = store.save(candles, "BTCUSDT", "1m")
            assert saved == 3
            assert store.load("BTCUSDT", "1m") == candles

    def test_create_creates_tickstore_db(self, tmp_path):
        directory = tmp_path / "data"
        store = Store.create(str(directory))
        assert (directory / "tickstore.db").exists()
        assert store.total_rows() == 0
        store.close()

    def test_save_load_roundtrip(self, tmp_path, make_candles):
        db = str(tmp_path / "t.db")
        candles = make_candles(5, start=1000, step=60_000)
        with Store(db) as store:
            store.save(candles, "BTCUSDT", "1h")
            loaded = store.load("BTCUSDT", "1h")
        assert loaded == candles

    def test_save_upserts_overlapping_by_ts(self, tmp_path, make_candles):
        db = str(tmp_path / "t.db")
        first = make_candles(3, start=1000, step=60_000)
        with Store(db) as store:
            store.save(first, "BTCUSDT", "1m")
        replacement = [
            _candle(ts=61_000, close=999.0),
            _candle(ts=181_000, close=777.0),
        ]
        with Store(db) as store:
            store.save(replacement, "BTCUSDT", "1m")
            candles = store.load("BTCUSDT", "1m")
        assert [c.ts for c in candles] == [1000, 61_000, 121_000, 181_000]
        assert candles[1].close == 999.0
        assert candles[0].close == pytest.approx(first[0].close)

    def test_symbols_are_isolated(self, tmp_path, make_candles):
        db = str(tmp_path / "t.db")
        with Store(db) as store:
            store.save(make_candles(2, start=1000), "AAA", "1m")
            store.save(make_candles(3, start=1000), "BBB", "1m")
        with Store(db) as store:
            assert store.total_rows() == 5
            assert len(store.load("AAA", "1m")) == 2
            assert len(store.load("BBB", "1m")) == 3

    def test_load_start_end_filter(self, tmp_path, make_candles):
        db = str(tmp_path / "t.db")
        candles = make_candles(4, start=100, step=100)
        with Store(db) as store:
            store.save(candles, "AAA", "1m")
            assert [c.ts for c in store.load("AAA", "1m", start=200)] == [200, 300, 400]
            assert [c.ts for c in store.load("AAA", "1m", end=200)] == [100, 200]
            assert [c.ts for c in store.load("AAA", "1m", start=200, end=300)] == [200, 300]

    def test_latest_ts_none_and_value(self, tmp_path, make_candles):
        db = str(tmp_path / "t.db")
        with Store(db) as store:
            assert store.latest_ts("AAA", "1m") is None
            store.save(make_candles(3, start=100, step=100), "AAA", "1m")
            assert store.latest_ts("AAA", "1m") == 300

    def test_has(self, tmp_path, make_candles):
        db = str(tmp_path / "t.db")
        with Store(db) as store:
            assert not store.has("AAA", "1m")
            store.save(make_candles(1), "AAA", "1m")
            assert store.has("AAA", "1m")
            assert not store.has("AAA", "1d")
            assert not store.has("BBB", "1m")

    def test_intervals_lists_distinct(self, tmp_path, make_candles):
        db = str(tmp_path / "t.db")
        with Store(db) as store:
            store.save(make_candles(1, start=100), "AAA", "4h")
            store.save(make_candles(1, start=200), "AAA", "1m")
            assert store.intervals("AAA") == ["1m", "4h"]

    def test_total_rows(self, tmp_path, make_candles):
        db = str(tmp_path / "t.db")
        with Store(db) as store:
            store.save(make_candles(4, start=100), "AAA", "1m")
            store.save(make_candles(2, start=100), "BBB", "5m")
            assert store.total_rows() == 6


class TestCsv:
    def test_export_csv_roundtrip(self, tmp_path, make_candles):
        db = str(tmp_path / "t.db")
        candles = make_candles(4, start=1767225600000, step=60_000)
        out = str(tmp_path / "out.csv")
        with Store(db) as store:
            store.save(candles, "AAA", "1m")
            assert store.export_csv(out, "AAA", "1m") == 4
        with Store(db) as store:
            loaded = store.load_csv(out, "ZZZ", "1h")
        assert loaded == candles

    def test_load_csv_iso_seconds_and_ms(self, tmp_path):
        text = _csv_text(
            [
                ("2026-01-01T00:00:00Z", 10, 12, 9, 11, 100),
                (1000, 10, 12, 9, 11, 200),
                (1767229200000, 10, 12, 9, 11, 300),
            ]
        )
        path = tmp_path / "in.csv"
        path.write_text(text)
        with Store() as store:
            candles = store.load_csv(str(path), "AAA", "1m")
        assert [c.ts for c in candles] == [1767225600000, 1_000_000, 1767229200000]
        assert [c.volume for c in candles] == [100, 200, 300]

    def test_load_csv_headerless_positional_and_blank_lines(self, tmp_path):
        path = tmp_path / "in.csv"
        path.write_text(
            "1767225600000,10,12,9,11,100\n"
            "\n"
            "1767229200000,20,22,19,21,200\n"
        )
        with Store() as store:
            candles = store.load_csv(str(path), "AAA", "1m")
        assert [c.ts for c in candles] == [1767225600000, 1767229200000]

    def test_load_csv_alt_header_names(self, tmp_path):
        path = tmp_path / "in.csv"
        path.write_text(
            "timestamp,open,high,low,close,volume\n"
            "1000,1,2,0.5,1.5,50\n"
        )
        with Store() as store:
            candles = store.load_csv(str(path), "AAA", "1m")
        assert candles[0].ts == 1_000_000
        assert candles[0].close == 1.5


class TestRefresh:
    def _recording_fetch(self):
        calls = []

        def fetch(symbol, interval, limit=500, start=None):
            calls.append((symbol, interval, limit, start))
            return []

        fetch.calls = calls
        return fetch

    def test_refresh_fetches_only_missing_tail(self, make_candles):
        store = Store(":memory:")
        store.save(make_candles(2, start=1000, step=60_000), "AAA", "1m")

        def tail_fetch(symbol, interval, limit=500, start=None):
            assert start == 61_001
            return [_candle(ts=121_000, close=98.0)]

        store.refresh("AAA", "1m", tail_fetch)
        assert store.total_rows() == 3
        assert store.latest_ts("AAA", "1m") == 121_000

    def test_refresh_skips_fetch_when_fresh(self, make_candles):
        store = Store(":memory:")
        store.save([_candle(ts=int(time.time() * 1000) - 1000, close=100.0)], "AAA", "1m")

        def boom(symbol, interval, limit=500, start=None):
            raise AssertionError("fetch must not run when data is fresh")

        store.refresh("AAA", "1m", boom, max_age_seconds=3600)
        assert store.total_rows() == 1

    def test_refresh_fetches_when_stale(self, make_candles):
        store = Store(":memory:")
        store.save([_candle(ts=int(time.time() * 1000) - 7200 * 1000, close=100.0)], "AAA", "1m")
        fetch = self._recording_fetch()
        store.refresh("AAA", "1m", fetch, max_age_seconds=3600)
        assert len(fetch.calls) == 1

    def test_refresh_paginates_full_batches(self, make_candles):
        store = Store(":memory:")
        batches = {
            None: make_candles(2, start=1000, step=60_000),
            61_001: make_candles(2, start=61_001, step=60_000),
            121_002: make_candles(1, start=121_002, step=60_000),
        }
        calls = []

        def fetch(symbol, interval, limit=500, start=None):
            calls.append(start)
            return batches.get(start, [])

        store.refresh("AAA", "1m", fetch, limit=2)
        assert calls == [None, 61_001, 121_002]
        assert store.total_rows() == 5

    def test_refresh_empty_initial_fetch_leaves_empty(self):
        store = Store(":memory:")
        fetch = self._recording_fetch()
        result = store.refresh("AAA", "1m", fetch)
        assert result == []
        assert fetch.calls == [("AAA", "1m", 500, None)]
        assert store.total_rows() == 0