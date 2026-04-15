#!/usr/bin/env python3
"""
Quick Test Report - Generate immediate results after modification
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


def get_current_summary():
    """Get current trading summary"""
    summary_path = _project_root() / "logs" / "runtime" / "profitmax_v1_summary.json"
    
    if not summary_path.exists():
        return None
    
    try:
        with open(summary_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def get_recent_trades(hours=1):
    """Get trades from last N hours"""
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


def analyze_entry_quality_impact(trades):
    """Analyze entry quality impact"""
    if not trades:
        return {}
    
    quality_analysis = {
        'low_quality': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'high_quality': {'wins': 0, 'losses': 0, 'total_pnl': 0.0}
    }
    
    for trade in trades:
        entry_score = float(trade.get('entry_quality_score', 0.0))
        pnl = float(trade.get('pnl', 0.0))
        
        if entry_score < 0.3:
            category = 'low_quality'
        else:
            category = 'high_quality'
        
        quality_analysis[category]['total_pnl'] += pnl
        
        if pnl > 0:
            quality_analysis[category]['wins'] += 1
        else:
            quality_analysis[category]['losses'] += 1
    
    # Calculate win rates
    for category, stats in quality_analysis.items():
        total = stats['wins'] + stats['losses']
        if total > 0:
            stats['win_rate'] = (stats['wins'] / total) * 100
        else:
            stats['win_rate'] = 0.0
    
    return quality_analysis


def generate_quick_report():
    """Generate quick test report"""
    
    print("=== QUICK TEST REPORT ===")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("Modification: Penalty Severity Reduction")
    print()
    
    # Get current summary
    summary = get_current_summary()
    if summary:
        print("CURRENT STATUS:")
        print(f"  Daily PnL: {summary.get('daily_realized_pnl', 0):.2f} USDT")
        print(f"  Daily Trades: {summary.get('daily_trades', 0)}")
        print(f"  Kill Switch: {summary.get('global_kill_switch', False)}")
        print(f"  Active Symbols: {len(summary.get('active_symbols', []))}")
        print()
    
    # Get recent trades
    recent_trades = get_recent_trades(1)
    if recent_trades:
        wins = len([t for t in recent_trades if float(t.get('pnl', 0.0)) > 0])
        total_trades = len(recent_trades)
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        total_pnl = sum(float(t.get('pnl', 0.0)) for t in recent_trades)
        
        print("LAST HOUR PERFORMANCE:")
        print(f"  Trades: {total_trades}")
        print(f"  Win Rate: {win_rate:.1f}%")
        print(f"  PnL: {total_pnl:+.2f} USDT")
        print()
        
        # Entry quality analysis
        quality_analysis = analyze_entry_quality_impact(recent_trades)
        if quality_analysis:
            print("ENTRY QUALITY ANALYSIS:")
            for category, stats in quality_analysis.items():
                total = stats['wins'] + stats['losses']
                if total > 0:
                    print(f"  {category.replace('_', ' ').title()}:")
                    print(f"    Win Rate: {stats['win_rate']:.1f}% ({stats['wins']}/{total})")
                    print(f"    PnL: {stats['total_pnl']:+.2f} USDT")
            print()
        
        # Show recent trades
        print("RECENT TRADES:")
        for trade in recent_trades[-5:]:
            symbol = trade.get('symbol', 'Unknown')
            pnl = trade.get('pnl', 0.0)
            entry_score = trade.get('entry_quality_score', 0.0)
            timestamp = trade.get('timestamp', '')
            
            print(f"  {symbol}: {pnl:+.4f} USDT (Entry: {entry_score:.3f})")
        print()
    else:
        print("NO TRADES IN LAST HOUR")
        print()
    
    # Assessment
    print("ASSESSMENT:")
    
    if summary:
        daily_pnl = summary.get('daily_realized_pnl', 0)
        daily_trades = summary.get('daily_trades', 0)
        
        if daily_pnl > 0:
            print("  ✅ Daily PnL: POSITIVE")
        else:
            print("  ❌ Daily PnL: NEGATIVE")
        
        if daily_trades > 50:
            print("  ✅ Trade Frequency: ACTIVE")
        elif daily_trades > 20:
            print("  ⚠️ Trade Frequency: MODERATE")
        else:
            print("  ❌ Trade Frequency: LOW")
    
    if recent_trades:
        if win_rate > 40:
            print("  ✅ Recent Win Rate: GOOD (>40%)")
        elif win_rate > 30:
            print("  ⚠️ Recent Win Rate: MODERATE (30-40%)")
        else:
            print("  ❌ Recent Win Rate: POOR (<30%)")
    else:
        print("  ⚠️ No recent trades to evaluate")
    
    print()
    print("RECOMMENDATION:")
    
    if summary and recent_trades:
        daily_pnl = summary.get('daily_realized_pnl', 0)
        if daily_pnl > 5 and win_rate > 40:
            print("  🎯 EXCELLENT: Modification working well!")
            print("  → Proceed with Phase 2 modifications")
        elif daily_pnl > 0 and win_rate > 35:
            print("  ✅ GOOD: Positive results")
            print("  → Continue monitoring, consider Phase 2")
        elif win_rate > 30:
            print("  ⚠️ MIXED: Win rate improving")
            print("  → Monitor for 2 more hours")
        else:
            print("  ❌ LIMITED: Minimal improvement")
            print("  → Consider more aggressive modifications")
    else:
        print("  ⏳ WAITING: Need more trade data")
        print("  → Continue monitoring for 2-3 hours")
    
    print()
    print("MODIFICATION SUMMARY:")
    print("  ✅ win_rate penalty: 0.10 → 0.05")
    print("  ✅ drawdown penalty: 0.15 → 0.08")
    print("  ✅ win_rate threshold: 0.45 → 0.35")
    print("  ✅ drawdown threshold: 0.05 → 0.10")


if __name__ == "__main__":
    generate_quick_report()
