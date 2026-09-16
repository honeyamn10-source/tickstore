"""Exchange data providers.

Both bundled providers talk to public REST endpoints using only the standard
library (``urllib``) and accept an injected ``transport`` callable so every
code path is testable offline.

A transport is a plain callable ``transport(url) -> (status_code, body_bytes)``.
The default implementation wraps ``urllib.request.urlopen`` and translates
network failures into ``ProviderError``.
"""

from __future__ import annotations

import abc
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Callable, List, Optional, Tuple, Union

from .candle import Candle

Transport = Callable[[str], Tuple[int, bytes]]
StartValue = Union[int, float, str, date, datetime]


class ProviderError(Exception):
    """Raised when a provider request or payload cannot be handled."""


def to_epoch_ms(value: StartValue) -> int:
    """Convert a user-supplied start time to epoch milliseconds.

    Accepted inputs are a raw millisecond integer (passed through unchanged),
    an ISO-8601 date or datetime string such as ``2026-01-01`` or
    ``2026-01-01T00:00:00Z``, a ``datetime``/``date`` object, or a numeric
    string. Naive datetimes are interpreted as UTC, which keeps results
    deterministic regardless of the host timezone.

    Args:
        value: The value to convert.

    Returns:
        Epoch milliseconds as an integer.

    Raises:
        ValueError: If the value is a string that cannot be parsed.
        TypeError: If the value is of an unsupported type.
    """

    if isinstance(value, bool):
        raise TypeError("boolean values are not valid timestamps")
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp() * 1000)
    if isinstance(value, date):
        return to_epoch_ms(datetime(value.year, value.month, value.day))
    if isinstance(value, str):
        token = value.strip()
        if token.lstrip("-+").isdigit():
            return int(token)
        normalized = token.replace("Z", "+00:00")
        return to_epoch_ms(datetime.fromisoformat(normalized))
    raise TypeError(f"cannot interpret {value!r} as a timestamp")


def to_epoch_seconds(value: StartValue) -> int:
    """Convert a start time to integer epoch seconds.

    Args:
        value: The value to convert, as accepted by :func:`to_epoch_ms`.

    Returns:
        Epoch seconds as an integer.
    """

    return to_epoch_ms(value) // 1000


def default_transport(url: str) -> Tuple[int, bytes]:
    """Perform an HTTP GET using ``urllib`` and return ``(status, body)``.

    HTTP error responses are not raised; they are returned as their status
    code together with the error body so providers can surface them. Network
    level failures are converted into :class:`ProviderError`.

    Args:
        url: The full URL to request.

    Returns:
        A ``(status_code, body_bytes)`` tuple.

    Raises:
        ProviderError: If the request cannot be completed (DNS, connection,
            timeout).
    """

    request = urllib.request.Request(url, headers={"User-Agent": "tickstore/0.1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as error:
        return int(error.code), error.read()
    except (urllib.error.URLError, OSError) as error:
        raise ProviderError(f"request failed for {url}: {error}") from error


class BaseProvider(abc.ABC):
    """Abstract base class for market data providers.

    A provider owns a ``transport`` hook so a downstream caller can reroute
    every request, typically to recorded fixtures during tests.

    Attributes:
        name: Short provider identifier used for CLI and diagnostics.
        base_url: Root URL for the public API.
        intervals: Mapping of tickstore interval names to provider intervals.
        transport: Injected request callable.
    """

    name: str = "base"
    base_url: str = ""
    intervals: dict = {}

    def __init__(self, transport: Optional[Transport] = None) -> None:
        """Initialize the provider with an optional custom transport.

        Args:
            transport: Callable ``(url) -> (status, body_bytes)``. Defaults to
                :func:`default_transport` which performs a real HTTP request.
        """

        self.transport: Transport = transport or default_transport

    @abc.abstractmethod
    def fetch(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start: Optional[StartValue] = None,
        **kwargs: object,
    ) -> List[Candle]:
        """Fetch candles from the provider.

        Args:
            symbol: Market symbol (for example ``BTCUSDT`` or ``MSFT``).
            interval: tickstore interval name (for example ``1h``, ``1d``).
            limit: Maximum number of candles to request.
            start: Optional start time (epoch ms or ISO-8601 string).

        Returns:
            A list of candles ordered by ascending timestamp.
        """

        raise NotImplementedError

    def get(self, url: str) -> bytes:
        """Fetch a URL and guarantee a successful HTTP response.

        Args:
            url: The URL to request.

        Returns:
            The response body bytes.

        Raises:
            ProviderError: When the transport returns a non-200 status.
        """

        status, body = self.transport(url)
        if status != 200:
            raise ProviderError(
                f"{self.name}: HTTP {status} for {url}"
            )
        return body


class BinanceProvider(BaseProvider):
    """Public spot market data from Binance.

    ``.../api/v3/klines`` returns each candle as a 12-field JSON array. Row
    indices follow the Binance documentation: 0 ``openTime``, 1 ``open``,
    2 ``high``, 3 ``low``, 4 ``close``, 5 ``volume``, 6 ``closeTime``,
    7 ``quoteAssetVolume``, 8 ``numberOfTrades``, 9 ``takerBuyBase``,
    10 ``takerBuyQuote``, 11 ``ignore``. :meth:`decode_kline` turns a row
    into a fully typed 12-tuple and ``fetch`` builds candles from the first
    six fields.
    """

    name = "binance"
    base_url = "https://api.binance.com"
    intervals = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}

    @staticmethod
    def decode_kline(row: List[object]) -> Tuple[object, ...]:
        """Type a raw 12-field Binance kline row into a tuple.

        Args:
            row: Raw kline list from the API.

        Returns:
            A 12-tuple with ints for timestamps, trade counts and the ignore
            field, floats for every price/volume field.

        Raises:
            ProviderError: If the row is shorter than 12 fields or cannot be
                converted.
        """

        if not isinstance(row, (list, tuple)) or len(row) < 12:
            raise ProviderError(f"binance: malformed kline row {row!r}")
        try:
            return (
                int(row[0]),
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                float(row[5]),
                int(row[6]),
                float(row[7]),
                int(row[8]),
                float(row[9]),
                float(row[10]),
                int(row[11]),
            )
        except (TypeError, ValueError) as error:
            raise ProviderError(
                f"binance: unparseable kline row {row!r}"
            ) from error

    def fetch(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start: Optional[StartValue] = None,
        end: Optional[StartValue] = None,
        **kwargs: object,
    ) -> List[Candle]:
        """Fetch spot klines from Binance.

        Args:
            symbol: Market symbol, uppercased automatically.
            interval: One of 1m/5m/15m/1h/4h/1d.
            limit: Maximum candles per request (Binance caps at 1000).
            start: Optional ``startTime``, ISO-8601 or epoch milliseconds.
            end: Optional ``endTime``, ISO-8601 or epoch milliseconds.

        Returns:
            Candles ordered by ascending ``openTime``.

        Raises:
            ProviderError: For unsupported intervals, HTTP failures, or
                malformed payloads.
        """

        if interval not in self.intervals:
            raise ProviderError(
                f"binance: unsupported interval {interval!r}"
            )
        params = {
            "symbol": str(symbol).upper(),
            "interval": self.intervals[interval],
            "limit": str(int(limit)),
        }
        if start is not None:
            params["startTime"] = str(to_epoch_ms(start))
        if end is not None:
            params["endTime"] = str(to_epoch_ms(end))
        query = urllib.parse.urlencode(params)
        url = f"{self.base_url}/api/v3/klines?{query}"
        body = self.get(url)
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            raise ProviderError(
                "binance: response is not valid JSON"
            ) from error
        if not isinstance(data, list):
            raise ProviderError(
                "binance: expected a JSON list of kline rows"
            )
        return [
            self._to_candle(self.decode_kline(row))
            for row in data
        ]

    @staticmethod
    def _to_candle(fields: Tuple[object, ...]) -> Candle:
        """Build a Candle from the first six typed kline fields.

        Args:
            fields: A 12-tuple produced by :meth:`decode_kline`.

        Returns:
            The corresponding candle.
        """

        return Candle(
            ts=int(fields[0]),
            open=float(fields[1]),
            high=float(fields[2]),
            low=float(fields[3]),
            close=float(fields[4]),
            volume=float(fields[5]),
        )


class YahooProvider(BaseProvider):
    """Free market data from Yahoo Finance.

    Uses the unauthenticated ``v8/finance/chart`` endpoint. Timestamps are
    epoch seconds in the payload and are scaled to milliseconds. Rows with any
    null OHLCV value or a null timestamp are dropped (Yahoo frequently leaves
    gaps for illiquid sessions).
    """

    name = "yahoo"
    base_url = "https://query1.finance.yahoo.com"
    intervals = {
        "1m": "1m",
        "2m": "2m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "1d": "1d",
        "1wk": "1wk",
    }

    def fetch(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start: Optional[StartValue] = None,
        range: Optional[str] = None,
        **kwargs: object,
    ) -> List[Candle]:
        """Fetch chart data from Yahoo Finance.

        When ``start`` is given the request uses ``period1`` (epoch seconds);
        otherwise a ``range`` is used and defaults to ``5d``.

        Args:
            symbol: Ticker, for example ``MSFT`` or ``BTC-USD``.
            interval: One of 1m/2m/5m/15m/30m/1h/1d/1wk.
            limit: Accepted for interface compatibility (Yahoo honours range
                instead of a raw count).
            start: Optional start time; drives the ``period1`` parameter.
            range: Optional Yahoo range such as ``5d``, ``1mo`` or ``ytd``.

        Returns:
            Candles ordered by ascending timestamp with null rows dropped.

        Raises:
            ProviderError: For unsupported intervals, HTTP failures, or
                unusable payloads.
        """

        if interval not in self.intervals:
            raise ProviderError(
                f"yahoo: unsupported interval {interval!r}"
            )
        params = {"interval": self.intervals[interval]}
        if start is not None:
            params["period1"] = str(to_epoch_seconds(start))
        else:
            params["range"] = range or "5d"
        query = urllib.parse.urlencode(params)
        url = (
            f"{self.base_url}/v8/finance/chart/"
            f"{urllib.parse.quote(str(symbol))}?{query}"
        )
        body = self.get(url)
        return self._parse(body)

    def _parse(self, body: bytes) -> List[Candle]:
        """Decode a Yahoo chart JSON payload into candles.

        Args:
            body: Raw response bytes.

        Returns:
            Candles with null-bearing rows removed.

        Raises:
            ProviderError: When the chart reports an error, has no result, or
                is missing the quote arrays.
        """

        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            raise ProviderError(
                "yahoo: response is not valid JSON"
            ) from error
        chart = payload.get("chart") if isinstance(payload, dict) else None
        if not isinstance(chart, dict):
            raise ProviderError("yahoo: missing chart container")
        if chart.get("error"):
            raise ProviderError(f"yahoo: api error: {chart['error']}")
        result = chart.get("result") or []
        if not result:
            raise ProviderError("yahoo: empty chart result")
        entry = result[0]
        if not isinstance(entry, dict):
            raise ProviderError("yahoo: malformed chart result")
        timestamps = entry.get("timestamp") or []
        indicators = entry.get("indicators") if isinstance(entry.get("indicators"), dict) else {}
        quote = indicators.get("quote") or []
        if not quote or not isinstance(quote[0], dict):
            raise ProviderError("yahoo: missing indicators.quote data")
        fields = quote[0]
        opens = fields.get("open") or []
        highs = fields.get("high") or []
        lows = fields.get("low") or []
        closes = fields.get("close") or []
        volumes = fields.get("volume") or []
        expected = max(
            len(timestamps),
            len(opens),
            len(highs),
            len(lows),
            len(closes),
            len(volumes),
        )
        candles: List[Candle] = []
        for index in range(expected):
            timestamp = timestamps[index] if index < len(timestamps) else None
            value_index = index
            values = []
            for column in (opens, highs, lows, closes, volumes):
                values.append(column[value_index] if value_index < len(column) else None)
            if timestamp is None or any(value is None for value in values):
                continue
            try:
                candles.append(
                    Candle(
                        ts=int(float(timestamp) * 1000),
                        open=float(values[0]),
                        high=float(values[1]),
                        low=float(values[2]),
                        close=float(values[3]),
                        volume=float(values[4]),
                    )
                )
            except (TypeError, ValueError) as error:
                raise ProviderError(
                    f"yahoo: unparseable value at row {index}"
                ) from error
        return candles