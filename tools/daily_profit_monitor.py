#!/usr/bin/env python3
"""
Daily Profit Monitor - 3% Target Tracking Module
Tracks and reports daily profit progress towards 3% target
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

# Add project root to sys.path for tools module import
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_config() -> Dict[str, Any]:
    """Load project configuration"""
    config_path = _project_root() / "config.json"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def calculate_daily_target() -> Dict[str, Any]:
    """Calculate 3% daily profit target"""
    config = _load_config()
    initial_equity = config.get("testnet_initial_equity", 10119.13907373)
    target_percentage = 0.03  # 3%
    target_profit = round(initial_equity * target_percentage, 2)
    
    return {
        "initial_equity": initial_equity,
        "target_percentage": target_percentage * 100,
        "target_profit_usdt": target_profit,
        "target_description": f"{target_percentage * 100}% of initial equity"
    }


def get_daily_profit_status() -> Dict[str, Any]:
    """Get current daily profit status"""
    target_info = calculate_daily_target()
    
    # Load current daily PnL from profitmax events
    events_path = _project_root() / "logs" / "runtime" / "profitmax_v1_events.jsonl"
    daily_pnl = 0.0
    daily_trades = 0
    last_reset_time = None
    
    if events_path.exists():
        try:
            with open(events_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        event = json.loads(line)
                        if event.get("event_type") == "DAILY_RESET":
                            last_reset_time = event.get("ts")
                            daily_pnl = 0.0
                            daily_trades = 0
                        elif event.get("event_type") == "POSITION_CLOSED":
                            daily_pnl = event.get("payload", {}).get("daily_realized_pnl", 0.0)
                            daily_trades = event.get("payload", {}).get("daily_trades", 0)
        except Exception as e:
            print(f"Error reading events: {e}")
    
    # Calculate progress
    progress_percentage = (daily_pnl / target_info["target_profit_usdt"]) * 100 if target_info["target_profit_usdt"] > 0 else 0
    remaining_target = target_info["target_profit_usdt"] - daily_pnl
    
    return {
        **target_info,
        "current_daily_pnl": round(daily_pnl, 2),
        "daily_trades": daily_trades,
        "progress_percentage": round(progress_percentage, 2),
        "remaining_target": round(remaining_target, 2),
        "target_achieved": daily_pnl >= target_info["target_profit_usdt"],
        "last_reset_time": last_reset_time,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def generate_daily_report() -> str:
    """Generate formatted daily profit report"""
    status = get_daily_profit_status()
    
    report = f"""
=== DAILY PROFIT MONITOR REPORT ===
Timestamp: {status['timestamp']}
Target: {status['target_percentage']}% ({status['target_profit_usdt']} USDT)
Current PnL: {status['current_daily_pnl']} USDT
Progress: {status['progress_percentage']}%
Remaining: {status['remaining_target']} USDT
Trades Today: {status['daily_trades']}
Status: {'TARGET ACHIEVED! ' if status['target_achieved'] else 'IN PROGRESS'}
===================================
"""
    return report


if __name__ == "__main__":
    print(generate_daily_report())
