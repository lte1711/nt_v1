from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))

STATES = [
    "DISCOVERED",
    "PAPER_TESTING",
    "SHADOW_READY",
    "LIVE_CANDIDATE",
    "LIVE_ACTIVE",
    "DEMOTED",
    "RETIRED",
]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def build_lifecycle(alpha_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S %Z")
    registry: list[dict[str, Any]] = []
    for row in alpha_rows:
        alpha_id = str(row.get("ALPHA_ID", "UNKNOWN"))
        trades = int(row.get("trade_sample_count", 0))
        pf = fnum(row.get("profit_factor"))
        bscore = fnum(row.get("BACKTEST_SCORE"))
        lscore = fnum(row.get("LIVE_SCORE"))
        rscore = fnum(row.get("RISK_SCORE"), 100.0)

        if trades < 10:
            state = "DISCOVERED"
        elif trades < 30:
            state = "PAPER_TESTING"
        elif pf >= 1.2 and rscore <= 50:
            state = "SHADOW_READY"
        else:
            state = "PAPER_TESTING"

        registry.append(
            {
                "ALPHA_ID": alpha_id,
                "STATE": state,
                "FEATURE_SET": row.get("FEATURE_SET", []),
                "PARAMETER_SET": row.get("PARAMETER_SET", {}),
                "BACKTEST_SCORE": round(bscore, 4),
                "LIVE_SCORE": round(lscore, 4),
                "RISK_SCORE": round(rscore, 4),
                "trade_sample_count": trades,
                "profit_factor": round(pf, 6),
                "created_ts": now,
                "last_review_ts": now,
                "state_history": [{"ts": now, "state": state, "reason": "phase10_lifecycle_initialization"}],
            }
        )
    return registry


def state_report(registry: list[dict[str, Any]]) -> str:
    cnt = Counter([str(x.get("STATE", "UNKNOWN")) for x in registry])
    lines = [
        "PHASE10_ALPHA_STATE_REPORT",
        f"GENERATED_AT_KST={datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"TOTAL_ALPHAS={len(registry)}",
    ]
    for s in STATES:
        lines.append(f"{s}_COUNT={cnt.get(s, 0)}")
    lines.append("LIFECYCLE_ENGINE=READY")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE10 Alpha Lifecycle Engine")
    parser.add_argument("--phase9-registry", required=True)
    parser.add_argument("--out-registry", required=True)
    parser.add_argument("--out-report", required=True)
    args = parser.parse_args()

    phase9_registry = read_json(Path(args.phase9_registry), default=[])
    lifecycle = build_lifecycle(phase9_registry)
    Path(args.out_registry).write_text(json.dumps(lifecycle, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(args.out_report).write_text(state_report(lifecycle), encoding="utf-8")
    print("PHASE10_LIFECYCLE_STATUS=COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

