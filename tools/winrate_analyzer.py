#!/usr/bin/env python3
"""
Win Rate Analyzer - Detailed win/loss analysis for trading performance
Analyzes trade outcomes to identify patterns and improvement opportunities
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_trade_outcomes() -> List[Dict[str, Any]]:
    """Load trade outcomes from runtime logs"""
    outcomes_path = _project_root() / "logs" / "runtime" / "trade_outcomes.json"
    
    if not outcomes_path.exists():
        print(f"Trade outcomes file not found: {outcomes_path}")
        return []
    
    try:
        with open(outcomes_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content.strip():
                return []
            return json.loads(content)
    except Exception as e:
        print(f"Error loading trade outcomes: {e}")
        return []


def analyze_symbol_performance(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze performance by symbol"""
    symbol_stats = defaultdict(lambda: {
        'total': 0,
        'wins': 0,
        'losses': 0,
        'total_pnl': 0.0,
        'win_pnl': 0.0,
        'loss_pnl': 0.0,
        'hold_times': [],
        'entry_scores': []
    })
    
    for trade in trades:
        symbol = trade.get('symbol', 'UNKNOWN')
        pnl = float(trade.get('pnl', 0.0))
        hold_time = float(trade.get('hold_time', 0.0))
        entry_score = float(trade.get('entry_quality_score', 0.0))
        
        stats = symbol_stats[symbol]
        stats['total'] += 1
        stats['total_pnl'] += pnl
        stats['hold_times'].append(hold_time)
        if entry_score > 0:
            stats['entry_scores'].append(entry_score)
        
        if pnl > 0:
            stats['wins'] += 1
            stats['win_pnl'] += pnl
        else:
            stats['losses'] += 1
            stats['loss_pnl'] += pnl
    
    # Calculate derived metrics
    results = {}
    for symbol, stats in symbol_stats.items():
        if stats['total'] == 0:
            continue
            
        win_rate = (stats['wins'] / stats['total']) * 100
        avg_win = stats['win_pnl'] / stats['wins'] if stats['wins'] > 0 else 0
        avg_loss = stats['loss_pnl'] / stats['losses'] if stats['losses'] > 0 else 0
        avg_hold_time = sum(stats['hold_times']) / len(stats['hold_times']) if stats['hold_times'] else 0
        avg_entry_score = sum(stats['entry_scores']) / len(stats['entry_scores']) if stats['entry_scores'] else 0
        
        results[symbol] = {
            'total_trades': stats['total'],
            'wins': stats['wins'],
            'losses': stats['losses'],
            'win_rate': round(win_rate, 1),
            'total_pnl': round(stats['total_pnl'], 4),
            'avg_win': round(avg_win, 4),
            'avg_loss': round(avg_loss, 4),
            'profit_factor': round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0,
            'avg_hold_time': round(avg_hold_time, 1),
            'avg_entry_score': round(avg_entry_score, 3)
        }
    
    return results


def analyze_time_patterns(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze performance by time patterns"""
    hourly_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'total_pnl': 0.0})
    
    for trade in trades:
        try:
            timestamp = trade.get('timestamp', '')
            if timestamp:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                hour = dt.hour
                
                pnl = float(trade.get('pnl', 0.0))
                stats = hourly_stats[hour]
                stats['total_pnl'] += pnl
                
                if pnl > 0:
                    stats['wins'] += 1
                else:
                    stats['losses'] += 1
        except Exception:
            continue
    
    results = {}
    for hour, stats in hourly_stats.items():
        total = stats['wins'] + stats['losses']
        if total == 0:
            continue
            
        win_rate = (stats['wins'] / total) * 100
        results[hour] = {
            'total_trades': total,
            'wins': stats['wins'],
            'losses': stats['losses'],
            'win_rate': round(win_rate, 1),
            'total_pnl': round(stats['total_pnl'], 4)
        }
    
    return results


def analyze_entry_quality_impact(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze impact of entry quality scores on win rates"""
    score_ranges = {
        'Low (0.0-0.2)': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'Medium (0.2-0.4)': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'High (0.4-0.6)': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'Very High (0.6+)': {'wins': 0, 'losses': 0, 'total_pnl': 0.0}
    }
    
    for trade in trades:
        entry_score = float(trade.get('entry_quality_score', 0.0))
        pnl = float(trade.get('pnl', 0.0))
        
        if entry_score < 0.2:
            category = 'Low (0.0-0.2)'
        elif entry_score < 0.4:
            category = 'Medium (0.2-0.4)'
        elif entry_score < 0.6:
            category = 'High (0.4-0.6)'
        else:
            category = 'Very High (0.6+)'
        
        stats = score_ranges[category]
        stats['total_pnl'] += pnl
        
        if pnl > 0:
            stats['wins'] += 1
        else:
            stats['losses'] += 1
    
    results = {}
    for category, stats in score_ranges.items():
        total = stats['wins'] + stats['losses']
        if total == 0:
            continue
            
        win_rate = (stats['wins'] / total) * 100
        results[category] = {
            'total_trades': total,
            'wins': stats['wins'],
            'losses': stats['losses'],
            'win_rate': round(win_rate, 1),
            'total_pnl': round(stats['total_pnl'], 4)
        }
    
    return results


def analyze_hold_time_impact(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze impact of hold time on win rates"""
    hold_ranges = {
        'Short (< 5min)': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'Medium (5-30min)': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'Long (30min-2hr)': {'wins': 0, 'losses': 0, 'total_pnl': 0.0},
        'Very Long (> 2hr)': {'wins': 0, 'losses': 0, 'total_pnl': 0.0}
    }
    
    for trade in trades:
        hold_time = float(trade.get('hold_time', 0.0))
        pnl = float(trade.get('pnl', 0.0))
        
        if hold_time < 300:  # < 5 minutes
            category = 'Short (< 5min)'
        elif hold_time < 1800:  # < 30 minutes
            category = 'Medium (5-30min)'
        elif hold_time < 7200:  # < 2 hours
            category = 'Long (30min-2hr)'
        else:
            category = 'Very Long (> 2hr)'
        
        stats = hold_ranges[category]
        stats['total_pnl'] += pnl
        
        if pnl > 0:
            stats['wins'] += 1
        else:
            stats['losses'] += 1
    
    results = {}
    for category, stats in hold_ranges.items():
        total = stats['wins'] + stats['losses']
        if total == 0:
            continue
            
        win_rate = (stats['wins'] / total) * 100
        results[category] = {
            'total_trades': total,
            'wins': stats['wins'],
            'losses': stats['losses'],
            'win_rate': round(win_rate, 1),
            'total_pnl': round(stats['total_pnl'], 4)
        }
    
    return results


def generate_winrate_report() -> str:
    """Generate comprehensive win rate analysis report"""
    trades = load_trade_outcomes()
    
    if not trades:
        return "No trade data available for analysis."
    
    # Overall statistics
    total_trades = len(trades)
    total_wins = len([t for t in trades if float(t.get('pnl', 0.0)) > 0])
    total_losses = total_trades - total_wins
    overall_win_rate = (total_wins / total_trades) * 100 if total_trades > 0 else 0
    total_pnl = sum(float(t.get('pnl', 0.0)) for t in trades)
    
    # Detailed analyses
    symbol_analysis = analyze_symbol_performance(trades)
    time_analysis = analyze_time_patterns(trades)
    entry_analysis = analyze_entry_quality_impact(trades)
    hold_analysis = analyze_hold_time_impact(trades)
    
    # Generate report
    report = f"""
=== WIN RATE ANALYSIS REPORT ===
Generated: {datetime.now().isoformat()}

## OVERALL PERFORMANCE
- Total Trades: {total_trades}
- Wins: {total_wins}
- Losses: {total_losses}
- Overall Win Rate: {overall_win_rate:.1f}%
- Total PnL: {total_pnl:.4f} USDT

## SYMBOL PERFORMANCE ANALYSIS
"""
    
    # Sort symbols by win rate
    sorted_symbols = sorted(symbol_analysis.items(), key=lambda x: x[1]['win_rate'], reverse=True)
    
    for symbol, stats in sorted_symbols:
        report += f"""
{symbol}:
  Win Rate: {stats['win_rate']}% ({stats['wins']}/{stats['total_trades']})
  Total PnL: {stats['total_pnl']} USDT
  Avg Win: {stats['avg_win']} USDT
  Avg Loss: {stats['avg_loss']} USDT
  Profit Factor: {stats['profit_factor']}
  Avg Hold Time: {stats['avg_hold_time']}s
  Avg Entry Score: {stats['avg_entry_score']}
"""
    
    report += "\n## ENTRY QUALITY IMPACT\n"
    for category, stats in entry_analysis.items():
        report += f"""
{category}:
  Win Rate: {stats['win_rate']}% ({stats['wins']}/{stats['total_trades']})
  Total PnL: {stats['total_pnl']} USDT
"""
    
    report += "\n## HOLD TIME IMPACT\n"
    for category, stats in hold_analysis.items():
        report += f"""
{category}:
  Win Rate: {stats['win_rate']}% ({stats['wins']}/{stats['total_trades']})
  Total PnL: {stats['total_pnl']} USDT
"""
    
    return report


if __name__ == "__main__":
    print(generate_winrate_report())
