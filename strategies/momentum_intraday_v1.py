from __future__ import annotations

from statistics import mean
from typing import Any


def calculate_sma(values: list[float], period: int) -> float:
    if len(values) < period:
        return 0.0
    return float(mean(values[-period:]))


def calculate_roc(values: list[float], period: int) -> float:
    if len(values) <= period:
        return 0.0
    base = float(values[-period - 1])
    if base == 0:
        return 0.0
    return ((float(values[-1]) - base) / base) * 100.0


def calculate_rsi(values: list[float], period: int) -> float:
    if len(values) <= period:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for i in range(-period, 0):
        delta = float(values[i]) - float(values[i - 1])
        if delta >= 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(delta))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class MomentumIntradayV1:
    strategy_id = "momentum_intraday_v1"
    strategy_unit = "BALANCED_INTRADAY_MOMENTUM"
    take_profit_pct = 0.012
    stop_loss_pct = 0.006

    def build_market_data(self, closes: list[float], volumes: list[float]) -> dict[str, float]:
        volume_now = float(volumes[-1]) if volumes else 0.0
        volume_avg = float(mean(volumes[-5:])) if len(volumes) >= 5 else volume_now
        return {
            "close": float(closes[-1]) if closes else 0.0,
            "roc_10": calculate_roc(closes, 10),
            "rsi_14": calculate_rsi(closes, 14),
            "sma_20": calculate_sma(closes, 20),
            "volume": volume_now,
            "volume_avg_5": volume_avg,
            "volume_ratio": (volume_now / volume_avg) if volume_avg > 0 else 0.0,
        }

    def generate_signal(self, data: dict[str, Any]) -> str:
        roc = float(data.get("roc_10", 0.0))
        rsi = float(data.get("rsi_14", 50.0))
        price = float(data.get("close", 0.0))
        sma = float(data.get("sma_20", 0.0))
        volume_ratio = float(data.get("volume_ratio", 0.0))

        # Relax the intraday trigger slightly so valid momentum setups do not
        # collapse into HOLD during normal testnet noise.
        # Enhanced volume filter for graph-based signals (0.85 -> 2.0)
        if roc > 0.35 and 55.0 < rsi < 82.0 and price > sma and volume_ratio >= 2.0:
            return "LONG"
        if roc < -0.3 and rsi < 45.0 and price < sma:
            return "SHORT"
        return "HOLD"

    def evaluate(self, symbol: str, closes: list[float], volumes: list[float]) -> dict[str, Any]:
        market_data = self.build_market_data(closes, volumes)
        signal = self.generate_signal(market_data)
        side_score = abs(float(market_data["roc_10"])) / 2.0
        return {
            "symbol": symbol,
            "strategy_id": self.strategy_id,
            "strategy_unit": self.strategy_unit,
            "signal": signal,
            "signal_score": round(side_score, 6),
            "take_profit_pct": self.take_profit_pct,
            "stop_loss_pct": self.stop_loss_pct,
            **{k: round(float(v), 6) for k, v in market_data.items()},
        }
