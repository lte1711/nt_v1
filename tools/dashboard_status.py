#!/usr/bin/env python3
"""
Dashboard Status Check - Comprehensive dashboard and system status report
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


def get_system_status():
    """Get comprehensive system status"""
    summary_path = _project_root() / "logs" / "runtime" / "profitmax_v1_summary.json"
    
    if not summary_path.exists():
        return None
    
    try:
        with open(summary_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def get_portfolio_metrics():
    """Get portfolio metrics"""
    metrics_path = _project_root() / "logs" / "runtime" / "portfolio_metrics_snapshot.json"
    
    if not metrics_path.exists():
        return None
    
    try:
        with open(metrics_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def get_recent_trades(hours=1):
    """Get recent trades"""
    outcomes_path = _project_root() / "logs" / "runtime" / "trade_outcomes.json"
    
    if not outcomes_path.exists():
        return []
    
    try:
        with open(outcomes_path, 'r', encoding='utf-8') as f:
            trades = json.load(f)
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_trades = []
        
        for trade in trades:
            try:
                trade_time = datetime.fromisoformat(trade.get('timestamp', '').replace('Z', '+00:00'))
                if trade_time >= cutoff_time:
                    recent_trades.append(trade)
            except:
                continue
        
        return recent_trades
    except:
        return []


def get_portfolio_allocation():
    """Get portfolio allocation"""
    allocation_path = _project_root() / "logs" / "runtime" / "portfolio_allocation.json"
    
    if not allocation_path.exists():
        return None
    
    try:
        with open(allocation_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def generate_dashboard_report():
    """Generate comprehensive dashboard status report"""
    
    print("=" * 60)
    print("🎯 NEXT-TRADE DASHBOARD STATUS REPORT")
    print("=" * 60)
    print(f"📅 Timestamp: {datetime.now().isoformat()}")
    print(f"🌐 Dashboard: http://127.0.0.1:8788")
    print(f"🔌 API Server: http://127.0.0.1:8100")
    print()
    
    # System Status
    print("📊 SYSTEM STATUS")
    print("-" * 30)
    
    status = get_system_status()
    if status:
        daily_pnl = status.get('daily_realized_pnl', 0)
        daily_trades = status.get('daily_trades', 0)
        active_symbols = status.get('active_symbols', [])
        position_open = status.get('position_open', False)
        kill_switch = status.get('global_kill_switch', False)
        
        print(f"💰 Daily PnL: {daily_pnl:+.2f} USDT")
        print(f"📈 Daily Trades: {daily_trades}")
        print(f"🎯 Active Symbols: {len(active_symbols)}")
        print(f"📊 Position Open: {'✅ Yes' if position_open else '❌ No'}")
        print(f"🔴 Kill Switch: {'🚨 ACTIVE' if kill_switch else '✅ Normal'}")
        
        if active_symbols:
            print(f"🔸 Active Symbols: {', '.join(list(active_symbols)[:5])}")
        
        # Daily target progress
        target_pnl = 303.57  # 3% of initial equity
        progress = (daily_pnl / target_pnl) * 100 if target_pnl > 0 else 0
        print(f"🎯 Daily Target: {progress:.1f}% ({daily_pnl:+.2f} / {target_pnl:.2f} USDT)")
        
    else:
        print("❌ System status unavailable")
    
    print()
    
    # Portfolio Metrics
    print("💼 PORTFOLIO METRICS")
    print("-" * 30)
    
    metrics = get_portfolio_metrics()
    if metrics:
        equity = metrics.get('equity', 0)
        realized_pnl = metrics.get('realized_pnl', 0)
        unrealized_pnl = metrics.get('unrealized_pnl', 0)
        win_rate = metrics.get('win_rate', 0) * 100
        drawdown = metrics.get('drawdown', 0) * 100
        total_trades = metrics.get('total_trades', 0)
        
        print(f"💵 Account Equity: {equity:.2f} USDT")
        print(f"💰 Realized PnL: {realized_pnl:+.2f} USDT")
        print(f"📊 Unrealized PnL: {unrealized_pnl:+.2f} USDT")
        print(f"🎯 Win Rate: {win_rate:.1f}%")
        print(f"📉 Drawdown: {drawdown:.2f}%")
        print(f"📈 Total Trades: {total_trades}")
        
        # Performance assessment
        if win_rate > 45:
            win_rate_status = "🟢 EXCELLENT"
        elif win_rate > 35:
            win_rate_status = "🟡 GOOD"
        elif win_rate > 25:
            win_rate_status = "🟠 MODERATE"
        else:
            win_rate_status = "🔴 POOR"
        
        if drawdown < 5:
            drawdown_status = "🟢 EXCELLENT"
        elif drawdown < 10:
            drawdown_status = "🟡 GOOD"
        elif drawdown < 15:
            drawdown_status = "🟠 MODERATE"
        else:
            drawdown_status = "🔴 HIGH"
        
        print(f"📊 Win Rate Status: {win_rate_status}")
        print(f"📉 Drawdown Status: {drawdown_status}")
        
    else:
        print("❌ Portfolio metrics unavailable")
    
    print()
    
    # Recent Activity
    print("⚡ RECENT ACTIVITY")
    print("-" * 30)
    
    recent_trades = get_recent_trades(1)
    if recent_trades:
        wins = len([t for t in recent_trades if float(t.get('pnl', 0.0)) > 0])
        total = len(recent_trades)
        win_rate = (wins / total) * 100 if total > 0 else 0
        total_pnl = sum(float(t.get('pnl', 0.0)) for t in recent_trades)
        
        print(f"📈 Last Hour Trades: {total}")
        print(f"🎯 Last Hour Win Rate: {win_rate:.1f}%")
        print(f"💰 Last Hour PnL: {total_pnl:+.2f} USDT")
        
        print(f"📋 Recent Trades:")
        for trade in recent_trades[-5:]:
            symbol = trade.get('symbol', 'Unknown')
            pnl = trade.get('pnl', 0.0)
            entry_score = trade.get('entry_quality_score', 0.0)
            timestamp = trade.get('timestamp', '')
            
            # Format timestamp
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_str = dt.strftime('%H:%M:%S')
            except:
                time_str = timestamp[:8]
            
            pnl_emoji = "🟢" if pnl > 0 else "🔴"
            print(f"  {pnl_emoji} {symbol}: {pnl:+.4f} USDT (Entry: {entry_score:.3f}) [{time_str}]")
    else:
        print("📉 No trades in last hour")
    
    print()
    
    # Portfolio Allocation
    print("🎯 PORTFOLIO ALLOCATION")
    print("-" * 30)
    
    allocation = get_portfolio_allocation()
    if allocation:
        weights = allocation.get('weights', {})
        target_symbols = allocation.get('target_symbols', [])
        active_symbols = allocation.get('active_symbols', [])
        
        print(f"🎯 Target Symbols: {len(target_symbols)}")
        print(f"🔸 Active Symbols: {len(active_symbols)}")
        
        if weights:
            print(f"📊 Top Allocations:")
            sorted_weights = sorted(weights.items(), key=lambda x: x[1], reverse=True)
            for symbol, weight in sorted_weights[:5]:
                bar_length = int(weight * 20)
                bar = "█" * bar_length + "░" * (20 - bar_length)
                print(f"  {symbol}: {weight:.1%} |{bar}| {weight:.1%}")
        
        # Mode
        mode = allocation.get('mode', 'Unknown')
        print(f"🔧 Allocation Mode: {mode}")
        
    else:
        print("❌ Portfolio allocation unavailable")
    
    print()
    
    # Overall Assessment
    print("🎯 OVERALL ASSESSMENT")
    print("-" * 30)
    
    if status and metrics:
        daily_pnl = status.get('daily_realized_pnl', 0)
        win_rate = metrics.get('win_rate', 0) * 100
        drawdown = metrics.get('drawdown', 0) * 100
        
        # Daily target assessment
        target_progress = (daily_pnl / 303.57) * 100
        if target_progress > 100:
            target_status = "🎯 TARGET ACHIEVED"
        elif target_progress > 50:
            target_status = "🟡 GOOD PROGRESS"
        elif target_progress > 0:
            target_status = "🟠 POSITIVE START"
        else:
            target_status = "🔴 BELOW TARGET"
        
        print(f"🎯 Daily Target: {target_status}")
        
        # System health
        if not status.get('global_kill_switch', False) and status.get('daily_trades', 0) > 0:
            system_health = "🟢 HEALTHY"
        elif status.get('daily_trades', 0) > 0:
            system_health = "🟡 OPERATIONAL"
        else:
            system_health = "🔴 INACTIVE"
        
        print(f"🔧 System Health: {system_health}")
        
        # Trading activity
        if recent_trades:
            activity_status = "🟢 ACTIVE"
        elif status.get('daily_trades', 0) > 50:
            activity_status = "🟡 MODERATE"
        else:
            activity_status = "🔴 LOW"
        
        print(f"⚡ Trading Activity: {activity_status}")
        
        # Overall
        if target_progress > 0 and win_rate > 35 and drawdown < 10:
            overall_status = "🟢 EXCELLENT"
        elif target_progress > -10 and win_rate > 25 and drawdown < 15:
            overall_status = "🟡 GOOD"
        elif target_progress > -20 and win_rate > 20:
            overall_status = "🟠 MODERATE"
        else:
            overall_status = "🔴 NEEDS ATTENTION"
        
        print(f"📊 Overall Status: {overall_status}")
    
    print()
    print("🔗 QUICK ACCESS")
    print("-" * 30)
    print("🌐 Dashboard: http://127.0.0.1:8788")
    print("🔌 API: http://127.0.0.1:8100")
    print("📊 Logs: ./logs/runtime/")
    print()
    
    print("=" * 60)


if __name__ == "__main__":
    generate_dashboard_report()
