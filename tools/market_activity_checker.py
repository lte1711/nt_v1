#!/usr/bin/env python3
"""
Market Activity Checker - Check if market is active and trading conditions are met
"""

import json
import sys
import os
import requests
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_config():
    """Load configuration"""
    config_path = _project_root() / "config.json"
    
    if not config_path.exists():
        return None
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def check_binance_testnet_status():
    """Check Binance testnet status"""
    try:
        response = requests.get("https://testnet.binance.vision/api/v3/time", timeout=5)
        if response.status_code == 200:
            return True, "Binance Testnet: OK"
        else:
            return False, f"Binance Testnet: HTTP {response.status_code}"
    except Exception as e:
        return False, f"Binance Testnet: {str(e)}"


def get_system_status():
    """Get overall system status"""
    summary_path = _project_root() / "logs" / "runtime" / "profitmax_v1_summary.json"
    
    if not summary_path.exists():
        return None
    
    try:
        with open(summary_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def check_trading_conditions():
    """Check if trading conditions are met"""
    system_status = get_system_status()
    
    if not system_status:
        return False, "System status unavailable"
    
    # Check kill switches
    if system_status.get('global_kill_switch', False):
        return False, "Global kill switch active"
    
    if system_status.get('kill', False):
        return False, "Individual kill switch active"
    
    # Check daily limits
    daily_trades = system_status.get('daily_trades', 0)
    if daily_trades >= 12:  # Max trades per day
        return False, f"Daily trade limit reached ({daily_trades}/12)"
    
    # Check profit target
    daily_pnl = system_status.get('daily_realized_pnl', 0)
    if daily_pnl >= 303.57:  # 3% daily target
        return False, f"Daily profit target reached ({daily_pnl:.2f} >= 303.57)"
    
    return True, "All conditions met"


def analyze_market_activity():
    """Analyze market activity and trading conditions"""
    
    print("=== MARKET ACTIVITY CHECK ===")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    # Check Binance testnet
    testnet_ok, testnet_msg = check_binance_testnet_status()
    print(f"EXCHANGE STATUS: {testnet_msg}")
    
    # Check system status
    system_status = get_system_status()
    if system_status:
        print(f"SYSTEM STATUS:")
        print(f"  Daily PnL: {system_status.get('daily_realized_pnl', 0):.2f} USDT")
        print(f"  Daily Trades: {system_status.get('daily_trades', 0)}")
        print(f"  Active Symbols: {len(system_status.get('active_symbols', []))}")
        print(f"  Position Open: {system_status.get('position_open', False)}")
        print(f"  Kill Switch: {system_status.get('global_kill_switch', False)}")
        print()
        
        # Check trading conditions
        can_trade, reason = check_trading_conditions()
        print(f"TRADING CONDITIONS: {'✅ CAN TRADE' if can_trade else '❌ CANNOT TRADE'}")
        print(f"  Reason: {reason}")
        print()
        
        # Analyze activity level
        daily_trades = system_status.get('daily_trades', 0)
        active_symbols = len(system_status.get('active_symbols', []))
        
        if daily_trades > 80:
            activity_level = "VERY HIGH"
        elif daily_trades > 50:
            activity_level = "HIGH"
        elif daily_trades > 20:
            activity_level = "MODERATE"
        elif daily_trades > 5:
            activity_level = "LOW"
        else:
            activity_level = "VERY LOW"
        
        print(f"ACTIVITY LEVEL: {activity_level}")
        print(f"  Daily Trades: {daily_trades}")
        print(f"  Active Symbols: {active_symbols}")
        print()
        
        # Check if we should expect trades
        current_hour = datetime.now().hour
        if 9 <= current_hour <= 21:  # Active trading hours
            expected_activity = "HIGH"
        else:
            expected_activity = "LOW"
        
        print(f"EXPECTED ACTIVITY: {expected_activity} (Current hour: {current_hour})")
        
        # Diagnosis
        print()
        print("DIAGNOSIS:")
        
        if not testnet_ok:
            print("  ❌ Exchange connectivity issue")
        elif not can_trade:
            print(f"  ❌ Trading blocked: {reason}")
        elif daily_trades < 5 and expected_activity == "HIGH":
            print("  ⚠️ Low activity during expected high period")
            print("  → Possible entry quality filtering too strict")
            print("  → Market conditions unfavorable")
        elif daily_trades < 5 and expected_activity == "LOW":
            print("  ✅ Normal low activity period")
        else:
            print("  ✅ System operating normally")
    
    else:
        print("❌ Unable to retrieve system status")
    
    print()
    print("RECOMMENDATIONS:")
    
    if system_status:
        daily_trades = system_status.get('daily_trades', 0)
        daily_pnl = system_status.get('daily_realized_pnl', 0)
        
        if daily_trades < 5:
            print("  1. Check market volatility and volume")
            print("  2. Review entry quality thresholds")
            print("  3. Consider temporary threshold relaxation")
        elif daily_pnl < 0:
            print("  1. Monitor for reversal patterns")
            print("  2. Consider risk reduction")
        else:
            print("  1. Continue current strategy")
            print("  2. Monitor for optimization opportunities")
    
    print("  4. Continue monitoring for 2-3 hours")
    print("  5. Prepare Phase 2 modifications if needed")


if __name__ == "__main__":
    analyze_market_activity()
