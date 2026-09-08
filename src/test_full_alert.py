"""Test completo: obtener datos de PONS y enviar alerta real a Telegram."""
import sys
sys.path.insert(0, r"c:\Users\marce\OneDrive\Documentos\Proyectos_AI\meme-radar-ai\src\fomo")
sys.path.insert(0, r"c:\Users\marce\OneDrive\Documentos\Proyectos_AI\meme-radar-ai\src\alertas")

from fomo_tracker import FomoTracker
from telegram_bot import send_radar_alert

tracker = FomoTracker()
data = tracker.get_token_market_data("PONS")

if data:
    print("Datos de PONS obtenidos:")
    for k, v in data.items():
        print(f"  {k}: {v}")
    print()

    result = send_radar_alert(
        asset=data["asset"],
        chain=data["chain"],
        score=72,
        signals=[
            "Market Cap > $500M",
            "Liquidity $8M+",
            "Volume activo en ultimos 5m"
        ],
        metrics={
            "market_cap": data["market_cap"],
            "liquidity": data["liquidity"],
            "volume_5m": data["volume_5m"]
        },
        audit={
            "contract": data["address"][:10] + "..." + data["address"][-6:],
            "risk": "MEDIO - Verificar manualmente"
        },
        actions={
            "DexScreener": data["pair_url"],
            "Comprar": f"https://app.uniswap.org/#/swap?outputCurrency={data['address']}"
        }
    )
    print("Alerta enviada a Telegram:", result)
else:
    print("No se pudieron obtener datos de PONS")
