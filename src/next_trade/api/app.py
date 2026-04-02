from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from dotenv import load_dotenv

from next_trade.api.routes_v1_investor import router as investor_router
from next_trade.api.routes_v1_ops import router as ops_router


# .env 파일 로드 (python-dotenv 사용)
load_dotenv()

app = FastAPI(title="NEXT-TRADE Ops API", version="1.0")
app.include_router(ops_router)
app.include_router(investor_router)


def _load_config_from_json() -> dict[str, str]:
    """JSON 설정 파일에서 직접 API 키 로드"""
    try:
        root = Path(__file__).resolve().parents[3]
        config_path = root / "config.json"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get("binance_testnet", {})
    except Exception:
        pass
    return {}


def _count_relevant_processes() -> tuple[int, int]:
    relevant_markers = (
        "next_trade.api.app:app",
        "tools\\multi5\\run_multi5_engine.py",
        "tools\\ops\\profitmax_v1_runner.py",
        "tools\\dashboard\\multi5_dashboard_server.py",
    )
    try:
        import psutil

        python_total = 0
        relevant_total = 0
        for proc in psutil.process_iter(["name", "cmdline"]):
            name = str(proc.info.get("name") or "").lower()
            if "python" not in name:
                continue
            python_total += 1
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            if any(marker.lower() in cmdline for marker in relevant_markers):
                relevant_total += 1
        return relevant_total, python_total
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq python.exe"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        python_total = sum(
            1 for line in result.stdout.splitlines() if line.strip().lower().startswith("python.exe")
        )
        return python_total, python_total
    except Exception:
        return 0, 0


@app.get("/api/status")
async def api_status():
    """Return the current boot-oriented process status snapshot."""
    process_count, python_processes = _count_relevant_processes()
    return {
        "boot_engine": "MULTI5",
        "process_count": process_count,
        "python_process_count": python_processes,
        "api_server_port": 8100,
        "dashboard_port": 8788,
        "orders_checked": "unknown",
        "system_status": "normal",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _load_runtime_env_defaults() -> None:
    root = Path(__file__).resolve().parents[3]
    env_path = root / ".env"
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and not os.getenv(key):
                os.environ[key] = value
    except Exception:
        return


