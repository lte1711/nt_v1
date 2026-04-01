from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
RND = random.Random(42)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


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


def eval_candidate(
    trades: list[dict[str, Any]],
    feature_snapshot: dict[str, Any],
    edge_threshold: float,
    regime_filters: list[str],
    max_symbol_active: int,
    position_size_model: str,
) -> dict[str, Any]:
    filtered = []
    for t in trades:
        edge = ff((t.get("entry_signal") or {}).get("expected_edge"))
        reg = str(t.get("market_regime", "")).lower()
        if edge < edge_threshold:
            continue
        if regime_filters and reg not in regime_filters:
            continue
        filtered.append(t)

    n = len(filtered)
    wins = [ff(t.get("profit_loss")) for t in filtered if ff(t.get("profit_loss")) > 0]
    losses = [ff(t.get("profit_loss")) for t in filtered if ff(t.get("profit_loss")) < 0]
    win_rate = (len(wins) / n) if n > 0 else 0.0
    gross_profit = sum(wins)
    gross_loss_abs = abs(sum(losses))
    pf = (gross_profit / gross_loss_abs) if gross_loss_abs > 0 else (999.0 if gross_profit > 0 else 0.0)
    net = sum(ff(t.get("profit_loss")) for t in filtered)

    # Heuristic risk penalties from feature store.
    vol = ff(feature_snapshot.get("VOLATILITY_CLUSTER"))
    liq = ff(feature_snapshot.get("LIQUIDATION_PRESSURE"))
    vwap_dist = ff(feature_snapshot.get("VWAP_DISTANCE"))
    risk_penalty = min(0.25, 0.6 * vol + 0.25 * liq + 0.15 * vwap_dist)

    size_factor = {"fixed": 0.0, "dynamic": 0.03, "reduced_high_vol": 0.02}.get(position_size_model, 0.0)
    symbol_factor = min(0.04, max(0, max_symbol_active - 2) * 0.01)
    regime_bonus = 0.02 if ("range" in regime_filters and "trend" in regime_filters) else 0.0

    backtest_score = 100.0 * (
        0.40 * min(pf / 2.0, 1.0)
        + 0.35 * win_rate
        + 0.15 * max(min(net / 3.0, 1.0), -1.0) * 0.5
        + size_factor
        + symbol_factor
        + regime_bonus
        - risk_penalty
    )
    backtest_score = round(max(0.0, backtest_score), 4)

    # Live score/risk score are conservative derivations.
    live_score = round(max(0.0, backtest_score * (1.0 - 0.35 * liq)), 4)
    risk_score = round(min(100.0, 100.0 * risk_penalty + 25.0 * (1.0 - min(pf / 1.2, 1.0))), 4)

    return {
        "trade_sample_count": n,
        "win_rate": round(win_rate, 6),
        "profit_factor": round(pf, 6),
        "net_pnl": round(net, 6),
        "BACKTEST_SCORE": backtest_score,
        "LIVE_SCORE": live_score,
        "RISK_SCORE": risk_score,
    }


def discover(
    trades: list[dict[str, Any]],
    feature_snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    # GRID_SEARCH
    threshold_grid = [0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7]
    regime_grid = [["range"], ["trend"], ["range", "trend"]]
    sizing_grid = ["fixed", "dynamic", "reduced_high_vol"]
    symbol_grid = [2, 3, 4, 5]
    cid = 1
    for th in threshold_grid:
        for rg in regime_grid:
            for sz in sizing_grid:
                for msa in symbol_grid:
                    metric = eval_candidate(trades, feature_snapshot, th, rg, msa, sz)
                    candidates.append(
                        {
                            "ALPHA_ID": f"ALPHA_GRID_{cid:04d}",
                            "METHOD": "GRID_SEARCH",
                            "FEATURE_SET": [
                                "ORDERBOOK_IMBALANCE",
                                "VWAP_DISTANCE",
                                "VOLATILITY_CLUSTER",
                                "LIQUIDATION_PRESSURE",
                            ],
                            "PARAMETER_SET": {
                                "MIN_EDGE_THRESHOLD": th,
                                "REGIME_FILTER_COMBINATIONS": rg,
                                "MAX_SYMBOL_ACTIVE": msa,
                                "POSITION_SIZING_MODELS": sz,
                            },
                            **metric,
                        }
                    )
                    cid += 1

    # RANDOM_SEARCH
    for i in range(40):
        th = round(RND.uniform(0.4, 0.7), 3)
        rg_pick = RND.choice(regime_grid)
        sz = RND.choice(sizing_grid)
        msa = RND.choice(symbol_grid)
        metric = eval_candidate(trades, feature_snapshot, th, rg_pick, msa, sz)
        candidates.append(
            {
                "ALPHA_ID": f"ALPHA_RND_{i+1:03d}",
                "METHOD": "RANDOM_SEARCH",
                "FEATURE_SET": [
                    "ORDERBOOK_IMBALANCE",
                    "VWAP_DISTANCE",
                    "VOLATILITY_CLUSTER",
                ],
                "PARAMETER_SET": {
                    "MIN_EDGE_THRESHOLD": th,
                    "REGIME_FILTER_COMBINATIONS": rg_pick,
                    "MAX_SYMBOL_ACTIVE": msa,
                    "POSITION_SIZING_MODELS": sz,
                },
                **metric,
            }
        )

    # GENETIC_MUTATION from best grid/random
    top_seed = sorted(candidates, key=lambda x: x["BACKTEST_SCORE"], reverse=True)[:12]
    for i, seed in enumerate(top_seed, start=1):
        p = seed["PARAMETER_SET"]
        mut_th = max(0.4, min(0.7, round(ff(p["MIN_EDGE_THRESHOLD"]) + RND.uniform(-0.03, 0.03), 3)))
        mut_rg = p["REGIME_FILTER_COMBINATIONS"][:]
        if RND.random() < 0.3:
            mut_rg = ["range", "trend"]
        mut_msa = max(2, min(5, int(p["MAX_SYMBOL_ACTIVE"]) + RND.choice([-1, 0, 1])))
        mut_sz = RND.choice(["dynamic", p["POSITION_SIZING_MODELS"], "reduced_high_vol"])
        metric = eval_candidate(trades, feature_snapshot, mut_th, mut_rg, mut_msa, mut_sz)
        candidates.append(
            {
                "ALPHA_ID": f"ALPHA_GEN_{i:03d}",
                "METHOD": "GENETIC_MUTATION",
                "FEATURE_SET": seed["FEATURE_SET"],
                "PARAMETER_SET": {
                    "MIN_EDGE_THRESHOLD": mut_th,
                    "REGIME_FILTER_COMBINATIONS": mut_rg,
                    "MAX_SYMBOL_ACTIVE": mut_msa,
                    "POSITION_SIZING_MODELS": mut_sz,
                },
                **metric,
            }
        )

    candidates.sort(key=lambda x: (x["BACKTEST_SCORE"], x["LIVE_SCORE"]), reverse=True)
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE9 Alpha Discovery Engine")
    parser.add_argument("--feature-snapshot", required=True)
    parser.add_argument("--trade-performance-jsonl", required=True)
    parser.add_argument("--out-candidates", required=True)
    parser.add_argument("--out-report", required=True)
    args = parser.parse_args()

    feature_snapshot = read_json(Path(args.feature_snapshot), {})
    trades = read_jsonl(Path(args.trade_performance_jsonl))
    candidates = discover(trades, feature_snapshot)
    top = candidates[:50]

    Path(args.out_candidates).write_text(json.dumps(top, indent=2, ensure_ascii=False), encoding="utf-8")
    report = "\n".join(
        [
            "PHASE9_ALPHA_DISCOVERY_REPORT",
            f"GENERATED_AT_KST={datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
            f"TOTAL_CANDIDATES_GENERATED={len(candidates)}",
            f"CANDIDATES_EXPORTED={len(top)}",
            f"TOP_ALPHA_ID={top[0]['ALPHA_ID'] if top else 'NONE'}",
            f"TOP_METHOD={top[0]['METHOD'] if top else 'NONE'}",
            f"TOP_BACKTEST_SCORE={top[0]['BACKTEST_SCORE'] if top else 0}",
            f"TOP_LIVE_SCORE={top[0]['LIVE_SCORE'] if top else 0}",
            f"TOP_RISK_SCORE={top[0]['RISK_SCORE'] if top else 0}",
            f"SEARCH_METHODS=GRID_SEARCH,RANDOM_SEARCH,GENETIC_MUTATION",
        ]
    )
    Path(args.out_report).write_text(report, encoding="utf-8")
    print("PHASE9_ALPHA_DISCOVERY_STATUS=COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

