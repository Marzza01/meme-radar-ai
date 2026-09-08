"""Cliente Cope API / FOMO — Nivel 2 (Verificación Francotirador de Alta Convicción).

USO RESTRINGIDO:
- NO se ejecuta en bucle continuo para proteger el límite gratuito de 250 llamadas/día.
- Solo se activa cuando:
    a) Una alerta supera un score de alta convicción (score >= 70).
    b) El usuario solicita verificación manual en Telegram con /verify.
- Gestiona cuota local persistente (config/cope_quota.json) con reinicio diario a medianoche UTC.
- Respeta la tasa de máx 10 solicitudes por minuto.
"""

import os
import sys
import json
import time
import datetime
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any

# Soporte UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).parent.parent.parent
QUOTA_FILE = PROJECT_ROOT / "config" / "cope_quota.json"

DEFAULT_BASE_URL = os.environ.get("COPE_BASE_URL", "https://api.mobula.io/api/1")
API_KEY = os.environ.get("COPE_API_KEY", "")

MAX_DAILY_CALLS = 220  # Techo de seguridad (reserva 30 llamadas del cupo de 250)
MAX_PER_MINUTE = 10


def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[COPE-VERIFIER][{ts}] {msg}")


class CopeQuotaManager:
    """Gestiona y audita el consumo de llamadas de la API para no quemar el cupo gratuito."""

    @staticmethod
    def _load() -> dict:
        if not QUOTA_FILE.exists():
            return {"date_utc": "", "calls_today": 0, "history": []}
        try:
            with open(QUOTA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"date_utc": "", "calls_today": 0, "history": []}

    @staticmethod
    def _save(data: dict):
        try:
            with open(QUOTA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log(f"Error guardando cuota: {e}")

    @classmethod
    def can_make_call(cls) -> bool:
        """Devuelve True si aún tenemos cupo disponible hoy."""
        today_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        data = cls._load()

        # Reinicio diario UTC
        if data.get("date_utc") != today_utc:
            data["date_utc"] = today_utc
            data["calls_today"] = 0
            cls._save(data)
            return True

        return data.get("calls_today", 0) < MAX_DAILY_CALLS

    @classmethod
    def register_call(cls, endpoint: str):
        """Incrementa el contador de llamadas realizadas."""
        today_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        data = cls._load()

        if data.get("date_utc") != today_utc:
            data["date_utc"] = today_utc
            data["calls_today"] = 0

        data["calls_today"] = data.get("calls_today", 0) + 1
        cls._save(data)
        log(f"Llamada registrada: {endpoint} | Uso hoy: {data['calls_today']}/{MAX_DAILY_CALLS}")

    @classmethod
    def get_quota_status(cls) -> dict:
        today_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        data = cls._load()
        if data.get("date_utc") != today_utc:
            return {"date_utc": today_utc, "used": 0, "limit": MAX_DAILY_CALLS, "remaining": MAX_DAILY_CALLS}
        used = data.get("calls_today", 0)
        return {
            "date_utc": today_utc,
            "used": used,
            "limit": MAX_DAILY_CALLS,
            "remaining": max(0, MAX_DAILY_CALLS - used)
        }


class CopeVerifier:
    """Cliente para verificaciones de alta convicción con protección estricta de cupo."""

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or os.environ.get("COPE_API_KEY", "")
        self.base_url = base_url or os.environ.get("COPE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self.last_calls = []  # Timestamps de llamadas en el último minuto

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 5)

    def _wait_rate_limit(self):
        """Asegura no exceder 10 llamadas por minuto."""
        now = time.time()
        self.last_calls = [t for t in self.last_calls if now - t < 60]
        if len(self.last_calls) >= MAX_PER_MINUTE:
            sleep_time = 60 - (now - self.last_calls[0]) + 0.5
            if sleep_time > 0:
                log(f"Rate limit de 10 req/min alcanzado, esperando {sleep_time:.1f}s...")
                time.sleep(sleep_time)
        self.last_calls.append(time.time())

    def _call(self, endpoint: str, params: dict = None) -> Optional[dict]:
        if not self.is_configured():
            log("Cope API Key no configurada en .env (modo simulación/desactivado).")
            return None

        if not CopeQuotaManager.can_make_call():
            status = CopeQuotaManager.get_quota_status()
            log(f"⚠️ CUPO DIARIO AGOTADO ({status['used']}/{status['limit']}). Preservando límite gratuito.")
            return None

        self._wait_rate_limit()

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if params:
            url += f"?{urllib.parse.urlencode(params)}"

        headers = {
            "User-Agent": "MemeRadarAI/2.2",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                CopeQuotaManager.register_call(endpoint)
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            log(f"HTTP Error {e.code} en Cope API ({endpoint}): {e.reason}")
        except Exception as e:
            log(f"Error consultando Cope API: {e}")
        return None

    def verify_token_smart_money(self, token_symbol_or_mint: str) -> Dict[str, Any]:
        """
        Reafirma si un token tiene acumulación activa de Smart Money según Cope.

        Returns:
            Dict con:
              - verified: bool
              - smart_money_holders: int
              - net_smart_flow: str
              - conviction_label: str
              - source: str
        """
        if not self.is_configured():
            return {
                "verified": False,
                "reason": "API_KEY_NOT_CONFIGURED",
                "message": "Cope API Key pendiente en .env. Se usó validación Nivel 1."
            }

        res = self._call("tokens", {"symbol": token_symbol_or_mint})
        if not res:
            return {"verified": False, "reason": "NO_DATA", "message": "Sin datos adicionales en Cope API."}

        data = res.get("data", res)
        sm_count = data.get("smart_money_holders", 0)
        flow = data.get("net_flow_24h", "N/A")

        return {
            "verified": True,
            "smart_money_holders": sm_count,
            "net_flow": flow,
            "conviction_label": "Alta" if sm_count >= 3 else ("Media" if sm_count >= 1 else "Baja"),
            "source": "Cope/FOMO API"
        }

    def verify_trader_activity(self, handle: str) -> Optional[dict]:
        """Consulta el leaderboard y actividad reciente de un top trader."""
        clean_handle = handle.lstrip("@").lower()
        res = self._call("activity", {"trader": clean_handle, "limit": 5})
        return res.get("data", res) if res else None


# Instancia singleton
cope_verifier = CopeVerifier()


if __name__ == "__main__":
    print("Estado del gestor de cuota de Cope API:")
    st = CopeQuotaManager.get_quota_status()
    print(f"  Fecha UTC:  {st['date_utc']}")
    print(f"  Consumo:    {st['used']} / {st['limit']} llamadas")
    print(f"  Restantes:  {st['remaining']} llamadas")
    print(f"  Configurado: {'SÍ' if cope_verifier.is_configured() else 'NO (Requiere COPE_API_KEY en .env)'}")
