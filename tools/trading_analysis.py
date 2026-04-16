#!/usr/bin/env python3
"""
Trading Analysis - Check modified sources and entry logic
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


def get_recent_events(hours=6):
    """Get recent trading events"""
    events_path = _project_root() / "logs" / "runtime" / "profitmax_v1_events.jsonl"
    
    if not events_path.exists():
        return []
    
    events = []
    cutoff_time = datetime.now() - timedelta(hours=hours)
    
    try:
        with open(events_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    event_time = datetime.fromisoformat(event.get('ts', '').replace('Z', '+00:00'))
                    if event_time >= cutoff_time:
                        events.append(event)
                except:
                    continue
    except Exception as e:
        print(f"Error reading events: {e}")
    
    return events


def get_recent_trades(hours=6):
    """Get recent trades"""
    trades_path = _project_root() / "logs" / "runtime" / "trade_outcomes.json"
    
    if not trades_path.exists():
        return []
    
    try:
        with open(trades_path, 'r', encoding='utf-8') as f:
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
    except Exception as e:
        print(f"Error reading trades: {e}")
        return []


def analyze_entry_logic():
    """Analyze entry logic and modifications"""
    
    print("=" * 70)
    print("🔧 수정된 소스 및 진입 로직 분석")
    print("=" * 70)
    print(f"📅 분석 시간: {datetime.now().isoformat()}")
    print()
    
    # 1. Check modified calculations
    print("📝 1. 수정된 진입 품질 계산")
    print("-" * 50)
    
    calc_path = _project_root() / "tools" / "ops" / "profitmax_v1_calculations.py"
    if calc_path.exists():
        try:
            with open(calc_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check for modifications
            modifications = []
            
            if "win_rate_soft_limit: float = 0.35" in content:
                modifications.append("✅ 승률 소프트 리미트: 0.45 → 0.35 (완화)")
            
            if "drawdown_soft_limit: float = 0.10" in content:
                modifications.append("✅ 드로우다운 소프트 리미트: 0.05 → 0.10 (완화)")
            
            if "score -= 0.05  # Reduced from 0.10 to 0.05" in content:
                modifications.append("✅ 승률 패널티: 0.10 → 0.05 (감소)")
            
            if "score -= 0.08  # Reduced from 0.15 to 0.08" in content:
                modifications.append("✅ 드로우다운 패널티: 0.15 → 0.08 (감소)")
            
            if modifications:
                for mod in modifications:
                    print(f"   {mod}")
            else:
                print("   ❌ 수정된 내용을 찾을 수 없음")
        except Exception as e:
            print(f"   ❌ 파일 읽기 오류: {e}")
    else:
        print("   ❌ 계산 파일을 찾을 수 없음")
    
    print()
    
    # 2. Check time-based entry logic
    print("⏰ 2. 시간별 진입 로직")
    print("-" * 50)
    
    runner_path = _project_root() / "tools" / "ops" / "profitmax_v1_runner.py"
    if runner_path.exists():
        try:
            with open(runner_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check time-based logic
            time_logic = []
            
            if "day_flat_hour_kst: int = 23" in content:
                time_logic.append("✅ 일일 리셋 시간: KST 23:55")
            
            if "day_flat_minute_kst: int = 55" in content:
                time_logic.append("✅ 일일 리셋 분: KST 55분")
            
            if "daily_take_profit_target = round(initial_equity * target_profit_pct, 2)" in content:
                time_logic.append("✅ 동적 3% 목표: 초기 자산 기준 계산")
            
            if "target_profit_pct = 0.03  # 3% target" in content:
                time_logic.append("✅ 목표 수익률: 3% 고정")
            
            if time_logic:
                for logic in time_logic:
                    print(f"   {logic}")
            else:
                print("   ❌ 시간 로직을 찾을 수 없음")
        except Exception as e:
            print(f"   ❌ 파일 읽기 오류: {e}")
    else:
        print("   ❌ 러너 파일을 찾을 수 없음")
    
    print()
    
    # 3. Check recent trading activity
    print("📊 3. 실거래 진행 상태")
    print("-" * 50)
    
    recent_events = get_recent_events(6)
    recent_trades = get_recent_trades(6)
    
    # Analyze events
    entry_blocked = [e for e in recent_events if e.get('event') == 'ENTRY_QUALITY_BLOCKED']
    daily_reset = [e for e in recent_events if e.get('event') == 'DAILY_RESET']
    
    print(f"📈 최근 6시간 이벤트: {len(recent_events)}건")
    print(f"🚫 진입 차단: {len(entry_blocked)}건")
    print(f"🔄 일일 리셋: {len(daily_reset)}건")
    
    if entry_blocked:
        print("\n🚫 진입 차단 상세:")
        for event in entry_blocked[-5:]:  # Show last 5
            symbol = event.get('payload', {}).get('symbol', 'Unknown')
            score = event.get('payload', {}).get('entry_quality_score', 0)
            min_req = event.get('payload', {}).get('min_required', 0)
            win_rate = event.get('payload', {}).get('win_rate', 0)
            drawdown = event.get('payload', {}).get('drawdown', 0)
            
            print(f"   📊 {symbol}: 진입 점수 {score:.3f} (최소 {min_req:.3f})")
            print(f"      승률: {win_rate:.1%}, 드로우다운: {drawdown:.1%}")
    
    if daily_reset:
        print("\n🔄 일일 리셋 상세:")
        for event in daily_reset[-3:]:  # Show last 3
            payload = event.get('payload', {})
            target = payload.get('daily_take_profit_target', 0)
            percentage = payload.get('target_percentage', 0)
            equity = payload.get('initial_equity', 0)
            
            print(f"   🎯 목표: {target:.2f} USDT ({percentage:.1f}%)")
            print(f"   💰 초기 자산: {equity:.2f} USDT")
    
    print()
    
    # 4. Analyze recent trades
    print("💰 4. 최근 거래 분석")
    print("-" * 50)
    
    if recent_trades:
        total_trades = len(recent_trades)
        winning_trades = len([t for t in recent_trades if float(t.get('pnl', 0)) > 0])
        total_pnl = sum(float(t.get('pnl', 0)) for t in recent_trades)
        
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        
        print(f"📊 총 거래: {total_trades}건")
        print(f"🎯 승률: {win_rate:.1f}%")
        print(f"💰 총 손익: {total_pnl:+.4f} USDT")
        print(f"📈 평균 손익: {avg_pnl:+.4f} USDT")
        
        # Show last few trades
        print(f"\n📋 최근 거래 (마지막 5건):")
        for trade in recent_trades[-5:]:
            symbol = trade.get('symbol', 'Unknown')
            pnl = trade.get('pnl', 0)
            entry_score = trade.get('entry_quality_score', 0)
            side = trade.get('side', 'Unknown')
            timestamp = trade.get('timestamp', '')
            
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_str = dt.strftime('%H:%M:%S')
            except:
                time_str = timestamp[:8]
            
            pnl_emoji = "🟢" if float(pnl) > 0 else "🔴"
            print(f"   {pnl_emoji} {symbol}: {pnl:+.4f} USDT ({side})")
            print(f"      진입 점수: {entry_score:.3f}, 시간: {time_str}")
    else:
        print("   ❌ 최근 6시간 내 거래 없음")
    
    print()
    
    # 5. Current status summary
    print("🎯 5. 현재 상태 요약")
    print("-" * 50)
    
    current_time = datetime.now()
    kst_time = current_time + timedelta(hours=9)  # KST is UTC+9
    
    print(f"🕐 현재 시간: {current_time.strftime('%H:%M:%S')} UTC")
    print(f"🕐 한국 시간: {kst_time.strftime('%H:%M:%S')} KST")
    
    # Check if we're in trading hours
    hour = kst_time.hour
    if 9 <= hour <= 21:
        trading_status = "🟢 활성 거래 시간"
    elif 22 <= hour <= 23:
        trading_status = "🟡 거래 마감 시간"
    else:
        trading_status = "🔴 휴식 시간"
    
    print(f"📊 거래 시간대: {trading_status}")
    
    # Entry quality status
    if entry_blocked:
        if len(entry_blocked) > 5:
            entry_status = "🔴 진입 제한 강화"
        elif len(entry_blocked) > 2:
            entry_status = "🟡 진입 제한 중간"
        else:
            entry_status = "🟢 진입 제한 완화"
    else:
        entry_status = "🟢 진입 정상"
    
    print(f"🚫 진입 상태: {entry_status}")
    
    # Overall assessment
    print()
    print("📋 종합 평가")
    print("-" * 50)
    
    if recent_trades and len(recent_trades) > 0:
        if total_pnl > 0:
            overall = "🟢 수익 발생 중"
        elif total_pnl > -10:
            overall = "🟡 소액 손실 중"
        else:
            overall = "🔴 대 손실 발생"
    else:
        overall = "🔴 거래 중단"
    
    print(f"📊 전체 상태: {overall}")
    
    if entry_blocked:
        print("🔧 권장 조치:")
        print("   1. 진입 품질 임계값 재조정")
        print("   2. 포트폴리오 상태 개선")
        print("   3. 시장 조건 확인")
    
    if not recent_trades:
        print("🔧 권장 조치:")
        print("   1. 시장 활성화 시간 대기")
        print("   2. 엔진 상태 확인")
        print("   3. 데이터 피드 확인")
    
    print()
    print("=" * 70)


if __name__ == "__main__":
    analyze_entry_logic()
