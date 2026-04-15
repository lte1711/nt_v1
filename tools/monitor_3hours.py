#!/usr/bin/env python3
"""
3-Hour Monitor - Track results after entry quality algorithm modification
"""

import json
import time
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_current_stats():
    """Get current trading statistics"""
    summary_path = _project_root() / "logs" / "runtime" / "profitmax_v1_summary.json"
    
    if not summary_path.exists():
        return None
    
    try:
        with open(summary_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def get_recent_trades(hours=3):
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


def calculate_win_rate(trades):
    """Calculate win rate from trades"""
    if not trades:
        return 0.0
    
    wins = len([t for t in trades if float(t.get('pnl', 0.0)) > 0])
    return (wins / len(trades)) * 100


def analyze_entry_quality_paradox(trades):
    """Analyze entry quality paradox"""
    if not trades:
        return {"very_low_win_rate": 0, "very_high_win_rate": 0}
    
    very_low_trades = [t for t in trades if float(t.get('entry_quality_score', 0.0)) < 0.1]
    very_high_trades = [t for t in trades if float(t.get('entry_quality_score', 0.0)) >= 0.6]
    
    very_low_win_rate = calculate_win_rate(very_low_trades) if very_low_trades else 0
    very_high_win_rate = calculate_win_rate(very_high_trades) if very_high_trades else 0
    
    return {
        "very_low_win_rate": very_low_win_rate,
        "very_high_win_rate": very_high_win_rate,
        "very_low_count": len(very_low_trades),
        "very_high_count": len(very_high_trades)
    }


def monitor_3_hours():
    """Monitor for 3 hours and report results"""
    print("=== 3-HOUR MONITORING STARTED ===")
    print(f"Start Time: {datetime.now().isoformat()}")
    print("Modification: Penalty Severity Reduction Applied")
    print("Changes Made:")
    print("  - win_rate penalty: 0.10 -> 0.05")
    print("  - drawdown penalty: 0.15 -> 0.08") 
    print("  - win_rate threshold: 0.45 -> 0.35")
    print("  - drawdown threshold: 0.05 -> 0.10")
    print()
    
    # Baseline data
    baseline_win_rate = 36.6
    baseline_very_low = 92.9
    baseline_very_high = 22.8
    baseline_pnl = -53.13
    
    start_time = datetime.now()
    check_interval = 600  # Check every 10 minutes
    
    print(f"Baseline Performance:")
    print(f"  Win Rate: {baseline_win_rate}%")
    print(f"  Very Low Quality Win Rate: {baseline_very_low}%")
    print(f"  Very High Quality Win Rate: {baseline_very_high}%")
    print(f"  Total PnL: {baseline_pnl} USDT")
    print()
    
    while (datetime.now() - start_time).total_seconds() < 10800:  # 3 hours = 10800 seconds
        elapsed = datetime.now() - start_time
        remaining = timedelta(seconds=10800 - elapsed.total_seconds())
        
        print(f"=== CHECK {elapsed.total_seconds()/60:.0f}min elapsed, {remaining.total_seconds()/60:.0f}min remaining ===")
        
        # Get current data
        recent_trades = get_recent_trades(3)
        current_stats = get_current_stats()
        
        if recent_trades:
            current_win_rate = calculate_win_rate(recent_trades)
            paradox_analysis = analyze_entry_quality_paradox(recent_trades)
            current_pnl = sum(float(t.get('pnl', 0.0)) for t in recent_trades)
            
            # Calculate improvements
            win_rate_change = current_win_rate - baseline_win_rate
            paradox_gap_before = baseline_very_low - baseline_very_high
            paradox_gap_after = paradox_analysis["very_low_win_rate"] - paradox_analysis["very_high_win_rate"]
            paradox_improvement = ((paradox_gap_before - paradox_gap_after) / paradox_gap_before * 100) if paradox_gap_before > 0 else 0
            
            print(f"Current Performance (Last 3 Hours):")
            print(f"  Total Trades: {len(recent_trades)}")
            print(f"  Win Rate: {current_win_rate:.1f}% ({win_rate_change:+.1f}%)")
            print(f"  PnL: {current_pnl:+.2f} USDT")
            print(f"  Very Low Quality: {paradox_analysis['very_low_win_rate']:.1f}% ({paradox_analysis['very_low_count']} trades)")
            print(f"  Very High Quality: {paradox_analysis['very_high_win_rate']:.1f}% ({paradox_analysis['very_high_count']} trades)")
            print(f"  Paradox Gap Improvement: {paradox_improvement:+.1f}%")
            
            # Assessment
            if win_rate_change > 5:
                status = "EXCELLENT"
            elif win_rate_change > 2:
                status = "GOOD"
            elif win_rate_change > 0:
                status = "POSITIVE"
            else:
                status = "NEUTRAL"
            
            print(f"  Status: {status}")
        else:
            print("No trades in last 3 hours - waiting for data...")
        
        if current_stats:
            print(f"  Daily Stats: {current_stats.get('daily_realized_pnl', 0):.2f} USDT, {current_stats.get('daily_trades', 0)} trades")
        
        print()
        
        # Wait for next check
        if (datetime.now() - start_time).total_seconds() < 10800:
            time.sleep(check_interval)
    
    # Final report
    print("=== 3-HOUR MONITORING COMPLETED ===")
    
    final_trades = get_recent_trades(3)
    if final_trades:
        final_win_rate = calculate_win_rate(final_trades)
        final_paradox = analyze_entry_quality_paradox(final_trades)
        final_pnl = sum(float(t.get('pnl', 0.0)) for t in final_trades)
        
        final_win_rate_change = final_win_rate - baseline_win_rate
        final_paradox_gap_before = baseline_very_low - baseline_very_high
        final_paradox_gap_after = final_paradox["very_low_win_rate"] - final_paradox["very_high_win_rate"]
        final_paradox_improvement = ((final_paradox_gap_before - final_paradox_gap_after) / final_paradox_gap_before * 100) if final_paradox_gap_before > 0 else 0
        
        print(f"\nFINAL RESULTS:")
        print(f"  Win Rate: {final_win_rate:.1f}% ({final_win_rate_change:+.1f}%)")
        print(f"  PnL: {final_pnl:+.2f} USDT")
        print(f"  Paradox Improvement: {final_paradox_improvement:+.1f}%")
        
        if final_win_rate_change > 5:
            print(f"\nRESULT: SUCCESS - Proceed to Phase 2 modifications")
        elif final_win_rate_change > 2:
            print(f"\nRESULT: GOOD - Continue monitoring, consider Phase 2")
        else:
            print(f"\nRESULT: LIMITED - Review modification effectiveness")
    else:
        print("\nNo trades occurred during 3-hour period")


if __name__ == "__main__":
    monitor_3_hours()
