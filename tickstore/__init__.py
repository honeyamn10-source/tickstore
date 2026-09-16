"""Dependency-free OHLCV market data for self-hosted trading research."""

from .candle import Candle, candle_issues, series, validate
from .indicators import atr, bollinger_bands, ema, rsi, sma, vwap
from .providers import (
    BaseProvider,
    BinanceProvider,
    ProviderError,
    YahooProvider,
    default_transport,
    to_epoch_ms,
)
from .resample import BUCKETS, ResampleError, resample
from .store import Store

__version__ = "0.1.0"

__all__ = [
    "BUCKETS",
    "BaseProvider",
    "BinanceProvider",
    "Candle",
    "ProviderError",
    "ResampleError",
    "Store",
    "YahooProvider",
    "atr",
    "bollinger_bands",
    "candle_issues",
    "default_transport",
    "ema",
    "resample",
    "rsi",
    "series",
    "sma",
    "to_epoch_ms",
    "validate",
    "vwap",
]