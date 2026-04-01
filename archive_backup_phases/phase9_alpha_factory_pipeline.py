from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
REPORTS_ROOT = Path(r"C:\next-trade-ver1.0\reports")


def resolve_honey_exec_report_dir() -> Path:
    return REPORTS_ROOT / datetime.now(KST).strftime("%Y-%m-%d") / "honey_execution_reports"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def run_step(cmd: list[str]) -> None:
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != 0:
        raise RuntimeError(f"STEP_FAILED: {' '.join(cmd)}\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE9 Alpha Factory Pipeline")
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--phase7-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    phase7_dir = Path(args.phase7_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    py = sys.executable
    feature_snapshot = out_dir / "feature_store_snapshot.json"
    feature_metrics = out_dir / "feature_store_metrics.txt"
    alpha_candidates = out_dir / "alpha_candidates.json"
    alpha_report = out_dir / "alpha_discovery_report.txt"
    cross_symbol = out_dir / "cross_symbol_opportunities.json"

    run_step(
        [
            py,
            str(Path(__file__).with_name("phase9_feature_store.py")),
            "--runtime-dir",
            str(runtime_dir),
            "--snapshot-out",
            str(feature_snapshot),
            "--metrics-out",
            str(feature_metrics),
        ]
    )
    run_step(
        [
            py,
            str(Path(__file__).with_name("phase9_alpha_discovery_engine.py")),
            "--feature-snapshot",
            str(feature_snapshot),
            "--trade-performance-jsonl",
            str(phase7_dir / "trade_performance.jsonl"),
            "--out-candidates",
            str(alpha_candidates),
            "--out-report",
            str(alpha_report),
        ]
    )
    run_step(
        [
            py,
            str(Path(__file__).with_name("phase9_cross_symbol_engine.py")),
            "--trade-performance-jsonl",
            str(phase7_dir / "trade_performance.jsonl"),
            "--out-json",
            str(cross_symbol),
        ]
    )

    candidates = read_json(alpha_candidates, [])
    # Alpha registry
    registry_rows = []
    for row in candidates:
        registry_rows.append(
            {
                "ALPHA_ID": row.get("ALPHA_ID"),
                "FEATURE_SET": row.get("FEATURE_SET", []),
                "PARAMETER_SET": row.get("PARAMETER_SET", {}),
                "BACKTEST_SCORE": row.get("BACKTEST_SCORE", 0),
                "LIVE_SCORE": row.get("LIVE_SCORE", 0),
                "RISK_SCORE": row.get("RISK_SCORE", 0),
                "trade_sample_count": row.get("trade_sample_count", 0),
                "method": row.get("METHOD", "UNKNOWN"),
            }
        )
    (out_dir / "phase9_alpha_registry.json").write_text(json.dumps(registry_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    # Alpha survival filter
    min_trades = 30
    min_pf = 1.2
    max_risk_score = 55.0
    survivors = []
    rejected = []
    for row in candidates:
        trades = int(row.get("trade_sample_count", 0))
        pf = float(row.get("profit_factor", 0.0))
        risk = float(row.get("RISK_SCORE", 100.0))
        if trades >= min_trades and pf >= min_pf and risk <= max_risk_score:
            survivors.append(row)
        else:
            rejected.append(
                {
                    "ALPHA_ID": row.get("ALPHA_ID"),
                    "reason": f"trades<{min_trades} or pf<{min_pf} or risk>{max_risk_score}",
                    "trade_sample_count": trades,
                    "profit_factor": pf,
                    "risk_score": risk,
                }
            )

    filter_report = "\n".join(
        [
            "PHASE9_ALPHA_SURVIVAL_FILTER_REPORT",
            f"GENERATED_AT_KST={datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
            f"MIN_TRADES={min_trades}",
            f"MIN_PROFIT_FACTOR={min_pf}",
            f"MAX_DRAWDOWN_LIMIT=RISK_SCORE<={max_risk_score}",
            f"TOTAL_CANDIDATES={len(candidates)}",
            f"SURVIVOR_COUNT={len(survivors)}",
            f"REJECTED_COUNT={len(rejected)}",
        ]
    )
    (out_dir / "alpha_survival_filter_report.txt").write_text(filter_report, encoding="utf-8")

    # Deploy safety plan
    deploy_plan = {
        "AUTO_APPLY": False,
        "CONFIG_UPDATE_ONLY": True,
        "ROLLBACK_REQUIRED": True,
        "safe_deploy_sequence": [
            "1) Candidate selection by Candy",
            "2) Technical verification by Gemini",
            "3) Dennis approval",
            "4) Staging config update",
            "5) 30m runtime observation",
            "6) Production rollout via BOOT control center only",
        ],
        "candidate_shortlist": [x.get("ALPHA_ID") for x in candidates[:5]],
        "survivor_shortlist": [x.get("ALPHA_ID") for x in survivors[:5]],
    }
    (out_dir / "phase9_deploy_plan.json").write_text(json.dumps(deploy_plan, indent=2, ensure_ascii=False), encoding="utf-8")

    # Honey summary
    summary = {
        "PHASE9_FEATURE_STORE_BUILT": "YES",
        "ALPHA_DISCOVERY_ENGINE_STATUS": "READY",
        "ALPHA_CANDIDATE_COUNT": str(len(candidates)),
        "CROSS_SYMBOL_ENGINE_STATUS": "READY",
        "ALPHA_REGISTRY_STATUS": "READY",
        "ALPHA_FILTER_STATUS": "READY",
        "DEPLOYMENT_MODE": "MANUAL_APPROVAL_ONLY",
        "SYSTEM_STATUS": "PHASE9_ALPHA_FACTORY_BUILT",
    }
    (out_dir / "nt_phase9_honey_summary.txt").write_text(
        "\n".join([f"{k}={v}" for k, v in summary.items()]),
        encoding="utf-8",
    )

    # Optional governance report mirror
    honey_dir = resolve_honey_exec_report_dir()
    honey_dir.mkdir(parents=True, exist_ok=True)
    (honey_dir / "nt_phase9_alpha_factory_honey_report.txt").write_text(
        "\n".join(
            [
                "NT_PHASE9_ALPHA_FACTORY_HONEY_STATUS=PASS",
                *[f"{k}={v}" for k, v in summary.items()],
                f"EVIDENCE_PATH={out_dir}",
            ]
        ),
        encoding="utf-8",
    )

    print("PHASE9_STATUS=COMPLETE")
    print(f"OUTPUT_DIR={out_dir}")
    for k, v in summary.items():
        print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

