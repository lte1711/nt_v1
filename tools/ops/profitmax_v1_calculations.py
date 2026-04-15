from __future__ import annotations

import math
from typing import Any


def build_allocation_top_from_snapshot(
    portfolio_allocation: dict[str, Any],
    limit: int = 8,
) -> list[dict[str, Any]]:
    allocation_weights = portfolio_allocation.get("weights") or {}
    allocation_scores = portfolio_allocation.get("raw_scores") or {}
    allocation_top: list[dict[str, Any]] = []
    if not isinstance(allocation_weights, dict):
        return allocation_top
    sorted_weights = sorted(
        (
            (str(symbol), float(weight or 0.0))
            for symbol, weight in allocation_weights.items()
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    for symbol, weight in sorted_weights[: max(1, int(limit or 8))]:
        allocation_top.append(
            {
                "symbol": symbol,
                "weight": round(weight, 6),
                "score": round(float(allocation_scores.get(symbol, 0.0) or 0.0), 6),
            }
        )
    return allocation_top


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def calculate_long_short_ratio(positions: list[dict[str, Any]]) -> float:
    long_count = 0
    short_count = 0
    for row in positions:
        side = str(row.get("side", "")).upper().strip()
        if side == "LONG":
            long_count += 1
        elif side == "SHORT":
            short_count += 1
    total = long_count + short_count
    if total == 0:
        return 0.5
    return long_count / total


def short_bias_guard(
    positions: list[dict[str, Any]],
    signal_side: str,
    *,
    enabled: bool,
    max_short_positions: int,
    min_long_ratio: float,
) -> tuple[bool, dict[str, Any]]:
    signal_side = str(signal_side).upper().strip()
    normalized_side = "LONG" if signal_side == "BUY" else "SHORT" if signal_side == "SELL" else signal_side
    long_count = sum(1 for row in positions if str(row.get("side", "")).upper().strip() == "LONG")
    short_count = sum(1 for row in positions if str(row.get("side", "")).upper().strip() == "SHORT")
    ratio = calculate_long_short_ratio(positions)
    state = {
        "signal_side": normalized_side,
        "long_count": long_count,
        "short_count": short_count,
        "long_short_ratio": ratio,
        "max_short_positions": max_short_positions,
        "min_long_ratio": min_long_ratio,
        "blocked_reason": "",
    }
    if not enabled:
        return True, state
    if normalized_side != "SHORT":
        return True, state
    if short_count >= max_short_positions:
        state["blocked_reason"] = "short_limit"
        return False, state
    if ratio < min_long_ratio:
        state["blocked_reason"] = "long_ratio_floor"
        return False, state
    return True, state


def calculate_portfolio_exposure(positions: list[dict[str, Any]]) -> dict[str, float]:
    total_notional = 0.0
    long_exposure = 0.0
    short_exposure = 0.0
    for row in positions:
        try:
            qty = abs(float(row.get("qty", 0.0) or 0.0))
        except Exception:
            qty = 0.0
        try:
            price = float(row.get("price", 0.0) or 0.0)
        except Exception:
            price = 0.0
        notional = abs(qty * price)
        total_notional += notional
        side = str(row.get("side", "")).upper().strip()
        if side == "LONG":
            long_exposure += notional
        elif side == "SHORT":
            short_exposure += notional
    return {
        "total": total_notional,
        "long": long_exposure,
        "short": short_exposure,
    }


def calculate_portfolio_metrics(trades: list[dict[str, Any]]) -> dict[str, float]:
    total_trades = len(trades)
    wins = sum(1 for trade in trades if float(trade.get("pnl", 0.0)) > 0)
    losses = sum(1 for trade in trades if float(trade.get("pnl", 0.0)) <= 0)
    total_pnl = sum(float(trade.get("pnl", 0.0)) for trade in trades)
    win_values = [float(trade.get("pnl", 0.0)) for trade in trades if float(trade.get("pnl", 0.0)) > 0]
    loss_values = [float(trade.get("pnl", 0.0)) for trade in trades if float(trade.get("pnl", 0.0)) <= 0]
    avg_win = sum(win_values) / len(win_values) if win_values else 0.0
    avg_loss = sum(loss_values) / len(loss_values) if loss_values else 0.0
    win_rate = wins / total_trades if total_trades else 0.0

    running = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for trade in trades:
        running += float(trade.get("pnl", 0.0))
        peak = max(peak, running)
        max_drawdown = min(max_drawdown, running - peak)

    return {
        "total_trades": float(total_trades),
        "wins": float(wins),
        "losses": float(losses),
        "win_rate": float(win_rate),
        "total_pnl": float(total_pnl),
        "avg_win": float(avg_win),
        "avg_loss": float(avg_loss),
        "max_drawdown": float(abs(max_drawdown)),
    }


def calculate_atr_from_prices(prices: list[float], period: int = 14) -> float:
    if len(prices) < max(3, period + 1):
        return 0.0
    true_ranges: list[float] = []
    for idx in range(1, len(prices)):
        high = float(prices[idx])
        low = float(prices[idx])
        prev_close = float(prices[idx - 1])
        true_range = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(abs(true_range))
    if not true_ranges:
        return 0.0
    window = true_ranges[-period:]
    return float(sum(window) / len(window))


def calculate_market_regime(
    price_series: list[float],
    atr: float,
    ma_fast: float,
    ma_slow: float,
    *,
    trend_threshold: float,
    vol_high: float,
    vol_low: float,
) -> dict[str, float | str]:
    latest_price = float(price_series[-1]) if price_series else 0.0
    trend = ((ma_fast - ma_slow) / ma_slow) if ma_slow else 0.0
    volatility = (atr / latest_price) if latest_price else 0.0

    regime = "SIDEWAYS"
    if trend > trend_threshold:
        regime = "BULL_TREND"
    elif trend < -trend_threshold:
        regime = "BEAR_TREND"

    if volatility > vol_high:
        regime = "HIGH_VOLATILITY"
    elif volatility < vol_low and regime == "SIDEWAYS":
        regime = "LOW_VOLATILITY"

    return {
        "regime": regime,
        "trend": float(trend),
        "volatility": float(volatility),
        "atr": float(atr),
        "price": latest_price,
        "ma_fast": float(ma_fast),
        "ma_slow": float(ma_slow),
    }


def calculate_entry_quality_score(
    signal_score: float,
    portfolio_win_rate: float,
    portfolio_drawdown: float,
    open_position_count: int,
    max_open_positions: int,
    *,
    portfolio_total_trades: int = 0,
    total_pnl: float = 0.0,
    current_long_ratio: float = 0.5,
    current_short_ratio: float = 0.5,
    signal_side: str = "",
    win_rate_soft_limit: float = 0.35,  # Reduced from 0.45 to 0.35
    drawdown_soft_limit: float = 0.10,  # Increased from 0.05 to 0.10
) -> float:
    score = abs(float(signal_score))

    if portfolio_total_trades >= 5 and portfolio_win_rate < win_rate_soft_limit:
        score -= 0.05  # Reduced from 0.10 to 0.05
    if portfolio_drawdown > drawdown_soft_limit:
        score -= 0.08  # Reduced from 0.15 to 0.08
    if portfolio_total_trades >= 3 and total_pnl < 0:
        score -= 0.05

    load_ratio = open_position_count / max_open_positions if max_open_positions else 0.0
    if load_ratio >= 0.80:
        score -= 0.05

    normalized_side = str(signal_side).upper().strip()
    if normalized_side == "SELL" and current_short_ratio >= 0.70:
        score -= 0.05
    if normalized_side == "BUY" and current_long_ratio >= 0.70:
        score -= 0.05

    return float(score)


def calculate_strategy_quality(stats: dict[str, Any]) -> float:
    trades = int(stats.get("trades", 0) or 0)
    pnl = float(stats.get("pnl", 0.0) or 0.0)
    if trades < 10:
        return 0.5
    win_rate = float(stats.get("wins", 0) or 0) / trades if trades > 0 else 0.0
    score = 0.5 + (win_rate * 0.3) + (min(pnl, 100.0) / 1000.0)
    return float(score)


def calculate_strategy_allocation(stats: dict[str, Any]) -> float:
    trades = max(0, int(stats.get("trades", 0) or 0))
    pnl = float(stats.get("pnl", 0.0) or 0.0)
    wins = max(0, int(stats.get("wins", 0) or 0))
    losses = max(0, int(stats.get("losses", 0) or 0))
    win_rate = (wins / trades) if trades > 0 else 0.0
    loss_rate = (losses / trades) if trades > 0 else 0.0
    avg_pnl = (pnl / trades) if trades > 0 else 0.0
    drawdown = float(stats.get("drawdown", 0.0) or 0.0)
    trade_confidence = min(trades, 20) / 20.0
    pnl_signal = 0.5 + (0.5 * math.tanh(avg_pnl))
    drawdown_penalty = 1.0 / (1.0 + max(drawdown, 0.0))
    negative_pnl_penalty = 1.0 if pnl >= 0.0 else max(0.35, 1.0 - min(abs(pnl) * 0.08, 0.65))
    loss_penalty = max(0.35, 1.0 - max(0.0, loss_rate - 0.45) * 1.8)
    negative_avg_penalty = 1.0 if avg_pnl >= 0.0 else max(0.45, 1.0 - min(abs(avg_pnl) * 4.0, 0.55))
    score = (
        0.22
        + (win_rate * 0.38)
        + (pnl_signal * 0.18)
        + (trade_confidence * 0.08)
    ) * drawdown_penalty * negative_pnl_penalty * loss_penalty * negative_avg_penalty
    return float(max(score, 0.000001))


def normalize_allocations(
    strategy_scores: dict[str, float],
    *,
    min_weight: float,
    max_weight: float,
) -> dict[str, float]:
    if not strategy_scores:
        return {}

    names = list(strategy_scores.keys())
    symbol_count = len(names)
    safe_max_weight = max(0.0, float(max_weight))
    safe_min_weight = max(0.0, min(float(min_weight), safe_max_weight))
    feasible_min_weight = safe_min_weight
    feasible_max_weight = safe_max_weight

    if feasible_min_weight * symbol_count > 1.0:
        feasible_min_weight = 1.0 / symbol_count
    if feasible_max_weight * symbol_count < 1.0:
        feasible_max_weight = 1.0 / symbol_count

    raw_values = [float(strategy_scores[name]) for name in names]
    mean_score = sum(raw_values) / symbol_count
    variance = sum((value - mean_score) ** 2 for value in raw_values) / symbol_count
    std_score = math.sqrt(max(variance, 1e-12))
    temperature = 2.75
    exp_scores = {
        name: math.exp(
            max(
                min(((float(strategy_scores[name]) - mean_score) / std_score) * temperature, 50.0),
                -50.0,
            )
        )
        for name in names
    }
    total_exp = sum(exp_scores.values())
    if total_exp <= 0:
        exp_scores = {name: 1.0 for name in names}
        total_exp = float(symbol_count)

    baseline_total = feasible_min_weight * symbol_count
    remaining_budget = max(0.0, 1.0 - baseline_total)
    weights = {
        name: feasible_min_weight + (remaining_budget * (exp_scores[name] / total_exp))
        for name in names
    }

    uncapped = set(names)
    while uncapped:
        over_cap = {name for name in uncapped if weights[name] > feasible_max_weight}
        if not over_cap:
            break

        excess = 0.0
        for name in over_cap:
            excess += weights[name] - feasible_max_weight
            weights[name] = feasible_max_weight
        uncapped -= over_cap
        if excess <= 0 or not uncapped:
            break

        uncapped_total = sum(exp_scores[name] for name in uncapped)
        if uncapped_total <= 0:
            share = excess / len(uncapped)
            for name in uncapped:
                weights[name] += share
            continue
        for name in uncapped:
            weights[name] += excess * (exp_scores[name] / uncapped_total)

    total_weight = sum(weights.values())
    if total_weight > 0:
        weights = {name: float(weight / total_weight) for name, weight in weights.items()}
    return weights


def evaluate_global_risk(
    account_equity: float,
    peak_equity: float,
    consecutive_losses: int,
    *,
    max_account_drawdown: float,
    max_consecutive_loss: int,
    volatility: float = 0.0,
    max_volatility_threshold: float = 0.08,
    api_failures: int = 0,
    api_failure_limit: int = 3,
    engine_errors: int = 0,
    engine_error_limit: int = 3,
) -> tuple[bool, str | None, float]:
    peak = max(float(peak_equity), float(account_equity), 0.0)
    drawdown = ((peak - float(account_equity)) / peak) if peak > 0 else 0.0
    if drawdown >= max_account_drawdown:
        return True, "ACCOUNT_DRAWDOWN", drawdown
    if int(consecutive_losses) >= int(max_consecutive_loss):
        return True, "CONSECUTIVE_LOSS", drawdown
    if float(volatility) >= float(max_volatility_threshold):
        return True, "PORTFOLIO_VOLATILITY_SPIKE", drawdown
    if int(api_failures) >= int(api_failure_limit):
        return True, "API_FAILURE_LIMIT", drawdown
    if int(engine_errors) >= int(engine_error_limit):
        return True, "ENGINE_ERROR_LIMIT", drawdown
    return False, None, drawdown
