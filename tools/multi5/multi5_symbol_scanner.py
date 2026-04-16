from __future__ import annotations

import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from strategies.momentum_intraday_v1 import MomentumIntradayV1

try:
    from .multi5_config import (
        DYNAMIC_UNIVERSE_CACHE_SEC,
        DYNAMIC_UNIVERSE_LIMIT,
        DYNAMIC_UNIVERSE_MIN_QUOTE_VOLUME,
        DYNAMIC_UNIVERSE_QUOTE_ASSET,
        ENABLE_DYNAMIC_SYMBOL_UNIVERSE,
        SYMBOL_UNIVERSE,
    )
except ImportError:
    from multi5_config import (
        DYNAMIC_UNIVERSE_CACHE_SEC,
        DYNAMIC_UNIVERSE_LIMIT,
        DYNAMIC_UNIVERSE_MIN_QUOTE_VOLUME,
        DYNAMIC_UNIVERSE_QUOTE_ASSET,
        ENABLE_DYNAMIC_SYMBOL_UNIVERSE,
        SYMBOL_UNIVERSE,
    )

BINANCE_TESTNET_MARKET_URL = "https://demo-fapi.binance.com/fapi/v1/klines"
BINANCE_TESTNET_EXCHANGE_INFO_URL = "https://demo-fapi.binance.com/fapi/v1/exchangeInfo"
BINANCE_TESTNET_TICKER_24H_URL = "https://demo-fapi.binance.com/fapi/v1/ticker/24hr"
MOMENTUM_INTRADAY = MomentumIntradayV1()
_UNIVERSE_CACHE: dict[str, Any] = {
    "symbols": list(SYMBOL_UNIVERSE),
    "expires_at": datetime.now(timezone.utc),
}
KST = timezone(timedelta(hours=9))
ACTIVE_WINDOW_START = time(9, 30)
ACTIVE_WINDOW_END = time(11, 30)
SELECTIVE_WINDOW_START = time(12, 0)
SELECTIVE_WINDOW_END = time(12, 30)
REACTIVE_STRATEGY_ID = "reactive_reversion_v1"
REACTIVE_STRATEGY_UNIT = "FACT_REACTIVE_REVERSION"
REACTIVE_TP_PCT = 0.010
REACTIVE_SL_PCT = 0.006


def calculate_edge_score(prices: list[float]) -> float:
    if len(prices) < 20:
        return 0.0
    window = prices[-30:] if len(prices) >= 30 else prices
    mu = mean(window)
    sigma = pstdev(window) if len(window) > 1 else 0.0
    if sigma <= 0:
        return 0.0
    z = (window[-1] - mu) / sigma
    return max(0.0, min(abs(z) / 2.0, 1.8))


def _analyze_regime(prices: list[float]) -> dict[str, float | str]:
    if len(prices) < 30:
        return {"regime": "warmup", "trend_strength": 0.0, "volatility": 0.0}
    ma_short = mean(prices[-10:])
    ma_long = mean(prices[-30:])
    trend_strength = abs((ma_short - ma_long) / ma_long) if ma_long else 0.0
    returns: list[float] = []
    for i in range(1, len(prices)):
        prev = prices[i - 1]
        if prev > 0:
            returns.append((prices[i] - prev) / prev)
    vol = pstdev(returns[-20:]) if len(returns) >= 20 else 0.0
    regime = "range"
    if vol > 0.0015:
        regime = "high_vol"
    elif trend_strength > 0.0008:
        regime = "trend"
    return {
        "regime": regime,
        "trend_strength": round(float(trend_strength), 6),
        "volatility": round(float(vol), 6),
    }


def _classify_regime(prices: list[float]) -> str:
    return str(_analyze_regime(prices).get("regime", "range"))


def _kst_now() -> datetime:
    return datetime.now(KST)


def _resolve_time_window() -> str:
    now_time = _kst_now().time()
    if ACTIVE_WINDOW_START <= now_time <= ACTIVE_WINDOW_END:
        return "ACTIVE"
    if SELECTIVE_WINDOW_START <= now_time <= SELECTIVE_WINDOW_END:
        return "SELECTIVE"
    return "BLOCKED"


def _shock_move_pct(closes: list[float], minutes: int) -> float:
    if len(closes) <= minutes:
        return 0.0
    base = float(closes[-minutes - 1])
    if base <= 0:
        return 0.0
    return ((float(closes[-1]) - base) / base) * 100.0


def _build_reactive_signal(
    *,
    symbol: str,
    closes_1m: list[float],
    volumes_1m: list[float],
    closes_5m: list[float],
    momentum_eval: dict[str, Any],
) -> dict[str, Any]:
    market_data = MOMENTUM_INTRADAY.build_market_data(closes_1m, volumes_1m)
    regime_obs = _analyze_regime(closes_5m)
    regime = str(regime_obs.get("regime", "range"))
    trend_strength = float(regime_obs.get("trend_strength", 0.0) or 0.0)
    volatility = float(regime_obs.get("volatility", 0.0) or 0.0)
    window_mode = _resolve_time_window()

    drop_candidates = [_shock_move_pct(closes_1m, 1), _shock_move_pct(closes_1m, 2), _shock_move_pct(closes_1m, 3)]
    rise_candidates = list(drop_candidates)
    min_move = min(drop_candidates) if drop_candidates else 0.0
    max_move = max(rise_candidates) if rise_candidates else 0.0

    latest_volume = float(volumes_1m[-1]) if volumes_1m else 0.0
    avg_volume = float(mean(volumes_1m[-20:])) if len(volumes_1m) >= 20 else (float(mean(volumes_1m)) if volumes_1m else 0.0)
    volume_ratio = (latest_volume / avg_volume) if avg_volume > 0 else 0.0

    is_strong_trend = trend_strength >= 0.0016 and regime == "trend"
    allow_reactive = regime in {"range", "high_vol"} and not is_strong_trend and window_mode != "BLOCKED"

    shock_threshold = 2.0
    volume_threshold = 1.6
    score_multiplier = 1.0
    if window_mode == "SELECTIVE":
        shock_threshold = 2.3
        volume_threshold = 1.9
        score_multiplier = 0.85

    signal = "HOLD"
    signal_source = "reactive_filter_block"
    signal_score = 0.0
    expected_edge = 0.0
    trigger_direction = ""

    if allow_reactive:
        if min_move <= -shock_threshold and volume_ratio >= volume_threshold:
            signal = "LONG"
            trigger_direction = "DROP_REVERSION"
        elif max_move >= shock_threshold and volume_ratio >= volume_threshold:
            signal = "SHORT"
            trigger_direction = "SPIKE_REVERSION"

    if signal in {"LONG", "SHORT"}:
        shock_score = max(abs(min_move), abs(max_move)) / max(shock_threshold, 0.1)
        raw_score = min(2.0, max(0.55, shock_score * 0.55 + volume_ratio * 0.35))
        signal_score = round(raw_score * score_multiplier, 6)
        expected_edge = round(signal_score, 6)
        signal_source = "reactive_reversion"

    return {
        "symbol": symbol,
        "strategy_id": REACTIVE_STRATEGY_ID,
        "strategy_unit": REACTIVE_STRATEGY_UNIT,
        "signal": signal,
        "signal_score": signal_score,
        "expected_edge": expected_edge,
        "take_profit_pct": REACTIVE_TP_PCT,
        "stop_loss_pct": REACTIVE_SL_PCT,
        "regime": regime,
        "trend_strength": trend_strength,
        "volatility": volatility,
        "time_window_mode": window_mode,
        "reactive_signal_source": signal_source,
        "trigger_direction": trigger_direction,
        "shock_move_1m_pct": round(_shock_move_pct(closes_1m, 1), 6),
        "shock_move_2m_pct": round(_shock_move_pct(closes_1m, 2), 6),
        "shock_move_3m_pct": round(_shock_move_pct(closes_1m, 3), 6),
        "close": float(market_data.get("close", 0.0) or 0.0),
        "roc_10": float(market_data.get("roc_10", 0.0) or 0.0),
        "rsi_14": float(market_data.get("rsi_14", 50.0) or 50.0),
        "sma_20": float(market_data.get("sma_20", 0.0) or 0.0),
        "volume_ratio": round(volume_ratio, 6),
        "momentum_signal": str(momentum_eval.get("signal", "HOLD")),
        "momentum_score": float(momentum_eval.get("signal_score", 0.0) or 0.0),
    }


def _infer_exploratory_signal(
    *,
    edge_score: float,
    regime: str,
    roc: float,
    rsi: float,
    price: float,
    sma: float,
    volume_ratio: float,
) -> str:
    if edge_score < 0.45:
        return "HOLD"

    long_ok = roc >= 0.18 and price > sma and rsi >= 52.0 and volume_ratio >= 0.75
    short_ok = roc <= -0.18 and price < sma and rsi <= 48.0 and volume_ratio >= 0.75

    if regime == "range":
        if edge_score < 0.75:
            return "HOLD"
        if long_ok and rsi <= 68.0:
            return "LONG"
        if short_ok and rsi >= 32.0:
            return "SHORT"
        return "HOLD"

    if long_ok:
        return "LONG"
    if short_ok:
        return "SHORT"
    return "HOLD"


def build_symbol_state(
    symbol: str,
    closes_1m: list[float],
    volumes_1m: list[float],
    closes_5m: list[float],
    volumes_5m: list[float],
) -> dict[str, Any]:
    edge_score = calculate_edge_score(closes_1m)
    returns: list[float] = []
    for i in range(1, len(closes_1m)):
        prev = closes_1m[i - 1]
        if prev > 0:
            returns.append((closes_1m[i] - prev) / prev)
    volatility = pstdev(returns[-20:]) if len(returns) >= 20 else 0.0
    regime_obs = _analyze_regime(closes_5m)
    regime = str(regime_obs.get("regime", "range"))
    strategy_eval = MOMENTUM_INTRADAY.evaluate(symbol, closes_1m, volumes_1m)
    reactive_eval = _build_reactive_signal(
        symbol=symbol,
        closes_1m=closes_1m,
        volumes_1m=volumes_1m,
        closes_5m=closes_5m,
        momentum_eval=strategy_eval,
    )
    signal = str(reactive_eval.get("signal", "HOLD"))
    strategy_score = float(reactive_eval.get("signal_score", 0.0) or 0.0)
    signal_source = str(reactive_eval.get("reactive_signal_source", "reactive_filter_block"))
    boosted_edge = edge_score + (strategy_score if signal in {"LONG", "SHORT"} else 0.0)
    return {
        "symbol": symbol,
        "edge_score": round(boosted_edge, 6),
        "base_edge_score": round(edge_score, 6),
        "volatility": round(float(volatility), 6),
        "regime": regime,
        "trend_strength": float(reactive_eval.get("trend_strength", regime_obs.get("trend_strength", 0.0)) or 0.0),
        "time_window_mode": reactive_eval.get("time_window_mode", "BLOCKED"),
        "strategy_id": reactive_eval.get("strategy_id"),
        "strategy_unit": reactive_eval.get("strategy_unit"),
        "strategy_signal": signal,
        "strategy_signal_source": signal_source,
        "strategy_signal_score": round(strategy_score, 6),
        "roc_10": reactive_eval.get("roc_10", 0.0),
        "rsi_14": reactive_eval.get("rsi_14", 50.0),
        "sma_20": reactive_eval.get("sma_20", 0.0),
        "close": reactive_eval.get("close", 0.0),
        "volume_ratio": reactive_eval.get("volume_ratio", 0.0),
        "take_profit_pct": reactive_eval.get("take_profit_pct", REACTIVE_TP_PCT),
        "stop_loss_pct": reactive_eval.get("stop_loss_pct", REACTIVE_SL_PCT),
        "shock_move_1m_pct": reactive_eval.get("shock_move_1m_pct", 0.0),
        "shock_move_2m_pct": reactive_eval.get("shock_move_2m_pct", 0.0),
        "shock_move_3m_pct": reactive_eval.get("shock_move_3m_pct", 0.0),
        "trigger_direction": reactive_eval.get("trigger_direction", ""),
        "momentum_signal": reactive_eval.get("momentum_signal", "HOLD"),
        "momentum_score": reactive_eval.get("momentum_score", 0.0),
    }


def _fetch_symbol_klines(symbol: str, interval: str = "5m", limit: int = 60) -> tuple[list[float], list[float]]:
    response = requests.get(
        BINANCE_TESTNET_MARKET_URL,
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=8,
    )
    response.raise_for_status()
    rows = response.json()
    closes: list[float] = []
    volumes: list[float] = []
    for row in rows:
        closes.append(float(row[4]))
        volumes.append(float(row[5]))
    return closes, volumes


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fetch_dynamic_symbol_universe() -> list[str]:
    exchange_info = requests.get(BINANCE_TESTNET_EXCHANGE_INFO_URL, timeout=8)
    exchange_info.raise_for_status()
    ticker_24h = requests.get(BINANCE_TESTNET_TICKER_24H_URL, timeout=8)
    ticker_24h.raise_for_status()

    ticker_rows = ticker_24h.json()
    quote_volume_by_symbol: dict[str, float] = {}
    for row in ticker_rows:
        symbol = str(row.get("symbol", "")).upper().strip()
        if not symbol:
            continue
        try:
            quote_volume_by_symbol[symbol] = float(row.get("quoteVolume", 0.0) or 0.0)
        except Exception:
            quote_volume_by_symbol[symbol] = 0.0

    dynamic_symbols: list[tuple[str, float]] = []
    for row in exchange_info.json().get("symbols", []):
        symbol = str(row.get("symbol", "")).upper().strip()
        if not symbol:
            continue
        if str(row.get("status", "")).upper() != "TRADING":
            continue
        if str(row.get("quoteAsset", "")).upper() != DYNAMIC_UNIVERSE_QUOTE_ASSET:
            continue
        if str(row.get("contractType", "")).upper() != "PERPETUAL":
            continue
        if str(row.get("underlyingType", "")).upper() not in {"COIN", "INDEX", "STOCK", "COMMODITY"}:
            # Testnet occasionally returns mixed instruments; keep standard perpetual listings.
            pass
        quote_volume = quote_volume_by_symbol.get(symbol, 0.0)
        if quote_volume < DYNAMIC_UNIVERSE_MIN_QUOTE_VOLUME:
            continue
        dynamic_symbols.append((symbol, quote_volume))

    dynamic_symbols.sort(key=lambda item: item[1], reverse=True)
    resolved = [symbol for symbol, _ in dynamic_symbols[:DYNAMIC_UNIVERSE_LIMIT]]
    return resolved or list(SYMBOL_UNIVERSE)


def resolve_symbol_universe(symbols: list[str] | None = None) -> list[str]:
    if symbols:
        return symbols
    if not ENABLE_DYNAMIC_SYMBOL_UNIVERSE:
        return list(SYMBOL_UNIVERSE)

    now = _utc_now()
    cached_symbols = _UNIVERSE_CACHE.get("symbols") or []
    expires_at = _UNIVERSE_CACHE.get("expires_at")
    if isinstance(expires_at, datetime) and now < expires_at and cached_symbols:
        return list(cached_symbols)

    try:
        resolved = _fetch_dynamic_symbol_universe()
        _UNIVERSE_CACHE["symbols"] = list(resolved)
        _UNIVERSE_CACHE["expires_at"] = now + timedelta(seconds=max(30, DYNAMIC_UNIVERSE_CACHE_SEC))
        return list(resolved)
    except Exception:
        if cached_symbols:
            return list(cached_symbols)
        return list(SYMBOL_UNIVERSE)


def fetch_universe_data(symbols: list[str] | None = None) -> list[dict[str, Any]]:
    universe = resolve_symbol_universe(symbols)
    states: list[dict[str, Any]] = []
    for symbol in universe:
        try:
            closes_1m, volumes_1m = _fetch_symbol_klines(symbol, interval="1m", limit=90)
            closes_5m, volumes_5m = _fetch_symbol_klines(symbol, interval="5m", limit=60)
            states.append(build_symbol_state(symbol, closes_1m, volumes_1m, closes_5m, volumes_5m))
        except Exception:
            states.append(
                {
                    "symbol": symbol,
                    "edge_score": 0.0,
                    "base_edge_score": 0.0,
                    "volatility": 0.0,
                    "regime": "error",
                    "strategy_id": MOMENTUM_INTRADAY.strategy_id,
                    "strategy_unit": REACTIVE_STRATEGY_UNIT,
                    "strategy_signal": "HOLD",
                    "strategy_signal_score": 0.0,
                    "roc_10": 0.0,
                    "rsi_14": 50.0,
                    "sma_20": 0.0,
                    "close": 0.0,
                    "volume_ratio": 0.0,
                    "take_profit_pct": MOMENTUM_INTRADAY.take_profit_pct,
                    "stop_loss_pct": MOMENTUM_INTRADAY.stop_loss_pct,
                }
            )
    return states
