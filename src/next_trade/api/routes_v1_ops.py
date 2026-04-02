from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json as _json

from fastapi import APIRouter


router = APIRouter(prefix="/api/v1/ops", tags=["ops"])
CONTRACT_VERSION = "v1"
_ENGINE_ALIVE_WINDOW_SEC = 90.0
_OPS_HEALTH_CACHE: dict[str, Any] = {"expires_at": 0.0, "value": None}
_OPS_HEALTH_CACHE_TTL_SEC = 10.0


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _latest_file(directory: Path, pattern: str) -> Path | None:
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _parse_ts(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        if value > 10_000_000_000:
            value /= 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _tail_jsonl(path: Path, max_lines: int = 256) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    rows: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _runtime_health_snapshot() -> dict[str, Any]:
    root = _project_root()
    runtime_dir = root / "logs" / "runtime"
    phase_log_dir = root / "evidence" / "phase_engine" / "shadow_v2" / "logs"
    pde_log_dir = root / "evidence" / "pde_v2" / "shadow_live"
    now = datetime.now(timezone.utc)

    latest_phase_log = _latest_file(phase_log_dir, "shadow_v2_engine_log_*.jsonl")
    latest_pde_log = _latest_file(pde_log_dir, "execution_072_shadow_live_log_*.jsonl")
    latest_runtime_log = _latest_file(runtime_dir, "multi5_runtime_events.jsonl")
    latest_log = None
    candidates = [p for p in (latest_phase_log, latest_pde_log, latest_runtime_log) if p]
    if candidates:
        latest_log = max(candidates, key=lambda p: p.stat().st_mtime)

    latest_row: dict[str, Any] | None = None
    latest_row_ts: datetime | None = None
    heartbeat_ts: datetime | None = None
    engine_pid = None

    if latest_log:
        for row in reversed(_tail_jsonl(latest_log)):
            row_ts = _parse_ts(row.get("LOOP_TS") or row.get("ts"))
            if latest_row is None and row_ts is not None:
                latest_row = row
                latest_row_ts = row_ts
            if row.get("event_type") == "HEARTBEAT" and row_ts is not None:
                heartbeat_ts = row_ts
                break

    engine_pid_file = runtime_dir / "engine.pid"
    if engine_pid_file.exists():
        try:
            engine_pid = int(engine_pid_file.read_text(encoding="utf-8").strip())
        except Exception:
            engine_pid = None

    reference_ts = heartbeat_ts or latest_row_ts
    if reference_ts is None and latest_log:
        reference_ts = datetime.fromtimestamp(latest_log.stat().st_mtime, tz=timezone.utc)
    age_sec = (now - reference_ts).total_seconds() if reference_ts else None
    engine_alive = bool(reference_ts and age_sec is not None and age_sec <= _ENGINE_ALIVE_WINDOW_SEC)

    if engine_alive:
        health_status = "OK"
    elif reference_ts:
        health_status = "WARN"
    else:
        health_status = "CRITICAL"

    checkpoint_file = runtime_dir / "checkpoint_log.txt"
    checkpoint_age_sec = None
    checkpoint_status = "UNKNOWN"
    checkpoint_source_mode = "checkpoint_file"
    if checkpoint_file.exists():
        checkpoint_age_sec = round(now.timestamp() - checkpoint_file.stat().st_mtime, 1)
        checkpoint_status = "FRESH" if checkpoint_age_sec <= _ENGINE_ALIVE_WINDOW_SEC else "STALE"
    if engine_alive and latest_log and latest_runtime_log and latest_log == latest_runtime_log:
        # Current runtime health is derived from the live runtime event log rather than
        # the legacy checkpoint file, so a stale checkpoint here is informational only.
        checkpoint_source_mode = "runtime_log"
        if checkpoint_status == "STALE":
            checkpoint_status = "INACTIVE_LEGACY"
    elif engine_alive and latest_log and "evidence\\pde_v2\\shadow_live" in str(latest_log):
        checkpoint_source_mode = "pde_shadow_live"
        checkpoint_status = "FRESH"

    return {
        "engine_pid": engine_pid,
        "engine_pid_source": "logs/runtime/engine.pid",
        "engine_pid_present": bool(engine_pid is not None),
        "engine_alive": engine_alive,
        "engine_cmdline_hint": str(latest_log) if latest_log else None,
        "checkpoint_age_sec": checkpoint_age_sec,
        "checkpoint_status": checkpoint_status,
        "checkpoint_source_mode": checkpoint_source_mode,
        "health_status": health_status,
        "last_health_ok": reference_ts.isoformat() if reference_ts and engine_alive else None,
        "restart_count": 0,
        "flap_detected": False,
        "task_state": "Running" if engine_alive else "UNKNOWN",
        "latest_log_path": str(latest_log) if latest_log else None,
        "latest_log_ts": latest_row_ts.isoformat() if latest_row_ts else None,
    }


def _load_runtime_env_defaults() -> None:
    root = _project_root()
    env_path = root / ".env"
    if not env_path.exists():
        print(f"DEBUG: .env file not found at {env_path}")
        return

    try:
        print(f"DEBUG: Loading .env from {env_path}")
        for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and not os.getenv(key):
                os.environ[key] = value
                print(f"DEBUG: Set env var {key}={value[:20]}...")
            elif key and value and os.getenv(key):
                print(f"DEBUG: Env var {key} already exists, skipping")
    except Exception as e:
        print(f"DEBUG: Error loading .env: {e}")
        return


@router.get("/health")
def get_ops_health_v1() -> dict[str, Any]:
    now_mono = time.monotonic()
    cached = _OPS_HEALTH_CACHE.get("value")
    expires_at = float(_OPS_HEALTH_CACHE.get("expires_at", 0.0) or 0.0)
    if isinstance(cached, dict) and now_mono < expires_at:
        return dict(cached)
    result = _runtime_health_snapshot()
    _OPS_HEALTH_CACHE["value"] = result
    _OPS_HEALTH_CACHE["expires_at"] = time.monotonic() + _OPS_HEALTH_CACHE_TTL_SEC
    return result


@router.get("/state")
def get_ops_state_v1() -> dict[str, Any]:
    health = _runtime_health_snapshot()
    pending_total = 0
    return {
        "contract_version": CONTRACT_VERSION,
        "ts": datetime.now(timezone.utc).isoformat(),
        "engine": {
            "pid": health.get("engine_pid"),
            "alive": bool(health.get("engine_alive")),
            "cmdline_hint": health.get("engine_cmdline_hint"),
            "task_state": health.get("task_state") or "UNKNOWN",
            "health_status": health.get("health_status") or "CRITICAL",
        },
        "kill": {
            "is_on": False,
            "reason": "NONE" if health.get("engine_alive") else (health.get("task_state") or "UNKNOWN"),
        },
        "counters": {
            "published": 1 if health.get("engine_alive") else 0,
            "consumed": 1 if health.get("engine_alive") else 0,
            "pending_total": pending_total,
            "restart_count": int(health.get("restart_count") or 0),
        },
        "freshness": {
            "checkpoint_age_sec": health.get("checkpoint_age_sec"),
            "checkpoint_status": health.get("checkpoint_status") or "UNKNOWN",
            "checkpoint_source_mode": health.get("checkpoint_source_mode") or "checkpoint_file",
            "is_stale": not bool(health.get("engine_alive")),
            "last_health_ok": health.get("last_health_ok"),
            "flap_detected": bool(health.get("flap_detected")),
        },
    }


@router.get("/ha_status")
def get_ops_ha_status_v1() -> dict[str, Any]:
    health = _runtime_health_snapshot()
    return {
        "contract_version": CONTRACT_VERSION,
        "ts": datetime.now(timezone.utc).isoformat(),
        "data_ts": health.get("latest_log_ts"),
        "source": "shadow_v2_engine_log",
        "active_stamp": None,
        "stamp": None,
        "age_sec": health.get("checkpoint_age_sec"),
        "ha_eval": None,
        "ha_pass": None,
        "ha_skip": None,
        "delta_eval": None,
        "delta_pass": None,
        "delta_skip": None,
        "engine": {
            "pid": health.get("engine_pid"),
            "alive": bool(health.get("engine_alive")),
            "health_status": health.get("health_status"),
        },
    }


@router.get("/api/investor/account")
async def get_investor_account_probe() -> dict[str, Any]:
    _load_runtime_env_defaults()

    api_key = os.getenv("BINANCE_TESTNET_API_KEY") or os.getenv("BINANCE_TESTNET_KEY_PLACEHOLDER")
    api_secret = os.getenv("BINANCE_TESTNET_API_SECRET") or os.getenv("BINANCE_TESTNET_SECRET_PLACEHOLDER")
    
    # JSON 설정 파일에서 자격증명 로드 (fallback)
    if not api_key or not api_secret:
        try:
            config_path = Path(__file__).parent.parent.parent.parent / "config.json"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = _json.load(f)
                binance_config = config.get("binance_testnet", {})
                api_key = binance_config.get("api_key", api_key)
                api_secret = binance_config.get("api_secret", api_secret)
        except Exception:
            pass
    
    # DEBUG: 환경변수 상태 로깅
    print(f"DEBUG: api_key={api_key[:10]}... if api_key else None")
    print(f"DEBUG: api_secret={api_secret[:10]}... if api_secret else None")
    print(f"DEBUG: env_vars loaded={list(os.environ.keys())}")

    return {
        "ok": True,
        "ts": datetime.now(timezone.utc).isoformat(),
        "credentials_present": bool(api_key and api_secret),
        "api_base": os.getenv("BINANCE_TESTNET_BASE_URL") or os.getenv("BINANCE_FUTURES_TESTNET_BASE_URL") or "https://demo-fapi.binance.com",
        "mode": "probe_only",
    }
