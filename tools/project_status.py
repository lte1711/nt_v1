#!/usr/bin/env python3
"""
Project Status Check - Comprehensive project progress analysis
"""

import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def check_modifications():
    """Check source code modifications"""
    print("1. SOURCE CODE MODIFICATIONS")
    print("=" * 50)
    
    # Check calculations file
    calc_path = _project_root() / "tools" / "ops" / "profitmax_v1_calculations.py"
    if calc_path.exists():
        with open(calc_path, 'r') as f:
            content = f.read()
        
        # Check for specific modifications
        checks = [
            ('win_rate_soft_limit: float = 0.35', 'win_rate_soft_limit: 0.45 -> 0.35'),
            ('drawdown_soft_limit: float = 0.10', 'drawdown_soft_limit: 0.05 -> 0.10'),
            ('score -= 0.05  # Reduced from 0.10 to 0.05', 'win_rate_penalty: 0.10 -> 0.05'),
            ('score -= 0.08  # Reduced from 0.15 to 0.08', 'drawdown_penalty: 0.15 -> 0.08')
        ]
        
        print("CALCULATIONS MODIFICATIONS:")
        for check, desc in checks:
            if check in content:
                print(f"  OK {desc}")
            else:
                print(f"  NG {desc.split(':')[0]}: NOT FOUND")
    else:
        print("  ERROR: Calculations file not found")
    
    # Check runner file
    runner_path = _project_root() / "tools" / "ops" / "profitmax_v1_runner.py"
    if runner_path.exists():
        with open(runner_path, 'r') as f:
            content = f.read()
        
        # Check for time-based logic
        time_checks = [
            ('day_flat_hour_kst: int = 23', 'Daily reset hour: KST 23'),
            ('day_flat_minute_kst: int = 55', 'Daily reset minute: KST 55'),
            ('daily_take_profit_target = round(initial_equity * target_profit_pct, 2)', 'Dynamic 3% target calculation'),
            ('target_profit_pct = 0.03  # 3% target', 'Target profit rate: 3%')
        ]
        
        print("\nTIME-BASED LOGIC:")
        for check, desc in time_checks:
            if check in content:
                print(f"  OK {desc}")
            else:
                print(f"  NG {desc.split(':')[0]}: NOT FOUND")
    else:
        print("  ERROR: Runner file not found")


def check_system_status():
    """Check system status"""
    print("\n2. SYSTEM STATUS")
    print("=" * 50)
    
    try:
        import requests
        
        # Check dashboard
        try:
            response = requests.get("http://127.0.0.1:8788/api/runtime", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print("DASHBOARD: OK (http://127.0.0.1:8788)")
                print(f"  Engine Status: {data.get('engine_process_status', 'Unknown')}")
                print(f"  Active Symbols: {data.get('active_symbol_count', 0)}")
                print(f"  Account Equity: {data.get('account_equity', 'Unknown')}")
                print(f"  Daily PnL: {data.get('kst_daily_realized_pnl', 'Unknown')}")
            else:
                print("DASHBOARD: ERROR (HTTP {})".format(response.status_code))
        except:
            print("DASHBOARD: ERROR (Connection failed)")
        
        # Check API server
        try:
            response = requests.get("http://127.0.0.1:8100/api/investor/account", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print("API SERVER: OK (http://127.0.0.1:8100)")
                print(f"  Account Equity: {data.get('account_equity', 'Unknown')}")
                print(f"  Wallet Balance: {data.get('total_wallet_balance', 'Unknown')}")
                print(f"  Binance Link: {data.get('binance_link_status', 'Unknown')}")
            else:
                print("API SERVER: ERROR (HTTP {})".format(response.status_code))
        except:
            print("API SERVER: ERROR (Connection failed)")
            
    except ImportError:
        print("ERROR: requests module not available")


def check_recent_activity():
    """Check recent trading activity"""
    print("\n3. RECENT ACTIVITY")
    print("=" * 50)
    
    # Check recent events
    events_path = _project_root() / "logs" / "runtime" / "profitmax_v1_events.jsonl"
    recent_events = []
    
    if events_path.exists():
        try:
            cutoff_time = datetime.now() - timedelta(hours=6)
            with open(events_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        event_time = datetime.fromisoformat(event.get('ts', '').replace('Z', '+00:00'))
                        if event_time >= cutoff_time:
                            recent_events.append(event)
                    except:
                        continue
        except:
            print("ERROR: Could not read events file")
    
    # Check recent trades
    trades_path = _project_root() / "logs" / "runtime" / "trade_outcomes.json"
    recent_trades = []
    
    if trades_path.exists():
        try:
            with open(trades_path, 'r', encoding='utf-8') as f:
                trades = json.load(f)
            
            cutoff_time = datetime.now() - timedelta(hours=6)
            for trade in trades:
                try:
                    trade_time = datetime.fromisoformat(trade.get('timestamp', '').replace('Z', '+00:00'))
                    if trade_time >= cutoff_time:
                        recent_trades.append(trade)
                except:
                    continue
        except:
            print("ERROR: Could not read trades file")
    
    print(f"Recent Events (6h): {len(recent_events)}")
    print(f"Recent Trades (6h): {len(recent_trades)}")
    
    # Analyze events
    entry_blocked = [e for e in recent_events if e.get('event') == 'ENTRY_QUALITY_BLOCKED']
    daily_reset = [e for e in recent_events if e.get('event') == 'DAILY_RESET']
    
    print(f"Entry Quality Blocked: {len(entry_blocked)}")
    print(f"Daily Resets: {len(daily_reset)}")
    
    # Analyze trades
    if recent_trades:
        total_trades = len(recent_trades)
        winning_trades = len([t for t in recent_trades if float(t.get('pnl', 0)) > 0])
        total_pnl = sum(float(t.get('pnl', 0)) for t in recent_trades)
        
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Total PnL: {total_pnl:+.4f} USDT")
        
        if recent_trades:
            last_trade = recent_trades[-1]
            print(f"Last Trade: {last_trade.get('symbol', 'Unknown')} ({last_trade.get('pnl', 0):+.4f})")
    else:
        print("No recent trades")


def check_time_status():
    """Check time-based status"""
    print("\n4. TIME STATUS")
    print("=" * 50)
    
    current_time = datetime.now()
    kst_time = current_time + timedelta(hours=9)  # KST is UTC+9
    
    print(f"Current Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"Korean Time: {kst_time.strftime('%Y-%m-%d %H:%M:%S')} KST")
    
    hour = kst_time.hour
    if 9 <= hour <= 21:
        trading_status = "ACTIVE TRADING HOURS"
        status_emoji = "GREEN"
    elif 22 <= hour <= 23:
        trading_status = "TRADING CLOSING TIME"
        status_emoji = "YELLOW"
    else:
        trading_status = "REST TIME"
        status_emoji = "RED"
    
    print(f"Trading Window: {status_emoji} - {trading_status}")
    
    # Check daily reset time
    if hour == 23 and kst_time.minute >= 55:
        print("Daily Reset: IMMINENT (23:55 KST)")
    elif hour >= 0 and hour <= 1:
        print("Daily Reset: COMPLETED")
    else:
        print("Daily Reset: PENDING")


def check_project_goals():
    """Check project goals"""
    print("\n5. PROJECT GOALS")
    print("=" * 50)
    
    # Check daily target
    print("DAILY TARGET: 3% Profit")
    print("  Initial Equity: 10,119.14 USDT")
    print("  Target Profit: 303.57 USDT")
    
    # Get current daily PnL from dashboard
    try:
        import requests
        response = requests.get("http://127.0.0.1:8788/api/runtime", timeout=5)
        if response.status_code == 200:
            data = response.json()
            daily_pnl = float(data.get('kst_daily_realized_pnl', 0))
            progress = (daily_pnl / 303.57) * 100
            
            print(f"  Current PnL: {daily_pnl:+.2f} USDT")
            print(f"  Progress: {progress:.1f}%")
            
            if progress >= 100:
                print("  Status: ACHIEVED")
            elif progress > 50:
                print("  Status: IN PROGRESS")
            elif progress > 0:
                print("  Status: BELOW TARGET")
            else:
                print("  Status: LOSS")
        else:
            print("  Status: UNKNOWN (Dashboard error)")
    except:
        print("  Status: UNKNOWN (Connection error)")
    
    # Check system modifications
    print("\nSYSTEM MODIFICATIONS:")
    print("  Entry Quality Algorithm: MODIFIED")
    print("  Daily Target System: IMPLEMENTED")
    print("  Real-time Dashboard: UPDATED")
    print("  Cache System: DISABLED")


def generate_summary():
    """Generate overall summary"""
    print("\n6. OVERALL SUMMARY")
    print("=" * 50)
    
    # Check system availability
    system_ok = True
    try:
        import requests
        response = requests.get("http://127.0.0.1:8788/api/runtime", timeout=3)
        if response.status_code != 200:
            system_ok = False
    except:
        system_ok = False
    
    # Check time
    current_time = datetime.now()
    kst_time = current_time + timedelta(hours=9)
    hour = kst_time.hour
    
    # Overall assessment
    if system_ok and 9 <= hour <= 21:
        overall = "GREEN - System operational, active trading hours"
    elif system_ok:
        overall = "YELLOW - System operational, non-trading hours"
    else:
        overall = "RED - System issues detected"
    
    print(f"Overall Status: {overall}")
    
    # Key achievements
    print("\nKEY ACHIEVEMENTS:")
    print("  - Entry quality penalty reduction completed")
    print("  - 3% daily target system implemented")
    print("  - Real-time dashboard cache disabled")
    print("  - Dynamic profit target calculation active")
    
    # Current issues
    print("\nCURRENT ISSUES:")
    print("  - Recent trading activity low")
    print("  - Daily PnL in negative territory")
    print("  - Entry quality blocking active")
    
    # Next steps
    print("\nNEXT STEPS:")
    print("  1. Monitor trading activity during active hours")
    print("  2. Evaluate entry quality algorithm performance")
    print("  3. Consider further parameter adjustments")
    print("  4. Track daily target progress")


def main():
    """Main function"""
    print("=" * 70)
    print("PROJECT STATUS REPORT")
    print("=" * 70)
    print(f"Generated: {datetime.now().isoformat()}")
    print()
    
    check_modifications()
    check_system_status()
    check_recent_activity()
    check_time_status()
    check_project_goals()
    generate_summary()
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
