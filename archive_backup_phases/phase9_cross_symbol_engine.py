from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path
from statistics import mean
from typing import Any

KST = timezone(timedelta(hours=9))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
        except Exception:
            continue
    return rows


def ff(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def corr(x: list[float], y: list[float]) -> float:
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    x = x[-n:]
    y = y[-n:]
    mx = mean(x)
    my = mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    denx = sum((a - mx) ** 2 for a in x) ** 0.5
    deny = sum((b - my) ** 2 for b in y) ** 0.5
    if denx < 1e-9 or deny < 1e-9:
        return 0.0
    return num / (denx * deny)


def build_cross_symbol(trades: list[dict[str, Any]]) -> dict[str, Any]:
    pnl_by_symbol: dict[str, list[float]] = defaultdict(list)
    hold_by_symbol: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        sym = str(t.get("symbol", "")).strip()
        if not sym:
            continue
        pnl_by_symbol[sym].append(ff(t.get("profit_loss")))
        hold_by_symbol[sym].append(ff(t.get("holding_time_sec")))

    opportunities: list[dict[str, Any]] = []
    syms = sorted(pnl_by_symbol.keys())
    for a, b in combinations(syms, 2):
        c = corr(pnl_by_symbol[a], pnl_by_symbol[b])
        hold_spread = abs(mean(hold_by_symbol[a]) - mean(hold_by_symbol[b])) if hold_by_symbol[a] and hold_by_symbol[b] else 0.0
        signal = "VOLATILITY_PAIR_TRADING" if abs(c) < 0.15 else ("MOMENTUM_SPREAD" if c < -0.2 else "CORRELATION_FOLLOW")
        opportunities.append(
            {
                "pair": f"{a}_{b}",
                "correlation": round(c, 6),
                "holding_time_spread_sec": round(hold_spread, 3),
                "opportunity_type": signal,
                "confidence": round(max(0.0, 1.0 - abs(c - 0.1)), 6),
            }
        )

    opportunities.sort(key=lambda x: x["confidence"], reverse=True)
    top = opportunities[:20]

    named = {
        "BTC_ETH_CORRELATION": next((x for x in top if x["pair"] in ("BTCUSDT_ETHUSDT", "ETHUSDT_BTCUSDT")), None),
        "BTC_SOL_MOMENTUM_SPREAD": next((x for x in top if x["pair"] in ("BTCUSDT_SOLUSDT", "SOLUSDT_BTCUSDT")), None),
        "VOLATILITY_PAIR_TRADING": next((x for x in top if x["opportunity_type"] == "VOLATILITY_PAIR_TRADING"), None),
    }

    return {
        "generated_at_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "symbol_count": len(syms),
        "pair_count": len(opportunities),
        "top_opportunities": top,
        "named_insights": named,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE9 Cross Symbol Intelligence")
    parser.add_argument("--trade-performance-jsonl", required=True)
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args()

    trades = read_jsonl(Path(args.trade_performance_jsonl))
    result = build_cross_symbol(trades)
    Path(args.out_json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("PHASE9_CROSS_SYMBOL_STATUS=COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
