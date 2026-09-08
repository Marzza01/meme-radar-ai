"""Cliente three.ws para Pump.fun — Nivel 1 (Gratuito 24/7 sin API Key).

Permite consultar:
1. /launches — Tokens recién nacidos en Pump.fun con filtros de market cap y edad.
2. /bonding  — Estado de la curva de enlace (progreso % hacia Raydium, SOL acumulado).
3. /whales   — Grandes compras de ballenas en Pump.fun (min SOL configurable).

Rate limit de three.ws: 60 solicitudes por minuto por IP.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
from typing import Optional, Dict, List

# Soporte UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_URL = os.environ.get("THREE_WS_BASE_URL", "https://three.ws/api/crypto")
HEADERS = {
    "User-Agent": "MemeRadarAI/2.2 (Agent/Autonomous)",
    "Accept": "application/json"
}


def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[THREE.WS][{ts}] {msg}")


def _http_get(endpoint: str, params: dict = None, timeout: int = 8) -> Optional[dict]:
    """Ejecuta una petición GET a three.ws con control de errores."""
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    if params:
        query_str = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{url}?{query_str}"

    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        log(f"HTTP {e.code} en {endpoint}: {e.reason}")
    except Exception as e:
        log(f"Error consultando {endpoint}: {e}")
    return None


class ThreeWsClient:
    """Cliente de acceso gratuito 24/7 a datos de Pump.fun vía three.ws."""

    def __init__(self):
        self.last_call_ts = 0.0
        self.min_interval = 1.0  # 1s entre llamadas para no superar 60 req/min

    def _rate_limit(self):
        elapsed = time.time() - self.last_call_ts
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call_ts = time.time()

    def get_recent_launches(self, limit: int = 20, min_mcap: float = 0, max_age_min: int = 60) -> List[Dict]:
        """
        Obtiene los lanzamientos más recientes en Pump.fun.

        Args:
            limit: Número de tokens a consultar (máx 100).
            min_mcap: Filtro de Market Cap mínimo en USD.
            max_age_min: Edad máxima en minutos.

        Returns:
            Lista de diccionarios con info de cada token lanzado.
        """
        self._rate_limit()
        params = {
            "limit": min(100, max(1, limit)),
            "minMarketCap": min_mcap if min_mcap > 0 else None,
            "maxAgeMin": max_age_min
        }
        res = _http_get("launches", params)
        if not res:
            return []

        # Normalizar respuesta (puede venir como lista directa o {data: [...]})
        if isinstance(res, list):
            return res
        return res.get("data", res.get("tokens", res.get("launches", [])))

    def get_bonding_curve(self, mint: str) -> Optional[Dict]:
        """
        Consulta el estado de la curva de enlace de un token específico.

        Returns:
            Dict con:
              - progress_pct: % completado hacia graduación a Raydium (0-100%)
              - sol_in_curve: SOL acumulados en la curva
              - market_cap: Market cap actual
              - is_graduated: True si ya migró a Raydium
        """
        if not mint or len(mint) < 32:
            return None

        self._rate_limit()
        params = {"mint": mint}
        res = _http_get("bonding", params)
        if not res:
            return None

        data = res if isinstance(res, dict) else {}
        # Normalizar claves comunes
        return {
            "mint": mint,
            "progress_pct": data.get("progress_pct") or data.get("progress") or data.get("bonding_curve_progress", 0),
            "sol_in_curve": data.get("sol_in_curve") or data.get("sol_reserves") or 0.0,
            "market_cap": data.get("market_cap") or data.get("usd_market_cap") or 0,
            "is_graduated": data.get("is_graduated") or data.get("complete", False),
            "raw": data
        }

    def get_whale_trades(self, min_sol: float = 1.0, limit: int = 15) -> List[Dict]:
        """
        Detecta grandes compras (ballenas) en Pump.fun.

        Args:
            min_sol: Cantidad mínima de SOL de la transacción (ej. 1.0 SOL, 5.0 SOL).
            limit: Número máximo de transacciones a retornar (máx 25).
        """
        self._rate_limit()
        params = {
            "minSol": max(0.1, min_sol),
            "limit": min(25, max(1, limit))
        }
        res = _http_get("whales", params)
        if not res:
            return []

        if isinstance(res, list):
            return res
        return res.get("data", res.get("trades", res.get("whales", [])))


# Instancia singleton para uso rápido
three_ws = ThreeWsClient()


if __name__ == "__main__":
    print("Probando conexión three.ws (Nivel 1 Gratuito)...")
    client = ThreeWsClient()
    launches = client.get_recent_launches(limit=5, max_age_min=120)
    print(f"Lanzamientos recientes obtenidos: {len(launches)}")
    if launches:
        for t in launches[:3]:
            print(f"  • ${t.get('symbol','?')} ({t.get('name','?')}) | MC: {t.get('market_cap','?')}")
    else:
        print("Endpoint three.ws sin respuesta o en fallback.")
