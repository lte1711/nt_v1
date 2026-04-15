from __future__ import annotations

import json
import re
import statistics
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(r"C:\nt_v1")
CONFIG_PATH = PROJECT_ROOT / "tools/multi5/multi5_config.py"
BOOT_PATH = PROJECT_ROOT / "BOOT/start_engine.ps1"
RESTART_SCRIPT = PROJECT_ROOT / "BOOT/restart_engine.ps1"
EVENT_LOG_PATH = PROJECT_ROOT / "logs/runtime/profitmax_v1_events.jsonl"
REPORT_DIR = PROJECT_ROOT / "reports/2026-03-28/codex_execution_reports"
REPORT_PATH = REPORT_DIR / "STEP_BAEKSEOL_DATA_STALL_FIX_2.txt"
SUMMARY_PATH = REPORT_DIR / "STEP_BAEKSEOL_DATA_STALL_FIX_2.summary.json"

REPORT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Profile:
    name: str
    universe: int
    active: int
    open_positions: int
    scan: int


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def replace_line(text: str, pattern: str, replacement: str) -> str:
    return re.sub(pattern, replacement, text, flags=re.MULTILINE)


def apply_profile(profile: Profile) -> None:
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    config_text = replace_line(config_text, r"^DYNAMIC_UNIVERSE_LIMIT\s*=\s*\d+", f"DYNAMIC_UNIVERSE_LIMIT = {profile.universe}")
    config_text = replace_line(config_text, r"^SCAN_INTERVAL_SEC\s*=\s*\d+", f"SCAN_INTERVAL_SEC = {profile.scan}")
    config_text = replace_line(config_text, r"^MAX_OPEN_POSITION\s*=\s*\d+", f"MAX_OPEN_POSITION = {profile.open_positions}")
    config_text = replace_line(config_text, r"^MAX_SYMBOL_ACTIVE\s*=\s*\d+", f"MAX_SYMBOL_ACTIVE = {profile.active}")
    CONFIG_PATH.write_text(config_text, encoding="utf-8")

    boot_text = BOOT_PATH.read_text(encoding="utf-8", errors="replace")
    boot_text = replace_line(boot_text, r"(\$scanIntervalSec\s*=\s*)\d+", rf"\g<1>{profile.scan}")
    boot_text = replace_line(boot_text, r"(\$maxOpenPositions\s*=\s*)\d+", rf"\g<1>{profile.open_positions}")
    boot_text = replace_line(boot_text, r"(\$maxSymbolActive\s*=\s*)\d+", rf"\g<1>{profile.active}")
    BOOT_PATH.write_text(boot_text, encoding="utf-8")


def restart_engine() -> None:
    subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RESTART_SCRIPT),
        ],
        cwd=str(PROJECT_ROOT),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(12)


def stat(values: list[float]) -> dict[str, Any] | None:
    if not values:
        return None
    values = sorted(values)
    return {
        "count": len(values),
        "avg": round(statistics.fmean(values), 3),
        "median": round(statistics.median(values), 3),
        "min": round(values[0], 3),
        "max": round(values[-1], 3),
    }


def measure_window(cutoff_iso: str) -> dict[str, Any]:
    cutoff = parse_iso_utc(cutoff_iso)
    fetch_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []

    with EVENT_LOG_PATH.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            ts_raw = row.get("ts")
            if not ts_raw:
                continue
            try:
                ts = parse_iso_utc(ts_raw)
            except Exception:
                continue
            if ts < cutoff:
                continue
            event_type = str(row.get("event_type", ""))
            payload = row.get("payload", {}) or {}
            symbol = str(row.get("symbol", ""))
            if not symbol:
                continue
            if event_type == "DATA_FLOW_TRACE_MARKET":
                fetch_rows.append(
                    {
                        "symbol": symbol,
                        "fetch_delay_ms": float(payload.get("fetch_delay_ms", 0.0) or 0.0),
                        "per_symbol_fetch_ms": float(payload.get("per_symbol_fetch_ms", 0.0) or 0.0),
                        "price_source": str(payload.get("price_source", "")),
                    }
                )
            elif event_type == "DATA_FLOW_TRACE_DECISION":
                total_delay = payload.get("total_delay_ms_to_decision")
                per_symbol_total = payload.get("per_symbol_total_ms")
                loop_total = payload.get("loop_total_ms")
                decision_rows.append(
                    {
                        "symbol": symbol,
                        "total_delay_ms": float(total_delay or 0.0),
                        "per_symbol_total_ms": float(per_symbol_total) if per_symbol_total is not None else None,
                        "loop_total_ms": float(loop_total) if loop_total is not None else None,
                    }
                )

    fetch_values = [row["fetch_delay_ms"] for row in fetch_rows]
    decision_values = [row["total_delay_ms"] for row in decision_rows]
    per_symbol_fetch_values = [row["per_symbol_fetch_ms"] for row in fetch_rows]
    per_symbol_total_values = [row["per_symbol_total_ms"] for row in decision_rows if row["per_symbol_total_ms"] is not None]
    loop_total_values = [row["loop_total_ms"] for row in decision_rows if row["loop_total_ms"] is not None]

    grouped_fetch: dict[str, list[float]] = defaultdict(list)
    grouped_total: dict[str, list[float]] = defaultdict(list)
    for row in fetch_rows:
        grouped_fetch[row["symbol"]].append(row["fetch_delay_ms"])
    for row in decision_rows:
        if row["per_symbol_total_ms"] is not None:
            grouped_total[row["symbol"]].append(row["per_symbol_total_ms"])

    top_fetch = [
        {"symbol": symbol, "avg_fetch_delay_ms": round(statistics.fmean(values), 3)}
        for symbol, values in grouped_fetch.items()
    ]
    top_fetch.sort(key=lambda x: x["avg_fetch_delay_ms"], reverse=True)

    top_local_total = [
        {"symbol": symbol, "avg_per_symbol_total_ms": round(statistics.fmean(values), 3)}
        for symbol, values in grouped_total.items()
    ]
    top_local_total.sort(key=lambda x: x["avg_per_symbol_total_ms"], reverse=True)

    price_source_counts: dict[str, int] = defaultdict(int)
    for row in fetch_rows:
        price_source_counts[row["price_source"]] += 1

    return {
        "cutoff": cutoff_iso,
        "fetch": stat(fetch_values),
        "total_delay_to_decision": stat(decision_values),
        "per_symbol_fetch": stat(per_symbol_fetch_values),
        "per_symbol_total": stat(per_symbol_total_values),
        "loop_total": stat(loop_total_values),
        "fetch_over_1s": sum(1 for v in fetch_values if v > 1000),
        "fetch_total": len(fetch_values),
        "decision_over_2s": sum(1 for v in decision_values if v > 2000),
        "decision_total_count": len(decision_values),
        "price_sources": [{"price_source": k, "count": v} for k, v in sorted(price_source_counts.items())],
        "top_fetch_by_symbol": top_fetch[:5],
        "top_local_total_by_symbol": top_local_total[:5],
    }


def run_profile(profile: Profile, settle_seconds: int = 55) -> dict[str, Any]:
    apply_profile(profile)
    restart_engine()
    cutoff = utcnow_iso()
    time.sleep(settle_seconds)
    metrics = measure_window(cutoff)
    return {
        "name": profile.name,
        "universe": profile.universe,
        "active": profile.active,
        "open": profile.open_positions,
        "scan": profile.scan,
        "metrics": metrics,
    }


def main() -> None:
    profiles = [
        Profile("PROFILE_A", 40, 12, 12, 5),
        Profile("PROFILE_B", 20, 8, 8, 5),
        Profile("PROFILE_C", 10, 5, 5, 5),
    ]

    results = [run_profile(profile) for profile in profiles]
    best_profile = min(
        results,
        key=lambda row: (
            row["metrics"]["fetch"]["avg"],
            row["metrics"]["total_delay_to_decision"]["avg"],
        ),
    )

    cadence_y_profile = Profile("CADENCE_Y", best_profile["universe"], best_profile["active"], best_profile["open"], 8)
    cadence_y = run_profile(cadence_y_profile)

    final_stable = best_profile
    if (
        cadence_y["metrics"]["fetch"]["avg"] < best_profile["metrics"]["fetch"]["avg"]
        and cadence_y["metrics"]["total_delay_to_decision"]["avg"] <= best_profile["metrics"]["total_delay_to_decision"]["avg"]
    ):
        final_stable = cadence_y

    final_profile = Profile(
        "FINAL_STABLE",
        final_stable["universe"],
        final_stable["active"],
        final_stable["open"],
        final_stable["scan"],
    )
    apply_profile(final_profile)
    restart_engine()

    profile_a = next(row for row in results if row["name"] == "PROFILE_A")
    profile_c = next(row for row in results if row["name"] == "PROFILE_C")

    root_cause = "UNDECIDED"
    action = "REMEASURE_REQUIRED"
    if profile_c["metrics"]["fetch"]["avg"] <= profile_a["metrics"]["fetch"]["avg"] * 0.85:
        root_cause = "LOCAL_PRESSURE_DOMINANT"
        action = "PROFILE_DOWNSIZE"
    elif profile_c["metrics"]["fetch"]["avg"] >= profile_a["metrics"]["fetch"]["avg"] * 0.95:
        root_cause = "TESTNET_FRESHNESS_CEILING_DOMINANT"
        action = "ACCEPT_RUNTIME_LIMIT_OR_ENVIRONMENT_REDESIGN"

    summary = {
        "profile_results": results,
        "cadence_y": cadence_y,
        "final_stable": final_stable,
        "root_cause": root_cause,
        "action": action,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = ["[FACT]"]
    for row in results:
        lines.append(f"- {row['name']}: universe={row['universe']}, active={row['active']}, open={row['open']}, scan={row['scan']}")
        lines.append(
            f"  - FETCH_DELAY avg/median/min/max = {row['metrics']['fetch']['avg']} / {row['metrics']['fetch']['median']} / "
            f"{row['metrics']['fetch']['min']} / {row['metrics']['fetch']['max']} ms"
        )
        lines.append(
            f"  - TOTAL_DELAY_TO_DECISION avg/median/min/max = {row['metrics']['total_delay_to_decision']['avg']} / "
            f"{row['metrics']['total_delay_to_decision']['median']} / {row['metrics']['total_delay_to_decision']['min']} / "
            f"{row['metrics']['total_delay_to_decision']['max']} ms"
        )
        lines.append(f"  - per_symbol_fetch_ms avg = {row['metrics']['per_symbol_fetch']['avg']} ms")
        lines.append(f"  - per_symbol_total_ms avg = {row['metrics']['per_symbol_total']['avg']} ms")
    lines.append(f"- CADENCE_Y: universe={cadence_y['universe']}, active={cadence_y['active']}, open={cadence_y['open']}, scan={cadence_y['scan']}")
    lines.append(
        f"  - FETCH_DELAY avg/median/min/max = {cadence_y['metrics']['fetch']['avg']} / {cadence_y['metrics']['fetch']['median']} / "
        f"{cadence_y['metrics']['fetch']['min']} / {cadence_y['metrics']['fetch']['max']} ms"
    )
    lines.append(
        f"  - TOTAL_DELAY_TO_DECISION avg/median/min/max = {cadence_y['metrics']['total_delay_to_decision']['avg']} / "
        f"{cadence_y['metrics']['total_delay_to_decision']['median']} / {cadence_y['metrics']['total_delay_to_decision']['min']} / "
        f"{cadence_y['metrics']['total_delay_to_decision']['max']} ms"
    )
    lines.append(f"  - per_symbol_fetch_ms avg = {cadence_y['metrics']['per_symbol_fetch']['avg']} ms")
    lines.append(f"  - per_symbol_total_ms avg = {cadence_y['metrics']['per_symbol_total']['avg']} ms")
    lines.append("- Top local per-symbol total candidates from final stable window:")
    for item in final_stable["metrics"]["top_local_total_by_symbol"]:
        lines.append(f"  - {item['symbol']} = {item['avg_per_symbol_total_ms']} ms")
    lines.extend(
        [
            "",
            "[CRITICAL_FINDINGS]",
            f"- root-cause classification = {root_cause}",
            f"- suggested action = {action}",
            (
                f"- final stable runtime profile = universe={final_stable['universe']}, active={final_stable['active']}, "
                f"open={final_stable['open']}, scan={final_stable['scan']}"
            ),
            "",
            "[INFERENCE]",
            "- Remaining stall classification was decided from profile-downsize comparison, cadence comparison, and local per-symbol timing.",
            "",
            "[FINAL_JUDGMENT]",
            (
                f"- NEXT_STABLE_RUNTIME_PROFILE = universe={final_stable['universe']}, active={final_stable['active']}, "
                f"open={final_stable['open']}, scan={final_stable['scan']}"
            ),
            f"- ROOT_CAUSE = {root_cause}",
            f"- ACTION = {action}",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

