"""Shared test infrastructure.

The centerpiece is the offline :class:`FakeTransport`: a callable shaped like
tickstore's ``transport`` hook that maps URL substrings to canned
``(status, bytes)`` responses and records every request so tests can assert on
the exact URLs the providers built.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import pytest

_FIXTURE_DIR = Path(__file__).parent / "fixtures"
_ROOT = _FIXTURE_DIR.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class FakeTransport:
    """Offline stand-in for ``providers.default_transport``.

    Responses are keyed by URL substring; the first matching key wins. Every
    request URL is appended to :attr:`requests` so tests can assert on the
    query strings the providers built.
    """

    def __init__(
        self,
        responses: Dict[str, Tuple[int, bytes]] | None = None,
        default_status: int = 404,
        default_body: bytes = b"not found",
    ) -> None:
        self.responses: Dict[str, Tuple[int, bytes]] = dict(responses or {})
        self.default: Tuple[int, bytes] = (default_status, default_body)
        self.requests: List[str] = []

    def __call__(self, url: str) -> Tuple[int, bytes]:
        self.requests.append(url)
        for key, response in self.responses.items():
            if key in url:
                return response
        return self.default


def load_fixture(name: str) -> bytes:
    """Read a fixture file's raw bytes.

    Args:
        name: Fixture file name under ``tests/fixtures``.

    Returns:
        The raw file contents.
    """

    return (_FIXTURE_DIR / name).read_bytes()


@pytest.fixture
def binance_transport() -> FakeTransport:
    """A transport serving the canned Binance klines fixture."""

    return FakeTransport(
        {"/api/v3/klines": (200, load_fixture("binance_klines.json"))}
    )


@pytest.fixture
def yahoo_transport() -> FakeTransport:
    """A transport serving the canned Yahoo chart fixture."""

    return FakeTransport(
        {"/v8/finance/chart/": (200, load_fixture("yahoo_chart.json"))}
    )


@pytest.fixture
def sample_csv_path() -> str:
    """Absolute path of the generated 5-day sample fixture."""

    return str(_FIXTURE_DIR / "sample_1m.csv")


@pytest.fixture
def make_candles() -> Callable:
    """Factory for deterministic candle batches.

    Returns a callable ``(count, start, step, price)`` producing ``count``
    candles beginning at ``start`` with ``step`` milliseconds spacing and a
    fixed OHLCV envelope around ``price``.
    """

    def _make(count: int, start: int = 0, step: int = 60_000, price: float = 100.0):
        from tickstore import Candle

        candles = []
        for index in range(count):
            ts = start + index * step
            candles.append(
                Candle(
                    ts=ts,
                    open=price + index,
                    high=price + index + 1,
                    low=price + index - 1,
                    close=price + index + 0.5,
                    volume=10.0 + index,
                )
            )
        return candles

    return _make