#!/usr/bin/env python3
"""
Continuous Monitor - Monitor system for 2-3 hours and report findings
"""

import json
import sys
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_system_status():
    """Get current system status"""
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


def monitor_continuously():
    """Monitor system continuously for 2-3 hours"""
    
    print("=== CONTINUOUS MONITORING STARTED ===")
    print(f"Start Time: {datetime.now().isoformat()}")
    print("Duration: 2 hours")
    print("Purpose: Monitor post-modification performance")
    print()
    
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=2)
    
    # Baseline data
    baseline_daily_pnl = 4.332472
    baseline_daily_trades = 103
    baseline_win_rate = 41.7  # From portfolio snapshot
    
    print(f"BASELINE METRICS:")
    print(f"  Daily PnL: {baseline_daily_pnl:.2f} USDT")
    print(f"  Daily Trades: {baseline_daily_trades}")
    print(f"  Win Rate: {baseline_win_rate:.1f}%")
    print()
    
    check_count = 0
    while datetime.now() < end_time:
        check_count += 1
        elapsed = datetime.now() - start_time
        remaining = end_time - datetime.now()
        
        print(f"=== CHECK #{check_count} - {elapsed.total_seconds()/60:.0f}min elapsed ===")
        
        # Get current status
        status = get_system_status()
        recent_trades = get_recent_trades(1)
        
        if status:
            current_daily_pnl = status.get('daily_realized_pnl', 0)
            current_daily_trades = status.get('daily_trades', 0)
            current_active_symbols = len(status.get('active_symbols', []))
            position_open = status.get('position_open', False)
            
            print(f"CURRENT STATUS:")
            print(f"  Daily PnL: {current_daily_pnl:.2f} USDT")
            print(f"  Daily Trades: {current_daily_trades}")
            print(f"  Active Symbols: {current_active_symbols}")
            print(f"  Position Open: {position_open}")
            
            # Calculate changes
            pnl_change = current_daily_pnl - baseline_daily_pnl
            trades_change = current_daily_trades - baseline_daily_trades
            
            print(f"CHANGES FROM BASELINE:")
            print(f"  PnL Change: {pnl_change:+.2f} USDT")
            print(f"  Trades Change: {trades_change:+d}")
            
            # Recent activity
            if recent_trades:
                recent_wins = len([t for t in recent_trades if float(t.get('pnl', 0.0)) > 0])
                recent_total = len(recent_trades)
                recent_win_rate = (recent_wins / recent_total) * 100 if recent_total > 0 else 0
                recent_pnl = sum(float(t.get('pnl', 0.0)) for t in recent_trades)
                
                print(f"LAST HOUR ACTIVITY:")
                print(f"  Trades: {recent_total}")
                print(f"  Win Rate: {recent_win_rate:.1f}%")
                print(f"  PnL: {recent_pnl:+.2f} USDT")
                
                # Show recent trades
                print(f"RECENT TRADES:")
                for trade in recent_trades[-3:]:
                    symbol = trade.get('symbol', 'Unknown')
                    pnl = trade.get('pnl', 0.0)
                    entry_score = trade.get('entry_quality_score', 0.0)
                    print(f"  {symbol}: {pnl:+.4f} USDT (Entry: {entry_score:.3f})")
            else:
                print(f"LAST HOUR: No trades")
            
            # Assessment
            print(f"ASSESSMENT:")
            
            if pnl_change > 2:
                pnl_assessment = "EXCELLENT"
            elif pnl_change > 0:
                pnl_assessment = "POSITIVE"
            elif pnl_change > -2:
                pnl_assessment = "STABLE"
            else:
                pnl_assessment = "DECLINING"
            
            if recent_trades:
                if recent_win_rate > 45:
                    win_rate_assessment = "EXCELLENT"
                elif recent_win_rate > 35:
                    win_rate_assessment = "GOOD"
                elif recent_win_rate > 25:
                    win_rate_assessment = "MODERATE"
                else:
                    win_rate_assessment = "POOR"
            else:
                win_rate_assessment = "NO DATA"
            
            print(f"  PnL Performance: {pnl_assessment}")
            print(f"  Win Rate: {win_rate_assessment}")
            
            # Overall status
            if pnl_change > 0 and recent_trades and recent_win_rate > 35:
                overall_status = "EXCELLENT"
            elif pnl_change > -1 and recent_trades:
                overall_status = "GOOD"
            elif recent_trades:
                overall_status = "MONITORING"
            else:
                overall_status = "WAITING"
            
            print(f"  Overall: {overall_status}")
        
        else:
            print("❌ Unable to retrieve system status")
        
        print()
        
        # Wait for next check
        if datetime.now() < end_time:
            sleep_time = min(600, (remaining.total_seconds() / 4))  # Check 4 times total
            print(f"Next check in {sleep_time/60:.0f} minutes...")
            time.sleep(sleep_time)
    
    # Final report
    print("=== MONITORING COMPLETED ===")
    
    final_status = get_system_status()
    if final_status:
        final_daily_pnl = final_status.get('daily_realized_pnl', 0)
        final_daily_trades = final_status.get('daily_trades', 0)
        
        final_pnl_change = final_daily_pnl - baseline_daily_pnl
        final_trades_change = final_daily_trades - baseline_daily_trades
        
        print(f"\nFINAL RESULTS:")
        print(f"  Daily PnL: {final_daily_pnl:.2f} USDT ({final_pnl_change:+.2f})")
        print(f"  Daily Trades: {final_daily_trades} ({final_trades_change:+d})")
        
        # Final assessment
        if final_pnl_change > 5:
            final_assessment = "EXCELLENT - Modification highly successful"
        elif final_pnl_change > 2:
            final_assessment = "GOOD - Modification working well"
        elif final_pnl_change > 0:
            final_assessment = "POSITIVE - Modification showing effect"
        elif final_pnl_change > -2:
            final_assessment = "STABLE - No significant change"
        else:
            final_assessment = "DECLINING - Modification needs review"
        
        print(f"\nFINAL ASSESSMENT: {final_assessment}")
        
        # Recommendation
        print(f"\nRECOMMENDATION:")
        if final_pnl_change > 2:
            print("  ✅ Proceed with Phase 2 modifications")
            print("  ✅ Consider signal score rebalancing")
        elif final_pnl_change > 0:
            print("  ⏳ Continue monitoring for 2 more hours")
            print("  ⏳ Prepare Phase 2 modifications")
        else:
            print("  🔍 Review modification effectiveness")
            print("  🔍 Consider more aggressive changes")
    
    else:
        print("\n❌ Unable to generate final report")


if __name__ == "__main__":
    monitor_continuously()
