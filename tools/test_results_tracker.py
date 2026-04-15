#!/usr/bin/env python3
"""
Test Results Tracker - Monitor 3-hour test results after entry quality algorithm modification
Tracks win rate improvement and entry quality paradox resolution
"""

import json
import sys
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_baseline_data() -> Dict[str, Any]:
    """Load baseline data before modification"""
    return {
        'total_trades': 71,
        'wins': 26,
        'losses': 45,
        'win_rate': 36.6,
        'total_pnl': -53.13,
        'very_low_quality_win_rate': 92.9,
        'very_high_quality_win_rate': 22.8,
        'timestamp': datetime.now() - timedelta(hours=3)
    }


def load_current_trades() -> List[Dict[str, Any]]:
    """Load trades after modification"""
    outcomes_path = _project_root() / "logs" / "runtime" / "trade_outcomes.json"
    
    if not outcomes_path.exists():
        return []
    
    try:
        with open(outcomes_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content.strip():
                return []
            return json.loads(content)
    except Exception:
        return []


def analyze_entry_quality_distribution(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze entry quality distribution after modification"""
    
    quality_ranges = {
        'Very Low (0.0-0.1)': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'Low (0.1-0.2)': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'Medium (0.2-0.4)': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'High (0.4-0.6)': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'Very High (0.6+)': {'wins': 0, 'losses': 0, 'total_pnl': 0.0}
    }
    
    for trade in trades:
        entry_score = float(trade.get('entry_quality_score', 0.0))
        pnl = float(trade.get('pnl', 0.0))
        
        # Determine quality range
        if entry_score < 0.1:
            category = 'Very Low (0.0-0.1)'
        elif entry_score < 0.2:
            category = 'Low (0.1-0.2)'
        elif entry_score < 0.4:
            category = 'Medium (0.2-0.4)'
        elif entry_score < 0.6:
            category = 'High (0.4-0.6)'
        else:
            category = 'Very High (0.6+)'
        
        stats = quality_ranges[category]
        stats['total_pnl'] += pnl
        
        if pnl > 0:
            stats['wins'] += 1
        else:
            stats['losses'] += 1
    
    # Calculate win rates
    for category, stats in quality_ranges.items():
        total = stats['wins'] + stats['losses']
        if total > 0:
            stats['win_rate'] = round((stats['wins'] / total) * 100, 1)
        else:
            stats['win_rate'] = 0.0
    
    return quality_ranges


def calculate_improvement_metrics(baseline: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate improvement metrics"""
    
    win_rate_change = current['win_rate'] - baseline['win_rate']
    win_rate_improvement_pct = (win_rate_change / baseline['win_rate']) * 100 if baseline['win_rate'] > 0 else 0
    
    pnl_change = current['total_pnl'] - baseline['total_pnl']
    
    # Calculate paradox improvement
    paradox_improvement = 0
    if 'very_high_quality_win_rate' in current and 'very_low_quality_win_rate' in current:
        baseline_gap = baseline['very_low_quality_win_rate'] - baseline['very_high_quality_win_rate']
        current_gap = current['very_low_quality_win_rate'] - current['very_high_quality_win_rate']
        paradox_improvement = (baseline_gap - current_gap) / baseline_gap * 100 if baseline_gap > 0 else 0
    
    return {
        'win_rate_change': round(win_rate_change, 1),
        'win_rate_improvement_pct': round(win_rate_improvement_pct, 1),
        'pnl_change': round(pnl_change, 2),
        'paradox_improvement_pct': round(paradox_improvement, 1)
    }


def generate_test_report() -> str:
    """Generate comprehensive 3-hour test report"""
    
    baseline = load_baseline_data()
    trades = load_current_trades()
    
    if not trades:
        return "No trade data available for testing."
    
    # Filter trades from last 3 hours
    three_hours_ago = datetime.now() - timedelta(hours=3)
    recent_trades = []
    
    for trade in trades:
        try:
            trade_time = datetime.fromisoformat(trade.get('timestamp', '').replace('Z', '+00:00'))
            if trade_time >= three_hours_ago:
                recent_trades.append(trade)
        except:
            continue
    
    if not recent_trades:
        return "No trades in the last 3 hours."
    
    # Calculate current metrics
    total_trades = len(recent_trades)
    wins = len([t for t in recent_trades if float(t.get('pnl', 0.0)) > 0])
    losses = total_trades - wins
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    total_pnl = sum(float(t.get('pnl', 0.0)) for t in recent_trades)
    
    # Analyze entry quality distribution
    quality_analysis = analyze_entry_quality_distribution(recent_trades)
    
    # Extract key quality metrics
    very_low_win_rate = quality_analysis['Very Low (0.0-0.1)']['win_rate']
    very_high_win_rate = quality_analysis['Very High (0.6+)']['win_rate']
    
    current_metrics = {
        'total_trades': total_trades,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'very_low_quality_win_rate': very_low_win_rate,
        'very_high_quality_win_rate': very_high_win_rate
    }
    
    # Calculate improvements
    improvements = calculate_improvement_metrics(baseline, current_metrics)
    
    # Generate report
    report = f"""
=== 3-HOUR TEST RESULTS REPORT ===
Test Period: Last 3 hours
Modification: Penalty Severity Reduction
Generated: {datetime.now().isoformat()}

## BASELINE VS CURRENT COMPARISON

### Before Modification (Baseline)
- Total Trades: {baseline['total_trades']}
- Win Rate: {baseline['win_rate']}%
- Total PnL: {baseline['total_pnl']} USDT
- Very Low Quality Win Rate: {baseline['very_low_quality_win_rate']}%
- Very High Quality Win Rate: {baseline['very_high_quality_win_rate']}%

### After Modification (Last 3 Hours)
- Total Trades: {current_metrics['total_trades']}
- Win Rate: {current_metrics['win_rate']:.1f}%
- Total PnL: {current_metrics['total_pnl']:.2f} USDT
- Very Low Quality Win Rate: {current_metrics['very_low_quality_win_rate']}%
- Very High Quality Win Rate: {current_metrics['very_high_quality_win_rate']}%

## IMPROVEMENT METRICS

### Win Rate Performance
- Change: {improvements['win_rate_change']:+.1f}%
- Improvement: {improvements['win_rate_improvement_pct']:+.1f}%

### PnL Performance  
- Change: {improvements['pnl_change']:+.2f} USDT

### Paradox Resolution
- Gap Improvement: {improvements['paradox_improvement_pct']:+.1f}%

## ENTRY QUALITY DISTRIBUTION ANALYSIS
"""
    
    for category, stats in quality_analysis.items():
        total = stats['wins'] + stats['losses']
        if total > 0:
            report += f"""
{category}:
  Trades: {total}
  Win Rate: {stats['win_rate']}%
  Total PnL: {stats['total_pnl']:.2f} USDT
"""
    
    # Assessment
    if improvements['win_rate_change'] > 5:
        win_rate_assessment = "EXCELLENT IMPROVEMENT"
    elif improvements['win_rate_change'] > 2:
        win_rate_assessment = "GOOD IMPROVEMENT"
    elif improvements['win_rate_change'] > 0:
        win_rate_assessment = "POSITIVE IMPROVEMENT"
    else:
        win_rate_assessment = "NO IMPROVEMENT"
    
    if improvements['paradox_improvement_pct'] > 30:
        paradox_assessment = "EXCELLENT RESOLUTION"
    elif improvements['paradox_improvement_pct'] > 15:
        paradox_assessment = "GOOD RESOLUTION"
    elif improvements['paradox_improvement_pct'] > 0:
        paradox_assessment = "POSITIVE RESOLUTION"
    else:
        paradox_assessment = "NO RESOLUTION"
    
    report += f"""
## ASSESSMENT

### Win Rate Improvement: {win_rate_assessment}
### Paradox Resolution: {paradox_assessment}

## RECOMMENDATIONS

"""
    
    if improvements['win_rate_change'] > 5:
        report += "- Excellent results! Proceed with Phase 2 modifications\n"
        report += "- Consider implementing signal score rebalancing\n"
    elif improvements['win_rate_change'] > 2:
        report += "- Good progress! Monitor for another 3 hours\n"
        report += "- Consider additional penalty reductions if needed\n"
    else:
        report += "- Limited improvement. Review modification effectiveness\n"
        report += "- Consider more aggressive penalty reductions\n"
    
    report += f"""
## NEXT STEPS
1. Continue monitoring for 3 more hours
2. If win rate > 45%, proceed to Phase 2
3. If paradox resolution > 50%, implement signal rebalancing
4. Document results for future optimization

Test Status: {'SUCCESS' if improvements['win_rate_change'] > 2 else 'MONITORING'}
"""
    
    return report


def monitor_for_3_hours():
    """Monitor and report results for 3 hours"""
    print("=== 3-HOUR MONITORING STARTED ===")
    print(f"Start Time: {datetime.now().isoformat()}")
    print("Modification: Penalty Severity Reduction")
    print("Monitoring: Win Rate and Entry Quality Paradox")
    print()
    
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=3)
    
    while datetime.now() < end_time:
        elapsed = datetime.now() - start_time
        remaining = end_time - datetime.now()
        
        print(f"Progress: {elapsed} elapsed, {remaining} remaining")
        
        # Generate interim report
        report = generate_test_report()
        print(report)
        print("=" * 60)
        
        # Wait for next check (every 30 minutes)
        if datetime.now() < end_time:
            sleep_time = min(30 * 60, (remaining.total_seconds() / 6))  # Check 6 times total
            print(f"Next check in {sleep_time/60:.0f} minutes...")
            time.sleep(sleep_time)
    
    print("=== 3-HOUR MONITORING COMPLETED ===")


if __name__ == "__main__":
    print(generate_test_report())
