#!/usr/bin/env python3
"""
Entry Source Analysis - Time-based entry source analysis
"""

import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def analyze_entry_sources():
    """Analyze time-based entry sources"""
    
    print("=" * 70)
    print("TIME-BASED ENTRY SOURCE ANALYSIS")
    print("=" * 70)
    print(f"Generated: {datetime.now().isoformat()}")
    print()
    
    events_path = _project_root() / "logs" / "runtime" / "profitmax_v1_events.jsonl"
    
    if not events_path.exists():
        print("ERROR: Events log file not found")
        return
    
    # Read events
    events = []
    try:
        with open(events_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    events.append(event)
                except:
                    continue
    except Exception as e:
        print(f"ERROR: Could not read events file: {e}")
        return
    
    # Filter relevant events
    entry_events = []
    for event in events:
        event_type = event.get('event', '')
        if any(keyword in event_type.lower() for keyword in ['entry', 'guard', 'daily_reset']):
            entry_events.append(event)
    
    print(f"Total Events Found: {len(entry_events)}")
    print()
    
    # Time-based analysis
    print("1. TIME-BASED ENTRY ANALYSIS")
    print("-" * 50)
    
    hourly_stats = defaultdict(lambda: {
        'total': 0,
        'blocked': 0,
        'quality_score': 0,
        'guard_reasons': defaultdict(int)
    })
    
    recent_events = []
    cutoff_time = datetime.now() - timedelta(hours=24)
    
    for event in entry_events:
        try:
            event_time = datetime.fromisoformat(event.get('ts', '').replace('Z', '+00:00'))
            if event_time < cutoff_time:
                continue
            
            kst_time = event_time + timedelta(hours=9)
            hour = kst_time.hour
            
            hourly_stats[hour]['total'] += 1
            
            event_type = event.get('event', '')
            payload = event.get('payload', {})
            
            if event_type == 'ENTRY_QUALITY_BLOCKED':
                hourly_stats[hour]['blocked'] += 1
                score = payload.get('entry_quality_score', 0)
                if score:
                    hourly_stats[hour]['quality_score'] += score
                
                reason = payload.get('guard_reason', 'Unknown')
                hourly_stats[hour]['guard_reasons'][reason] += 1
            
            recent_events.append({
                'time': kst_time,
                'event': event_type,
                'symbol': payload.get('symbol', ''),
                'score': payload.get('entry_quality_score', 0),
                'min_required': payload.get('min_required', 0),
                'reason': payload.get('guard_reason', ''),
                'daily_target': payload.get('daily_take_profit_target', 0)
            })
            
        except:
            continue
    
    # Display hourly stats
    print("Hourly Entry Activity (Last 24 hours, KST):")
    print("Hour | Total | Blocked | Block Rate | Avg Score | Main Guard Reason")
    print("-" * 70)
    
    for hour in range(24):
        stats = hourly_stats[hour]
        total = stats['total']
        blocked = stats['blocked']
        
        if total > 0:
            block_rate = (blocked / total) * 100
            avg_score = stats['quality_score'] / blocked if blocked > 0 else 0
            
            # Get main guard reason
            main_reason = "None"
            if stats['guard_reasons']:
                main_reason = max(stats['guard_reasons'].items(), key=lambda x: x[1])[0]
                # Shorten reason names
                if main_reason == "POSITION_ALREADY_OPEN":
                    main_reason = "POSITION_OPEN"
                elif main_reason == "MIN_ORDER_INTERVAL_ACTIVE":
                    main_reason = "ORDER_INTERVAL"
                elif main_reason == "MAX_TRADES_PER_DAY":
                    main_reason = "MAX_TRADES"
                elif main_reason == "MAX_CONSECUTIVE_LOSS":
                    main_reason = "CONSECUTIVE_LOSS"
                elif main_reason == "DAILY_STOP_LOSS":
                    main_reason = "STOP_LOSS"
                elif main_reason == "DAILY_TAKE_PROFIT_LOCK":
                    main_reason = "TAKE_PROFIT"
                elif main_reason == "DATA_STALL":
                    main_reason = "DATA_STALL"
            
            print(f"{hour:02d}   | {total:5d} | {blocked:7d} | {block_rate:8.1f}% | {avg_score:9.3f} | {main_reason}")
    
    print()
    
    # Recent events analysis
    print("2. RECENT ENTRY EVENTS (Last 20)")
    print("-" * 50)
    
    recent_events.sort(key=lambda x: x['time'], reverse=True)
    
    for event in recent_events[:20]:
        time_str = event['time'].strftime('%H:%M:%S')
        event_type = event['event']
        symbol = event['symbol']
        score = event['score']
        min_req = event['min_required']
        reason = event['reason']
        
        # Format event type
        if event_type == 'ENTRY_QUALITY_BLOCKED':
            event_display = "BLOCKED"
            detail = f"Score: {score:.3f} < {min_req:.3f}"
        elif event_type == 'ENTRY_QUALITY_SCORE':
            event_display = "SCORE"
            detail = f"Score: {score:.3f}"
        elif event_type == 'DAILY_RESET':
            event_display = "RESET"
            detail = f"Target: {event['daily_target']:.2f}"
        else:
            event_display = event_type
            detail = f"Reason: {reason}"
        
        print(f"{time_str} | {event_display:8s} | {symbol:8s} | {detail}")
    
    print()
    
    # Guard reason analysis
    print("3. GUARD REASON ANALYSIS")
    print("-" * 50)
    
    guard_reason_counts = defaultdict(int)
    for event in recent_events:
        reason = event['reason']
        if reason:
            guard_reason_counts[reason] += 1
    
    print("Guard Reason Distribution:")
    for reason, count in sorted(guard_reason_counts.items(), key=lambda x: x[1], reverse=True):
        # Format reason names
        display_reason = reason
        if reason == "POSITION_ALREADY_OPEN":
            display_reason = "Position Already Open"
        elif reason == "MIN_ORDER_INTERVAL_ACTIVE":
            display_reason = "Min Order Interval"
        elif reason == "MAX_TRADES_PER_DAY":
            display_reason = "Max Trades Per Day"
        elif reason == "MAX_CONSECUTIVE_LOSS":
            display_reason = "Max Consecutive Loss"
        elif reason == "DAILY_STOP_LOSS":
            display_reason = "Daily Stop Loss"
        elif reason == "DAILY_TAKE_PROFIT_LOCK":
            display_reason = "Daily Take Profit"
        elif reason == "DATA_STALL":
            display_reason = "Data Stall"
        
        print(f"  {display_reason}: {count}")
    
    print()
    
    # Entry quality score analysis
    print("4. ENTRY QUALITY SCORE ANALYSIS")
    print("-" * 50)
    
    scores = []
    min_requirements = []
    
    for event in recent_events:
        if event['score'] > 0:
            scores.append(event['score'])
        if event['min_required'] > 0:
            min_requirements.append(event['min_required'])
    
    if scores:
        avg_score = sum(scores) / len(scores)
        min_score = min(scores)
        max_score = max(scores)
        
        print(f"Entry Quality Scores (Recent):")
        print(f"  Average: {avg_score:.3f}")
        print(f"  Minimum: {min_score:.3f}")
        print(f"  Maximum: {max_score:.3f}")
        print(f"  Count: {len(scores)}")
    
    if min_requirements:
        avg_min_req = sum(min_requirements) / len(min_requirements)
        print(f"\nMinimum Required Scores:")
        print(f"  Average: {avg_min_req:.3f}")
        print(f"  Count: {len(min_requirements)}")
    
    print()
    
    # Trading window analysis
    print("5. TRADING WINDOW ANALYSIS")
    print("-" * 50)
    
    current_time = datetime.now()
    kst_time = current_time + timedelta(hours=9)
    current_hour = kst_time.hour
    
    print(f"Current Time: {current_time.strftime('%H:%M:%S')} UTC")
    print(f"Current KST: {kst_time.strftime('%H:%M:%S')} KST")
    print(f"Current Hour: {current_hour:02d}")
    
    # Check if current hour has activity
    current_hour_stats = hourly_stats[current_hour]
    if current_hour_stats['total'] > 0:
        print(f"Current Hour Activity: {current_hour_stats['total']} events")
        print(f"Current Hour Blocked: {current_hour_stats['blocked']} events")
        print(f"Current Hour Block Rate: {(current_hour_stats['blocked']/current_hour_stats['total']*100):.1f}%")
    else:
        print("Current Hour Activity: None")
    
    # Peak hours analysis
    print("\nPeak Activity Hours:")
    peak_hours = sorted(hourly_stats.items(), key=lambda x: x[1]['total'], reverse=True)[:3]
    for hour, stats in peak_hours:
        if stats['total'] > 0:
            print(f"  {hour:02d}:00-{hour:02d}:59 KST: {stats['total']} events")
    
    print()
    
    # Summary
    print("6. SUMMARY")
    print("-" * 50)
    
    total_events_24h = sum(stats['total'] for stats in hourly_stats.values())
    total_blocked_24h = sum(stats['blocked'] for stats in hourly_stats.values())
    
    if total_events_24h > 0:
        overall_block_rate = (total_blocked_24h / total_events_24h) * 100
        print(f"24h Total Events: {total_events_24h}")
        print(f"24h Total Blocked: {total_blocked_24h}")
        print(f"24h Block Rate: {overall_block_rate:.1f}%")
    else:
        print("24h Total Events: 0")
    
    # Most common guard reason
    if guard_reason_counts:
        most_common = max(guard_reason_counts.items(), key=lambda x: x[1])
        print(f"Most Common Guard Reason: {most_common[0]} ({most_common[1]} times)")
    
    # Current status
    if 9 <= current_hour <= 21:
        trading_status = "ACTIVE TRADING HOURS"
    elif 22 <= current_hour <= 23:
        trading_status = "TRADING CLOSING TIME"
    else:
        trading_status = "REST TIME"
    
    print(f"Current Trading Window: {trading_status}")
    
    print()
    print("=" * 70)


if __name__ == "__main__":
    analyze_entry_sources()
