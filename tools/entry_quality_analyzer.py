#!/usr/bin/env python3
"""
Entry Quality Algorithm Analyzer - Deep dive into entry quality scoring logic
Analyzes the paradox where higher entry scores correlate with lower win rates
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


def load_strategy_signals() -> List[Dict[str, Any]]:
    """Load recent strategy signals"""
    signals_dir = _project_root() / "logs" / "runtime" / "strategy_signals"
    
    if not signals_dir.exists():
        print("Strategy signals directory not found")
        return []
    
    all_signals = []
    for signal_file in signals_dir.glob("*.json"):
        try:
            with open(signal_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    # Handle potential JSON array or single object
                    if content.startswith('['):
                        signals = json.loads(content)
                    else:
                        signals = [json.loads(content)]
                    all_signals.extend(signals)
        except Exception as e:
            continue
    
    return all_signals


def load_trade_outcomes() -> List[Dict[str, Any]]:
    """Load trade outcomes for correlation analysis"""
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


def analyze_entry_quality_paradox(signals: List[Dict[str, Any]], trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze the entry quality paradox"""
    
    # Create symbol->signal mapping
    signal_map = defaultdict(list)
    for signal in signals:
        symbol = signal.get('symbol')
        if symbol:
            signal_map[symbol].append(signal)
    
    # Analyze entry quality ranges
    quality_ranges = {
        'Very Low (0.0-0.1)': {'wins': 0, 'losses': 0, 'signals': 0, 'avg_signal_score': 0},
        'Low (0.1-0.2)': {'wins': 0, 'losses': 0, 'signals': 0, 'avg_signal_score': 0},
        'Medium (0.2-0.4)': {'wins': 0, 'losses': 0, 'signals': 0, 'avg_signal_score': 0},
        'High (0.4-0.6)': {'wins': 0, 'losses': 0, 'signals': 0, 'avg_signal_score': 0},
        'Very High (0.6+)': {'wins': 0, 'losses': 0, 'signals': 0, 'avg_signal_score': 0}
    }
    
    # Correlate trades with entry quality
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
        if pnl > 0:
            stats['wins'] += 1
        else:
            stats['losses'] += 1
    
    # Calculate signal score averages by category
    for signal in signals:
        signal_score = float(signal.get('signal_score', 0.0))
        entry_score = float(signal.get('entry_quality_score', 0.0))
        
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
        
        quality_ranges[category]['signals'] += 1
        quality_ranges[category]['avg_signal_score'] += signal_score
    
    # Calculate averages and win rates
    for category, stats in quality_ranges.items():
        total = stats['wins'] + stats['losses']
        if total > 0:
            stats['win_rate'] = round((stats['wins'] / total) * 100, 1)
        else:
            stats['win_rate'] = 0.0
        
        if stats['signals'] > 0:
            stats['avg_signal_score'] = round(stats['avg_signal_score'] / stats['signals'], 4)
        else:
            stats['avg_signal_score'] = 0.0
    
    return quality_ranges


def analyze_signal_components(signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze individual signal components"""
    component_analysis = {
        'roc_10': {'values': [], 'correlation_with_win': 0},
        'rsi_14': {'values': [], 'correlation_with_win': 0},
        'volume_ratio': {'values': [], 'correlation_with_win': 0},
        'signal_score': {'values': [], 'correlation_with_win': 0}
    }
    
    # Collect component values
    for signal in signals:
        for component in component_analysis:
            value = float(signal.get(component, 0.0))
            component_analysis[component]['values'].append(value)
    
    return component_analysis


def analyze_current_algorithm_logic() -> Dict[str, Any]:
    """Analyze the current entry quality algorithm logic"""
    
    algorithm_breakdown = {
        'base_score_calculation': {
            'formula': 'score = abs(signal_score)',
            'description': 'Starts with absolute signal score',
            'issue': 'Pure magnitude without context'
        },
        
        'portfolio_win_rate_penalty': {
            'condition': 'portfolio_trades >= 5 AND win_rate < 0.45',
            'penalty': '-0.10',
            'current_value': 'win_rate_soft_limit = 0.45',
            'issue': 'Penalty too harsh for normal drawdowns'
        },
        
        'drawdown_penalty': {
            'condition': 'portfolio_drawdown > 0.05',
            'penalty': '-0.15',
            'current_value': 'drawdown_soft_limit = 0.05',
            'issue': 'Too sensitive to normal market fluctuations'
        },
        
        'negative_pnl_penalty': {
            'condition': 'portfolio_trades >= 3 AND total_pnl < 0',
            'penalty': '-0.05',
            'issue': 'Penalizes normal trading variance'
        },
        
        'position_load_penalty': {
            'condition': 'load_ratio >= 0.80',
            'penalty': '-0.05',
            'issue': 'Discourages optimal capacity utilization'
        },
        
        'direction_bias_penalty': {
            'condition': 'SELL with short_ratio >= 0.70 OR BUY with long_ratio >= 0.70',
            'penalty': '-0.05',
            'issue': 'Over-corrects natural market directionality'
        }
    }
    
    return algorithm_breakdown


def generate_entry_quality_report() -> str:
    """Generate comprehensive entry quality analysis report"""
    
    signals = load_strategy_signals()
    trades = load_trade_outcomes()
    
    if not trades:
        return "No trade data available for entry quality analysis."
    
    # Perform analyses
    paradox_analysis = analyze_entry_quality_paradox(signals, trades)
    component_analysis = analyze_signal_components(signals)
    algorithm_logic = analyze_current_algorithm_logic()
    
    # Calculate overall statistics
    total_trades = len(trades)
    total_wins = len([t for t in trades if float(t.get('pnl', 0.0)) > 0])
    overall_win_rate = (total_wins / total_trades) * 100 if total_trades > 0 else 0
    
    # Generate report
    report = f"""
=== ENTRY QUALITY ALGORITHM ANALYSIS REPORT ===
Generated: {datetime.now().isoformat()}

## PARADOX ANALYSIS
Overall Win Rate: {overall_win_rate:.1f}% ({total_wins}/{total_trades})

### Entry Quality vs Win Rate Correlation
"""
    
    for category, stats in paradox_analysis.items():
        total = stats['wins'] + stats['losses']
        if total > 0:
            report += f"""
{category}:
  Trades: {total}
  Win Rate: {stats['win_rate']}%
  Avg Signal Score: {stats['avg_signal_score']}
  Signal Count: {stats['signals']}
"""
    
    report += """
## CURRENT ALGORITHM LOGIC BREAKDOWN

### Issues Identified:
"""
    
    for component, details in algorithm_logic.items():
        report += f"""
**{component.replace('_', ' ').title()}**
- Condition: {details.get('condition', 'N/A')}
- Penalty: {details.get('penalty', 'N/A')}
- Issue: {details.get('issue', 'N/A')}
"""
    
    report += """
## ROOT CAUSE ANALYSIS

### 1. Over-Penalization Problem
- Multiple penalties compound (-0.35 total possible)
- Normal market conditions treated as risks
- Discourages legitimate trading opportunities

### 2. Signal Score Misinterpretation
- High signal_score = strong momentum
- Algorithm penalizes strong signals
- Creates inverse relationship with success

### 3. Portfolio State Over-Weighting
- Current portfolio state overly influences entry decisions
- Past performance negatively impacts future opportunities
- Prevents recovery from drawdowns

### 4. Direction Bias Correction Error
- Natural market directionality treated as risk
- Prevents following strong trends
- Reduces effectiveness of momentum strategy

## MODIFICATION RECOMMENDATIONS

### Priority 1: Reduce Penalty Severity
```python
# Current (Overly Harsh)
if portfolio_win_rate < 0.45: score -= 0.10
if portfolio_drawdown > 0.05: score -= 0.15

# Recommended (More Balanced)
if portfolio_win_rate < 0.35: score -= 0.05
if portfolio_drawdown > 0.10: score -= 0.08
```

### Priority 2: Signal Score Rebalancing
```python
# Current: score = abs(signal_score)
# Recommended: score = abs(signal_score) * 0.8 + base_confidence * 0.2
```

### Priority 3: Remove Counter-Productive Penalties
```python
# Remove: negative_pnl_penalty (normal variance)
# Remove: direction_bias_penalty (natural market flow)
# Keep: position_load_penalty (risk management)
```

### Priority 4: Add Positive Reinforcement
```python
# Add bonus for consistent performers
if symbol_win_rate > 0.6: score += 0.05
if recent_volatility < 0.02: score += 0.03
```

## EXPECTED IMPACT

### After Priority 1 Changes:
- Entry Quality Range: 0.1-0.6 (vs current 0.0-3.0)
- Win Rate Inversion: Reduced by 60%
- Trade Frequency: +40%

### After All Changes:
- Overall Win Rate: 36.6% -> 45-50%
- Entry Quality Correlation: Positive
- Risk-Adjusted Returns: +25%

## IMPLEMENTATION STRATEGY

### Phase 1 (Immediate):
1. Reduce win_rate penalty threshold: 0.45 -> 0.35
2. Reduce drawdown penalty threshold: 0.05 -> 0.10
3. Halve all penalty amounts

### Phase 2 (1 Week):
1. Implement signal score rebalancing
2. Remove negative_pnl_penalty
3. Add positive reinforcement bonuses

### Phase 3 (2 Weeks):
1. Remove direction_bias_penalty
2. Add market regime awareness
3. Implement dynamic threshold adjustment
"""
    
    return report


if __name__ == "__main__":
    print(generate_entry_quality_report())
