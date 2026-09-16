"""SQLite-backed local candle cache with CSV import/export.

The store is a single SQLite database holding one ``candles`` table keyed by
``(symbol, interval, ts)``. Writes use ``INSERT OR REPLACE`` so re-saving an
overlapping batch is an upsert: existing timestamps are overwritten and new
ones appended.

Thread safety is intentionally out of scope. Design for one writer process;
concurrent readers are fine on a file database.
"""

from __future__ import annotations

import csv
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Protocol, Sequence

from .candle import Candle


class Fetcher(Protocol):
    """Protocol for callables used by :meth:`Store.refresh`.

    Matches the signature of ``BaseProvider.fetch`` so a provider instance can
    be passed directly.
    """

    def __call__(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start: Optional[object] = None,
    ) -> List[Candle]:
        ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    symbol   TEXT    NOT NULL,
    interval TEXT    NOT NULL,
    ts       INTEGER NOT NULL,
    open     REAL    NOT NULL,
    high     REAL    NOT NULL,
    low      REAL    NOT NULL,
    close    REAL    NOT NULL,
    volume   REAL    NOT NULL,
    PRIMARY KEY (symbol, interval, ts)
)
"""


def _parse_timestamp(token: str) -> int:
    """Parse a CSV timestamp token into epoch milliseconds.

    Supports epoch seconds, epoch milliseconds, and ISO-8601 dates/datetimes.

    Args:
        token: The raw string cell.

    Returns:
        Epoch milliseconds.

    Raises:
        ValueError: If the token cannot be interpreted as a timestamp.
    """

    token = token.strip()
    try:
        number = float(token)
    except ValueError:
        normalized = token.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    if abs(number) >= 10**12:
        return int(number)
    return int(number * 1000)


def _column_index(header: Optional[Sequence[str]], name: str, fallback: int) -> int:
    """Resolve a CSV column index for a header-aware import.

    Args:
        header: Lowercased header names, or None for positional rows.
        name: Preferred column name.
        fallback: Positional index used when the header is missing or the
            name is absent.

    Returns:
        The column index to read.
    """

    if header is not None:
        lookup = {column: index for index, column in enumerate(header)}
        for alias in (name, name.replace("_", "")):
            if alias in lookup:
                return lookup[alias]
    return fallback


class Store:
    """Local SQLite cache for candles.

    Args:
        path: Database file path, or ``":memory:"`` for a transient database.

    Attributes:
        conn: The underlying ``sqlite3.Connection``.
    """

    def __init__(self, path: str = ":memory:"):
        """Open (creating if needed) a SQLite candle database."""

        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_SCHEMA)
        self.conn.commit()

    @classmethod
    def create(cls, directory: str) -> "Store":
        """Create (or open) a store inside ``directory``.

        The directory and its parents are created as needed, and the database
        file is always named ``tickstore.db``.

        Args:
            directory: Directory to hold ``tickstore.db``.

        Returns:
            A ready-to-use store.
        """

        os.makedirs(directory, exist_ok=True)
        path = str(Path(directory) / "tickstore.db")
        return cls(path)

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        self.conn.close()

    def __enter__(self) -> "Store":
        """Enter the context manager."""

        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        """Exit the context manager and close the connection."""

        self.close()

    def save(self, candles: Sequence[Candle], symbol: str, interval: str) -> int:
        """Upsert candles for a symbol/interval pair.

        Timestamps already present are overwritten; the batch is committed in
        one transaction.

        Args:
            candles: Candles to store.
            symbol: Symbol key.
            interval: Interval key.

        Returns:
            Number of rows written (matches ``len(candles)``).
        """

        rows = [
            (
                symbol,
                interval,
                candle.ts,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
            )
            for candle in candles
        ]
        if not rows:
            return 0
        self.conn.executemany(
            "INSERT OR REPLACE INTO candles "
            "(symbol, interval, ts, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def load(
        self,
        symbol: str,
        interval: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
    ) -> List[Candle]:
        """Load candles for a symbol/interval pair, ordered by timestamp.

        Args:
            symbol: Symbol key.
            interval: Interval key.
            start: Include only candles with ``ts >= start``.
            end: Include only candles with ``ts <= end``.

        Returns:
            Candles ordered by ascending timestamp.
        """

        query = (
            "SELECT ts, open, high, low, close, volume FROM candles "
            "WHERE symbol = ? AND interval = ?"
        )
        params: List[object] = [symbol, interval]
        if start is not None:
            query += " AND ts >= ?"
            params.append(start)
        if end is not None:
            query += " AND ts <= ?"
            params.append(end)
        query += " ORDER BY ts"
        rows = self.conn.execute(query, params).fetchall()
        return [
            Candle(
                ts=int(row["ts"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            for row in rows
        ]

    def latest_ts(self, symbol: str, interval: str) -> Optional[int]:
        """Return the newest stored timestamp for a pair, or None.

        Args:
            symbol: Symbol key.
            interval: Interval key.

        Returns:
            The maximum timestamp in milliseconds, or None when empty.
        """

        row = self.conn.execute(
            "SELECT ts FROM candles WHERE symbol = ? AND interval = ? "
            "ORDER BY ts DESC LIMIT 1",
            (symbol, interval),
        ).fetchone()
        return int(row["ts"]) if row is not None else None

    def has(self, symbol: str, interval: str) -> bool:
        """Return True when any candle exists for a symbol/interval pair.

        Args:
            symbol: Symbol key.
            interval: Interval key.

        Returns:
            Whether at least one candle is stored for the pair.
        """

        row = self.conn.execute(
            "SELECT 1 FROM candles WHERE symbol = ? AND interval = ? LIMIT 1",
            (symbol, interval),
        ).fetchone()
        return row is not None

    def intervals(self, symbol: str) -> List[str]:
        """List distinct intervals stored for a symbol.

        Args:
            symbol: Symbol key.

        Returns:
            Distinct interval names, ordered alphabetically.
        """

        rows = self.conn.execute(
            "SELECT DISTINCT interval FROM candles WHERE symbol = ? ORDER BY interval",
            (symbol,),
        ).fetchall()
        return [str(row["interval"]) for row in rows]

    def total_rows(self) -> int:
        """Return the total number of stored candles.

        Returns:
            Count of every row in the ``candles`` table.
        """

        row = self.conn.execute("SELECT COUNT(*) FROM candles").fetchone()
        return int(row[0])

    def refresh(
        self,
        symbol: str,
        interval: str,
        fetch: Fetcher,
        max_age_seconds: Optional[int] = None,
        limit: int = 500,
    ) -> List[Candle]:
        """Bring a series up to date and return the full stored series.

        Fetches only the missing tail: when the pair already has data the
        ``start`` argument of the next fetch is set one millisecond past the
        latest stored timestamp. When ``max_age_seconds`` is given and the
        latest candle is younger, the fetch is skipped entirely.

        Args:
            symbol: Symbol key.
            interval: Interval key.
            fetch: Any callable matching :class:`Fetcher`, typically a
                provider instance.
            max_age_seconds: When set, skip the network entirely if the newest
                stored candle is younger than this many seconds.
            limit: Batch size used while paginating.

        Returns:
            The complete series after the refresh, ordered by timestamp.
        """

        latest = self.latest_ts(symbol, interval)
        if latest is not None:
            age_ms = int(time.time() * 1000) - latest
            if max_age_seconds is not None and age_ms < max_age_seconds * 1000:
                return self.load(symbol, interval)
            start: Optional[object] = latest + 1
        else:
            start = None

        candles: List[Candle] = []
        cursor = start
        while True:
            batch = fetch(symbol, interval, limit=limit, start=cursor)
            if not batch:
                break
            candles.extend(batch)
            if len(batch) < limit:
                break
            cursor = batch[-1].ts + 1
        if candles:
            self.save(candles, symbol, interval)
        return self.load(symbol, interval)

    def export_csv(self, path: str, symbol: str, interval: str) -> int:
        """Export a symbol/interval pair to a CSV file.

        The file has a ``ts,open,high,low,close,volume`` header with epoch
        millisecond timestamps.

        Args:
            path: Destination file path.
            symbol: Symbol key.
            interval: Interval key.

        Returns:
            Number of rows written.
        """

        candles = self.load(symbol, interval)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["ts", "open", "high", "low", "close", "volume"])
            for candle in candles:
                writer.writerow(
                    [
                        candle.ts,
                        candle.open,
                        candle.high,
                        candle.low,
                        candle.close,
                        candle.volume,
                    ]
                )
        return len(candles)

    def load_csv(self, path: str, symbol: str, interval: str) -> List[Candle]:
        """Import candles from a CSV file.

        Accepts either a header row (``ts,open,high,low,close,volume`` with
        flexible column names) or bare positional rows. Timestamps may be
        epoch seconds, epoch milliseconds, or ISO-8601.

        Args:
            path: Source CSV path.
            symbol: Symbol key to store under.
            interval: Interval key to store under.

        Returns:
            The parsed candles.

        Raises:
            ValueError: On a row that cannot be converted.
        """

        with open(path, newline="", encoding="utf-8") as handle:
            raw_rows = list(csv.reader(handle))
        if not raw_rows:
            return []
        first = raw_rows[0]
        header: Optional[List[str]] = None
        rows = raw_rows
        if first and not _is_numeric(first[0]):
            header = [str(cell).strip().lower() for cell in first]
            rows = raw_rows[1:]

        ts_index = _column_index(header, "ts", 0)
        open_index = _column_index(header, "open", 1)
        high_index = _column_index(header, "high", 2)
        low_index = _column_index(header, "low", 3)
        close_index = _column_index(header, "close", 4)
        volume_index = _column_index(header, "volume", 5)

        candles: List[Candle] = []
        for row in rows:
            if not row or not row[0].strip():
                continue
            candles.append(
                Candle(
                    ts=_parse_timestamp(row[ts_index]),
                    open=float(row[open_index]),
                    high=float(row[high_index]),
                    low=float(row[low_index]),
                    close=float(row[close_index]),
                    volume=float(row[volume_index]),
                )
            )
        return candles

    def record_csv(self, path: str, symbol: str, interval: str) -> int:
        """Import a CSV file into the store and persist it.

        Args:
            path: Source CSV path.
            symbol: Symbol key to store under.
            interval: Interval key to store under.

        Returns:
            Number of candles saved.
        """

        candles = self.load_csv(path, symbol, interval)
        return self.save(candles, symbol, interval)


def _is_numeric(token: str) -> bool:
    """Return True when a string cell parses as a number.

    Args:
        token: The cell to test.

    Returns:
        Whether ``token`` parses as a float.
    """

    try:
        float(str(token).strip())
        return True
    except ValueError:
        return False