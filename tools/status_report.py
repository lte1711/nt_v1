#!/usr/bin/env python3
"""
Current Status Report - Comprehensive system status overview
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_dashboard_status():
    """Get dashboard API status"""
    try:
        import requests
        response = requests.get("http://127.0.0.1:8788/api/runtime", timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        return {"error": str(e)}


def get_api_status():
    """Get API server status"""
    try:
        import requests
        response = requests.get("http://127.0.0.1:8100/api/investor/account", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        return {"error": str(e)}


def generate_status_report():
    """Generate comprehensive status report"""
    
    print("=" * 70)
    print("🎯 NEXT-TRADE 현재 진행 상태 보고")
    print("=" * 70)
    print(f"📅 생성 시간: {datetime.now().isoformat()}")
    print()
    
    # Dashboard Status
    print("📊 대시보드 상태")
    print("-" * 40)
    
    dashboard_data = get_dashboard_status()
    if dashboard_data and "error" not in dashboard_data:
        print("✅ 대시보드 정상 작동 중")
        print(f"🌐 대시보드 주소: http://127.0.0.1:8788")
        print(f"🔧 엔진 상태: {dashboard_data.get('engine_status', 'Unknown')}")
        print(f"📈 활성 심볼: {dashboard_data.get('active_symbol_count', 0)}개")
        print(f"💰 계좌 자산: {dashboard_data.get('account_equity', 'Unknown')} USDT")
        print(f"📊 실현 손익: {dashboard_data.get('kst_daily_realized_pnl', 'Unknown')} USDT")
        print(f"🎯 일일 거래: {dashboard_data.get('kst_daily_trade_count', 0)}건")
        print(f"🔓 포지션 상태: {dashboard_data.get('position_status', 'Unknown')}")
        
        # Health warnings
        health_warnings = dashboard_data.get('health_warnings', [])
        if health_warnings:
            print("⚠️ 건강 경고:")
            for warning in health_warnings:
                print(f"   - {warning}")
        else:
            print("✅ 시스템 건강 상태 양호")
    else:
        print("❌ 대시보드 연결 실패")
        if dashboard_data and "error" in dashboard_data:
            print(f"   오류: {dashboard_data['error']}")
    
    print()
    
    # API Server Status
    print("🔌 API 서버 상태")
    print("-" * 40)
    
    api_data = get_api_status()
    if api_data and "error" not in api_data:
        print("✅ API 서버 정상 작동 중")
        print(f"🌐 API 주소: http://127.0.0.1:8100")
        print(f"💰 계좌 자산: {api_data.get('account_equity', 'Unknown')} USDT")
        print(f"💵 지갑 잔고: {api_data.get('total_wallet_balance', 'Unknown')} USDT")
        print(f"📊 미실현 손익: {api_data.get('total_unrealized_pnl', 'Unknown')} USDT")
        print(f"🔗 실시간 연결: {'✅' if api_data.get('binance_realtime_link_ok') else '❌'}")
        print(f"🌐 API 기반: {api_data.get('api_base', 'Unknown')}")
        print(f"📡 연결 상태: {api_data.get('binance_link_status', 'Unknown')}")
    else:
        print("❌ API 서버 연결 실패")
        if api_data and "error" in api_data:
            print(f"   오류: {api_data['error']}")
    
    print()
    
    # Trading Performance
    print("📈 거래 성과")
    print("-" * 40)
    
    if dashboard_data and "error" not in dashboard_data:
        daily_pnl = float(dashboard_data.get('kst_daily_realized_pnl', 0))
        trade_count = int(dashboard_data.get('kst_daily_trade_count', 0))
        win_rate = float(dashboard_data.get('kpi_win_rate', 0)) * 100
        drawdown = float(dashboard_data.get('kpi_drawdown', 0)) * 100
        
        print(f"💰 일일 손익: {daily_pnl:+.2f} USDT")
        print(f"📊 일일 거래: {trade_count}건")
        print(f"🎯 승률: {win_rate:.1f}%")
        print(f"📉 드로우다운: {drawdown:.2f}%")
        
        # Daily target progress
        target_pnl = 303.57  # 3% of initial equity
        progress = (daily_pnl / target_pnl) * 100 if target_pnl > 0 else 0
        print(f"🎯 일일 목표: {progress:.1f}% ({daily_pnl:+.2f} / {target_pnl:.2f} USDT)")
        
        # Performance assessment
        if progress > 100:
            target_status = "🎯 목표 달성"
        elif progress > 50:
            target_status = "🟡 목표 진행 중"
        elif progress > 0:
            target_status = "🟠 목표 미달"
        else:
            target_status = "🔴 손실 상태"
        
        print(f"📊 목표 상태: {target_status}")
        
        if win_rate > 45:
            win_rate_status = "🟢 우수"
        elif win_rate > 35:
            win_rate_status = "🟡 양호"
        elif win_rate > 25:
            win_rate_status = "🟠 보통"
        else:
            win_rate_status = "🔴 미흡"
        
        print(f"🎯 승률 상태: {win_rate_status}")
    
    print()
    
    # System Summary
    print("🔧 시스템 요약")
    print("-" * 40)
    
    dashboard_ok = dashboard_data and "error" not in dashboard_data
    api_ok = api_data and "error" not in api_data
    
    if dashboard_ok and api_ok:
        overall_status = "🟢 정상 작동"
    elif dashboard_ok or api_ok:
        overall_status = "🟡 부분 작동"
    else:
        overall_status = "🔴 시스템 중단"
    
    print(f"📊 전체 상태: {overall_status}")
    print(f"🌐 대시보드: {'✅' if dashboard_ok else '❌'}")
    print(f"🔌 API 서버: {'✅' if api_ok else '❌'}")
    
    # Active positions
    if dashboard_data and "error" not in dashboard_data:
        position_count = int(dashboard_data.get('open_positions_count', 0))
        if position_count > 0:
            print(f"🔓 활성 포지션: {position_count}개")
            symbols = dashboard_data.get('open_position_symbols', '-')
            if symbols != '-':
                print(f"   심볼: {symbols}")
        else:
            print("🔓 활성 포지션: 없음")
    
    print()
    
    # Recommendations
    print("📋 권장 사항")
    print("-" * 40)
    
    if not dashboard_ok:
        print("1. 대시보드 서버 재시작 필요")
        print("   명령어: python tools\\dashboard\\multi5_dashboard_server.py")
    
    if not api_ok:
        print("2. API 서버 재시작 필요")
        print("   명령어: python -m uvicorn src.next_trade.api.app:app --host 127.0.0.1 --port 8100")
    
    if dashboard_ok and api_ok:
        if trade_count == 0:
            print("1. 현재 거래 활동 없음")
            print("   - 시장 상태 확인 필요")
            print("   - 트레이딩 설정 검토")
        
        if daily_pnl < 0:
            print("2. 현재 손실 상태")
            print("   - 리스크 관리 강화")
            print("   - 전략 재검토")
        
        if progress < 50:
            print("3. 일일 목표 달성률 낮음")
            print("   - 거래 빈도 증가")
            print("   - 수익률 개선")
    
    print()
    print("=" * 70)


if __name__ == "__main__":
    generate_status_report()
