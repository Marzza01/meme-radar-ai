"""Módulo de rastreo de Smart Money y datos de FOMO.

Monitorea la actividad de los Top Traders clave (Unipcs, DumbCrayonEater, Salem, etc.)
y proporciona el conector para detectar compras en tiempo real.
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from typing import List, Dict, Optional

# Soporte UTF-8 en consola de Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Lista de Top Traders prioritarios mapeados en tu ecosistema
TOP_TRADERS = {
    "theunipcs": {"alias": "Unipcs", "role": "Top 1 FOMO", "pnl": "+$10M"},
    "DumbCrayonEater": {"alias": "DumbCrayonEater", "role": "Legendary Trader", "pnl": "+$8.8M"},
    "Salem1299534": {"alias": "Salem", "role": "Market Maker", "pnl": "+$5M"},
    "brrrgrrrz": {"alias": "Burgz", "role": "Market Maker", "pnl": "+$4M"},
    "Natan_benish": {"alias": "Nate", "role": "Top Trader", "pnl": "+$3M"},
    "AvgJoesCrypto": {"alias": "AJC", "role": "KOL / Trader", "pnl": "+$2M"},
    "changefomo": {"alias": "change", "role": "Market Maker", "pnl": "+$3M"}
}


class FomoTracker:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.environ.get("COPE_API_KEY", "")
        self.base_url = base_url or os.environ.get("COPE_BASE_URL", "https://api.mobula.io/api/1")
        self.headers = {
            "User-Agent": "MemeRadar/1.0",
            "Accept": "application/json"
        }
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    def get_token_market_data(self, token_address_or_symbol: str) -> Optional[Dict]:
        """Obtiene datos de liquidez, volumen y market cap vía DexScreener (API pública gratuita)."""
        clean_query = token_address_or_symbol.replace("$", "").strip()
        url = f"https://api.dexscreener.com/latest/dex/search?q={urllib.parse.quote(clean_query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "MemeRadar/1.0"})
        
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                pairs = data.get("pairs", [])
                if not pairs:
                    return None
                
                # Seleccionar el par con mayor liquidez
                pairs.sort(key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0), reverse=True)
                top_pair = pairs[0]
                
                mcap = top_pair.get("fdv") or top_pair.get("marketCap") or 0
                liq = top_pair.get("liquidity", {}).get("usd", 0) or 0
                vol_5m = top_pair.get("volume", {}).get("m5", 0) or 0
                price_usd = top_pair.get("priceUsd", "0")
                chain_id = top_pair.get("chainId", "unknown")
                
                return {
                    "asset": top_pair.get("baseToken", {}).get("symbol", clean_query),
                    "chain": chain_id,
                    "address": top_pair.get("baseToken", {}).get("address", ""),
                    "price_usd": f"${float(price_usd):.6f}" if float(price_usd) < 1 else f"${float(price_usd):.2f}",
                    "market_cap": f"${mcap:,.0f}",
                    "liquidity": f"${liq:,.0f}",
                    "volume_5m": f"${vol_5m:,.0f}",
                    "pair_url": top_pair.get("url", "")
                }
        except Exception as e:
            print(f"Error al consultar DexScreener: {e}")
            return None


if __name__ == "__main__":
    tracker = FomoTracker()
    print("Probando consulta de mercado para $PONS...")
    data = tracker.get_token_market_data("PONS")
    if data:
        print("✅ Datos obtenidos correctamente:")
        for k, v in data.items():
            print(f"   • {k}: {v}")
    else:
        print("No se encontraron pares.")
