#!/usr/bin/env python3
"""
Real-time Status Report - Live data only
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


def get_realtime_status():
    """Get real-time status from live APIs"""
    
    print("=" * 70)
    print("REAL-TIME STATUS REPORT")
    print("=" * 70)
    print(f"Generated: {datetime.now().isoformat()}")
    print()
    
    try:
        import requests
        
        # Get dashboard data
        dashboard_data = None
        try:
            response = requests.get("http://127.0.0.1:8788/api/runtime", timeout=10)
            if response.status_code == 200:
                dashboard_data = response.json()
        except:
            print("ERROR: Cannot connect to dashboard")
        
        # Get API data
        api_data = None
        try:
            response = requests.get("http://127.0.0.1:8100/api/investor/account", timeout=5)
            if response.status_code == 200:
                api_data = response.json()
        except:
            print("ERROR: Cannot connect to API server")
        
        # Get positions
        positions_data = None
        active_positions = 0
        try:
            response = requests.get("http://127.0.0.1:8100/api/v1/investor/positions", timeout=5)
            if response.status_code == 200:
                positions_data = response.json()
                if positions_data and 'positions' in positions_data:
                    active_positions = len([p for p in positions_data['positions'] if float(p.get('positionAmt', 0)) != 0])
        except:
            print("ERROR: Cannot get positions")
        
        # Report real-time data only
        print("1. LIVE SYSTEM STATUS")
        print("-" * 50)
        
        if dashboard_data:
            print(f"Engine Status: {dashboard_data.get('engine_process_status', 'Unknown')}")
            print(f"Active Symbols: {dashboard_data.get('active_symbol_count', 0)}")
            print(f"Open Positions: {dashboard_data.get('open_positions_count', 0)}")
            print(f"Position Status: {dashboard_data.get('position_status', 'Unknown')}")
            print(f"Effective Roles: {dashboard_data.get('effective_role_count', 0)}")
        
        print()
        
        print("2. LIVE ACCOUNT DATA")
        print("-" * 50)
        
        if api_data:
            print(f"Account Equity: {api_data.get('account_equity', 'Unknown')} USDT")
            print(f"Wallet Balance: {api_data.get('total_wallet_balance', 'Unknown')} USDT")
            print(f"Unrealized PnL: {api_data.get('total_unrealized_pnl', 'Unknown')} USDT")
            print(f"Binance Link: {api_data.get('binance_link_status', 'Unknown')}")
            print(f"API Base: {api_data.get('api_base', 'Unknown')}")
        
        print()
        
        print("3. LIVE TRADING DATA")
        print("-" * 50)
        
        if dashboard_data:
            print(f"Daily Realized PnL: {dashboard_data.get('kst_daily_realized_pnl', 'Unknown')} USDT")
            print(f"Daily Trade Count: {dashboard_data.get('kst_daily_trade_count', 0)}")
            print(f"Win Rate: {float(dashboard_data.get('kpi_win_rate', 0)) * 100:.1f}%")
            print(f"Drawdown: {float(dashboard_data.get('kpi_drawdown', 0)) * 100:.2f}%")
            print(f"Entry Attempts: {dashboard_data.get('entry_attempts', 0)}")
            print(f"Trade Executions: {dashboard_data.get('trade_executions', 0)}")
            print(f"Buy Count: {dashboard_data.get('buy_count', 0)}")
            print(f"Sell Count: {dashboard_data.get('sell_count', 0)}")
        
        print()
        
        print("4. LIVE POSITIONS")
        print("-" * 50)
        
        print(f"Active Positions: {active_positions}")
        
        if positions_data and 'positions' in positions_data:
            active_pos = [p for p in positions_data['positions'] if float(p.get('positionAmt', 0)) != 0]
            if active_pos:
                print("Active Position Details:")
                for pos in active_pos[:5]:  # Show max 5
                    symbol = pos.get('symbol', 'Unknown')
                    amount = pos.get('positionAmt', 0)
                    entry_price = pos.get('entryPrice', 0)
                    mark_price = pos.get('markPrice', 0)
                    pnl = pos.get('unRealizedProfit', 0)
                    print(f"  {symbol}: {amount} @ {entry_price} | PnL: {pnl}")
            else:
                print("No active positions")
        
        print()
        
        print("5. LIVE SYSTEM HEALTH")
        print("-" * 50)
        
        if dashboard_data:
            health_warnings = dashboard_data.get('health_warnings', [])
            if health_warnings:
                print("Health Warnings:")
                for warning in health_warnings:
                    print(f"  - {warning}")
            else:
                print("No health warnings")
            
            print(f"Global Kill Switch: {dashboard_data.get('global_kill_switch_state', 'Unknown')}")
            print(f"Exchange API OK: {dashboard_data.get('exchange_api_ok', 'Unknown')}")
            print(f"Position Sync OK: {dashboard_data.get('position_sync_ok', 'Unknown')}")
            print(f"Account Snapshot OK: {dashboard_data.get('account_snapshot_ok', 'Unknown')}")
        
        print()
        
        print("6. LIVE DATA SOURCES")
        print("-" * 50)
        
        if dashboard_data:
            print(f"Current Equity Source: {dashboard_data.get('current_equity_source_label', 'Unknown')}")
            print(f"PnL Real-time: {dashboard_data.get('pnl_realtime', 'Unknown')}")
            print(f"PnL Last Update: {dashboard_data.get('pnl_last_update_ts', 'Unknown')}")
            print(f"Portfolio Snapshot Age: {dashboard_data.get('portfolio_snapshot_age_sec', 0)} seconds")
        
        print()
        
        print("7. LIVE PERFORMANCE METRICS")
        print("-" * 50)
        
        if dashboard_data:
            print(f"Profit Factor: {dashboard_data.get('profit_factor', 0)}")
            print(f"Edge Score: {dashboard_data.get('edge_score', 0)}")
            print(f"Buy/Sell Ratio: {dashboard_data.get('buy_sell_ratio', 0)}")
            print(f"Launched Symbols: {dashboard_data.get('launched_symbols_count', 0)}")
            print(f"Selected Symbols: {dashboard_data.get('selected_symbol_count', 0)}")
        
        print()
        
        # Calculate daily target progress
        if dashboard_data:
            daily_pnl = float(dashboard_data.get('kst_daily_realized_pnl', 0))
            target_pnl = 303.57  # 3% of initial equity
            progress = (daily_pnl / target_pnl) * 100 if target_pnl > 0 else 0
            
            print("8. LIVE TARGET PROGRESS")
            print("-" * 50)
            print(f"Daily Target: 3% ({target_pnl:.2f} USDT)")
            print(f"Current PnL: {daily_pnl:+.2f} USDT")
            print(f"Progress: {progress:.1f}%")
            
            if progress >= 100:
                status = "TARGET ACHIEVED"
                emoji = "GREEN"
            elif progress > 50:
                status = "IN PROGRESS"
                emoji = "YELLOW"
            elif progress > 0:
                status = "BELOW TARGET"
                emoji = "ORANGE"
            else:
                status = "LOSS"
                emoji = "RED"
            
            print(f"Status: {emoji} - {status}")
        
        print()
        
        # Current time and trading window
        current_time = datetime.now()
        kst_time = current_time + timedelta(hours=9)
        hour = kst_time.hour
        
        print("9. LIVE TIME STATUS")
        print("-" * 50)
        print(f"Current Time: {current_time.strftime('%H:%M:%S')} UTC")
        print(f"Korean Time: {kst_time.strftime('%H:%M:%S')} KST")
        
        if 9 <= hour <= 21:
            trading_window = "ACTIVE TRADING HOURS"
            window_emoji = "GREEN"
        elif 22 <= hour <= 23:
            trading_window = "TRADING CLOSING TIME"
            window_emoji = "YELLOW"
        else:
            trading_window = "REST TIME"
            window_emoji = "RED"
        
        print(f"Trading Window: {window_emoji} - {trading_window}")
        
        print()
        
        # Overall assessment
        print("10. LIVE OVERALL ASSESSMENT")
        print("-" * 50)
        
        system_ok = dashboard_data is not None and api_data is not None
        trading_active = dashboard_data.get('active_symbol_count', 0) > 0 if dashboard_data else False
        pnl_positive = daily_pnl > 0 if dashboard_data else False
        
        if system_ok and trading_active and pnl_positive:
            overall = "GREEN - Trading actively and profitable"
        elif system_ok and trading_active:
            overall = "YELLOW - Trading active but not profitable"
        elif system_ok:
            overall = "YELLOW - System ready but not trading"
        else:
            overall = "RED - System issues detected"
        
        print(f"Overall Status: {overall}")
        
        print()
        print("=" * 70)
        print("REAL-TIME STATUS COMPLETE")
        print("=" * 70)
        
    except ImportError:
        print("ERROR: requests module not available")
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    get_realtime_status()
