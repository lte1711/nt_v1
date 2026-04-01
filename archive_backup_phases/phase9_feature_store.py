from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev
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


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def parse_feature_store(runtime_dir: Path) -> tuple[dict[str, Any], str]:
    profitmax = read_jsonl(runtime_dir / "profitmax_v1_events.jsonl")
    investor = read_jsonl(runtime_dir / "investor_order_api.jsonl")
    multi5 = read_jsonl(runtime_dir / "multi5_runtime_events.jsonl")

    # Collect price/score series by symbol using heartbeat + entry signal snapshots.
    price_series: dict[str, list[float]] = defaultdict(list)
    signal_series: dict[str, list[float]] = defaultdict(list)
    edge_series: dict[str, list[float]] = defaultdict(list)

    for row in profitmax:
        sym = str(row.get("symbol", "")).strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        et = str(row.get("event_type", ""))
        if not sym:
            continue
        if et == "HEARTBEAT":
            price_series[sym].append(fnum(payload.get("price")))
        elif et in ("ENTRY_SIGNAL", "ENTRY_DECISION_5M"):
            signal_series[sym].append(fnum(payload.get("signal_score")))
            edge_series[sym].append(fnum(payload.get("expected_edge")))
        elif et == "ENTRY":
            edge_series[sym].append(fnum(payload.get("expected_edge")))

    # Add multi5 selected symbol edge stream as supplemental signal.
    for row in multi5[-5000:]:
        sym = str(row.get("selected_symbol", "")).strip()
        if sym:
            edge_series[sym].append(fnum(row.get("edge_score")))

    # ORDERBOOK_IMBALANCE proxy: normalized mean signal direction per symbol.
    imbalance_by_symbol: dict[str, float] = {}
    for sym, vals in signal_series.items():
        if not vals:
            continue
        pos = sum(1 for x in vals if x > 0)
        neg = sum(1 for x in vals if x < 0)
        total = max(len(vals), 1)
        imbalance_by_symbol[sym] = round((pos - neg) / total, 6)
    orderbook_imbalance = round(mean(imbalance_by_symbol.values()), 6) if imbalance_by_symbol else 0.0

    # VWAP_DISTANCE proxy: mean absolute deviation from rolling mean price.
    vwap_distance_by_symbol: dict[str, float] = {}
    for sym, prices in price_series.items():
        if len(prices) < 5:
            continue
        avg = mean(prices)
        dev = mean(abs(p - avg) for p in prices)
        vwap_distance_by_symbol[sym] = round(dev / max(abs(avg), 1e-9), 6)
    vwap_distance = round(mean(vwap_distance_by_symbol.values()), 6) if vwap_distance_by_symbol else 0.0

    # VOLATILITY_CLUSTER proxy: stdev of returns (heartbeat prices) averaged by symbol.
    volatility_cluster_by_symbol: dict[str, float] = {}
    for sym, prices in price_series.items():
        if len(prices) < 8:
            continue
        rets: list[float] = []
        for i in range(1, len(prices)):
            p0 = prices[i - 1]
            p1 = prices[i]
            if abs(p0) < 1e-9:
                continue
            rets.append((p1 - p0) / p0)
        if len(rets) >= 5:
            volatility_cluster_by_symbol[sym] = round(pstdev(rets), 6)
    volatility_cluster = round(mean(volatility_cluster_by_symbol.values()), 6) if volatility_cluster_by_symbol else 0.0

    # Funding/open-interest/liquidation sources are not present in current runtime logs.
    # Keep explicit null values and expose data readiness.
    funding_rate = None
    open_interest_delta = None

    # LIQUIDATION_PRESSURE proxy: ratio of rejected orders and large edge spikes.
    total_resp = 0
    rejected = 0
    for row in investor:
        if str(row.get("event_type", "")) != "ORDER_API_RESPONSE":
            continue
        total_resp += 1
        status = row.get("status")
        if isinstance(status, int) and status >= 400:
            rejected += 1
    reject_ratio = (rejected / total_resp) if total_resp > 0 else 0.0
    edge_spikes = sum(1 for vals in edge_series.values() for x in vals if abs(x) >= 1.5)
    edge_total = sum(len(vals) for vals in edge_series.values())
    edge_spike_ratio = (edge_spikes / edge_total) if edge_total > 0 else 0.0
    liquidation_pressure = round(0.7 * reject_ratio + 0.3 * edge_spike_ratio, 6)

    snapshot = {
        "generated_at_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "feature_source": "runtime_log_derived",
        "ORDERBOOK_IMBALANCE": orderbook_imbalance,
        "VWAP_DISTANCE": vwap_distance,
        "VOLATILITY_CLUSTER": volatility_cluster,
        "FUNDING_RATE": funding_rate,
        "OPEN_INTEREST_DELTA": open_interest_delta,
        "LIQUIDATION_PRESSURE": liquidation_pressure,
        "symbol_metrics": {
            "orderbook_imbalance_by_symbol": imbalance_by_symbol,
            "vwap_distance_by_symbol": vwap_distance_by_symbol,
            "volatility_cluster_by_symbol": volatility_cluster_by_symbol,
        },
        "data_readiness": {
            "funding_rate_ready": False,
            "open_interest_ready": False,
            "runtime_price_ready_symbols": len(price_series),
            "signal_ready_symbols": len(signal_series),
        },
    }

    metrics_report = "\n".join(
        [
            "PHASE9_FEATURE_STORE_METRICS",
            f"GENERATED_AT_KST={snapshot['generated_at_kst']}",
            f"ORDERBOOK_IMBALANCE={orderbook_imbalance}",
            f"VWAP_DISTANCE={vwap_distance}",
            f"VOLATILITY_CLUSTER={volatility_cluster}",
            f"FUNDING_RATE={funding_rate}",
            f"OPEN_INTEREST_DELTA={open_interest_delta}",
            f"LIQUIDATION_PRESSURE={liquidation_pressure}",
            f"SYMBOL_PRICE_SERIES_COUNT={len(price_series)}",
            f"SIGNAL_SYMBOL_COUNT={len(signal_series)}",
            f"INVESTOR_RESPONSE_COUNT={total_resp}",
            f"ORDER_REJECT_RATIO={round(reject_ratio, 6)}",
        ]
    )
    return snapshot, metrics_report


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE9 Feature Store Builder")
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--snapshot-out", required=True)
    parser.add_argument("--metrics-out", required=True)
    args = parser.parse_args()

    snapshot, metrics = parse_feature_store(Path(args.runtime_dir))
    Path(args.snapshot_out).write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(args.metrics_out).write_text(metrics, encoding="utf-8")
    print("PHASE9_FEATURE_STORE_STATUS=COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

