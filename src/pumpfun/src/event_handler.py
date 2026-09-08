"""
Event Handling and Formatting Module
"""

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class EventHandler:
    """Handles parsing and formatting of SSE events."""
    
    @staticmethod
    def format_event(event_type: str, event_data: Dict[str, Any]) -> str:
        """Format event for console display."""
        try:
            timestamp = datetime.now().strftime('%H:%M:%S')
            
            if event_type == "connected":
                return f"✅ [{timestamp}] Connected: {event_data.get('endpoint', 'unknown')}"
                
            elif event_type == "trade":
                return EventHandler._format_trade(timestamp, event_data)
                
            elif event_type == "new_coin":
                return EventHandler._format_new_coin(timestamp, event_data)
                
            elif event_type == "new_coin_detailed":
                return EventHandler._format_new_coin_detailed(timestamp, event_data)
                
            elif event_type == "pump_trade":
                return EventHandler._format_pump_trade(timestamp, event_data)
                
            elif event_type == "graduated":
                return EventHandler._format_graduated(timestamp, event_data)
                
            else:
                return f"📨 [{timestamp}] {event_type}"
                
        except Exception as e:
            logger.error(f"Formatting error: {e}")
            return f"❌ Error formatting {event_type}"

    @staticmethod
    def _format_trade(timestamp: str, data: Dict) -> str:
        # Wrapper handling
        trade_data = data.get('data', [])
        if isinstance(trade_data, list) and trade_data:
            trade = trade_data[0]
        else:
            return f"📈 [{timestamp}] Trade (Empty)"
            
        updated_data = trade.get('updatedData', {})
        ticker = updated_data.get('ticker', 'UNKNOWN')
        name = updated_data.get('name', 'Unknown')
        
        sol_amount = trade.get('solAmount', '0')
        market_cap = trade.get('marketCap', '0')
        is_buy = trade.get('isBuy', True)
        
        # Format values
        try:
            sol_amount_num = abs(float(sol_amount)) if sol_amount else 0.0
            sol_fmt = f"{sol_amount_num:.6f}"
        except:
            sol_fmt = "0.000000"
            
        try:
            mc_num = float(market_cap) if market_cap else 0.0
            mc_fmt = f"${mc_num:,.2f}"
        except:
            mc_fmt = "$0.00"
            
        action = "🟢 BUY" if is_buy else "🔴 SELL"
        name_short = name[:20] + "..." if len(name) > 20 else name
        
        return f"{action} [{timestamp}] {ticker} ({name_short}) | 💰 {sol_fmt} SOL | 💎 {mc_fmt}"

    @staticmethod
    def _format_new_coin(timestamp: str, data: Dict) -> str:
        coin = data.get('data', data) # Handle wrapper
        if not isinstance(coin, dict): return f"🪙 [{timestamp}] New Coin: Invalid format"
        
        name = coin.get('name', 'Unknown')
        ticker = coin.get('ticker', 'UNKNOWN')
        market_cap = coin.get('marketCap', 0)
        mint = coin.get('mint', 'N/A')
        
        try:
            mc_num = float(market_cap) if market_cap else 0.0
            mc_fmt = f"${mc_num:,.2f}"
        except:
            mc_fmt = "$0.00"
            
        mint_short = mint[:8] + "..." if len(mint) > 8 else mint
        name_short = name[:25] + "..." if len(name) > 25 else name
        
        return f"🪙 [{timestamp}] New: {ticker} ({name_short}) | 💎 {mc_fmt} | 🏠 {mint_short}"

    @staticmethod
    def _format_new_coin_detailed(timestamp: str, data: Dict) -> str:
        coin = data.get('data', data)
        if not isinstance(coin, dict): return f"🪙✨ [{timestamp}] Detailed: Invalid format"
        
        symbol = coin.get('symbol', 'UNKNOWN')
        name = coin.get('name', 'Unknown')
        market_cap = coin.get('usd_market_cap', coin.get('market_cap', 0))
        creator = coin.get('creator', 'N/A')
        total_supply = coin.get('total_supply', 0)
        
        # Socials
        twitter = coin.get('twitter', '')
        website = coin.get('website', '')
        telegram = coin.get('telegram', '')
        
        try:
            mc_num = float(market_cap) if market_cap else 0.0
            mc_fmt = f"${mc_num:,.2f}"
        except:
            mc_fmt = "$0.00"
            
        try:
            supply_fmt = f"{int(total_supply):,}" if total_supply else "N/A"
        except:
            supply_fmt = str(total_supply)
            
        creator_short = creator[:8] + "..." if len(creator) > 8 else creator
        name_short = name[:20] + "..." if len(name) > 20 else name
        
        socials = []
        if twitter: socials.append("🐦")
        if website: socials.append("🌐")
        if telegram: socials.append("💬")
        social_icons = "".join(socials) if socials else ""
        
        return f"🪙✨ [{timestamp}] {symbol} ({name_short}) | 💎 {mc_fmt} | 👤 {creator_short} | 📊 {supply_fmt} {social_icons}"

    @staticmethod
    def _format_pump_trade(timestamp: str, data: Dict) -> str:
        trade_data = data.get('data', [])
        if isinstance(trade_data, list) and trade_data:
            trade = trade_data[0]
        else:
            return "🔄 PumpSwap (Empty)"
            
        updated_data = trade.get('updatedData', {})
        ticker = updated_data.get('ticker', 'UNKNOWN')
        name = updated_data.get('name', 'Unknown')
        volume = updated_data.get('volume', '0')
        
        sol_amount = trade.get('solAmount', '0')
        market_cap = trade.get('marketCap', '0')
        is_buy = trade.get('isBuy', True)
        
        try:
            sol_num = abs(float(sol_amount)) if sol_amount else 0.0
            sol_fmt = f"{sol_num:.6f}"
        except:
            sol_fmt = "0.000000"
            
        try:
            mc_num = float(market_cap) if market_cap else 0.0
            mc_fmt = f"${mc_num:,.2f}"
        except:
            mc_fmt = "$0.00"
            
        try:
            vol_num = float(volume) if volume else 0.0
            vol_fmt = f"{vol_num:,.2f}"
        except:
            vol_fmt = "0.00"
            
        action = "🟢 BUY" if is_buy else "🔴 SELL"
        name_short = name[:18] + "..." if len(name) > 18 else name
        
        return f"{action} [{timestamp}] 🔄 {ticker} ({name_short}) | 💰 {sol_fmt} SOL | 💎 {mc_fmt} | 📊 {vol_fmt} VOL"

    @staticmethod
    def _format_graduated(timestamp: str, data: Dict) -> str:
        coin = data.get('data', data)
        if not isinstance(coin, dict): return f"🎓 [{timestamp}] Graduated: Invalid format"
        
        name = coin.get('name', 'Unknown')
        ticker = coin.get('ticker', 'UNKNOWN')
        market_cap = coin.get('marketCap', 0)
        ath_mc = coin.get('allTimeHighMarketCap', 0)
        num_holders = coin.get('numHolders', 0)
        sniper_count = coin.get('sniperCount', 0)
        volume = coin.get('volume', 0)
        
        try:
            mc_num = float(market_cap) if market_cap else 0.0
            mc_fmt = f"${mc_num:,.2f}"
            ath_num = float(ath_mc) if ath_mc else 0.0
            ath_fmt = f"${ath_num:,.2f}"
            vol_num = float(volume) if volume else 0.0
            vol_fmt = f"{vol_num:,.2f}"
        except:
            mc_fmt = "$0.00"
            ath_fmt = "$0.00"
            vol_fmt = "0.00"
            
        name_short = name[:20] + "..." if len(name) > 20 else name
        sniper_warning = f"⚠️ {sniper_count} sniper" if sniper_count > 0 else ""
        
        return f"🎓 [{timestamp}] GRADUATED: {ticker} ({name_short}) | 💎 {mc_fmt} | 🏆 ATH: {ath_fmt} | 👥 {num_holders} | 📊 {vol_fmt} SOL {sniper_warning}"

    @staticmethod
    def format_raw_data(event_name: str, data: Dict[str, Any], indent: int = 2) -> str:
        """Format raw event data for debug display."""
        return f"📄 Raw Data ({event_name}): {json.dumps(data, ensure_ascii=False, indent=indent)}"
