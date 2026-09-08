"""Script de Verificación General y Diagnóstico Pre-Vuelo para Meme Radar AI."""

import os
import sys
import json
import ssl
import time
import urllib.request
from pathlib import Path

# Soporte UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "alertas"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "auditoria"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "bitacora"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "fomo"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "pumpfun"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "wallet_tracker"))

# Cargar .env
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

report = []

def check(name, success, details=""):
    icon = "✅" if success else "❌"
    status_str = f"{icon} [{name}]: {details}"
    print(status_str)
    report.append((name, success, details))

print("\n" + "=" * 60)
print("  MEME RADAR AI — VERIFICACIÓN GENERAL PRE-VUELO")
print("=" * 60 + "\n")

# 1. Configs y Archivos Base
print("--- [1/6] ESTRUCTURA DE CONFIGURACIÓN ---")
wm_path = PROJECT_ROOT / "config" / "watchlist.json"
sm_path = PROJECT_ROOT / "config" / "smart_money.json"
lw_path = PROJECT_ROOT / "config" / "learned_weights.json"

check("Watchlist Config", wm_path.exists(), f"Existe en {wm_path.name}")
check("Smart Money Config", sm_path.exists(), f"Existe en {sm_path.name}")
check("Learned Weights", lw_path.exists(), f"Existe en {lw_path.name}")

if sm_path.exists():
    try:
        with open(sm_path, "r", encoding="utf-8") as f:
            sm_data = json.load(f)
            priority = sm_data.get("priority_handles", [])
            check("Traders Mapeados", len(priority) > 0, f"{len(priority)} priority traders en radar")
    except Exception as e:
        check("Traders Mapeados", False, str(e))

# 2. Conectividad Telegram
print("\n--- [2/6] TELEGRAM ALERTING & BOT ---")
bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
check("Telegram Bot Token", bool(bot_token and ":" in bot_token), f"Configurado ({bot_token[:8]}...)")
check("Telegram Chat ID", bool(chat_id), f"Configurado (ID: {chat_id})")

if bot_token:
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        req = urllib.request.Request(url, headers={"User-Agent": "MemeRadar/2.2"})
        with urllib.request.urlopen(req, context=ctx, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                username = data["result"].get("username", "Unknown")
                check("Telegram API Connect", True, f"Conectado a bot @{username}")
            else:
                check("Telegram API Connect", False, data.get("description", "Error"))
    except Exception as e:
        check("Telegram API Connect", False, f"Fallo al contactar Telegram: {e}")

# 3. Conexiones On-Chain (DexScreener, RugCheck, Solana RPC)
print("\n--- [3/6] CONECTIVIDAD DE DATOS (NIVEL 1 GRATIS) ---")

# DexScreener
try:
    url = "https://api.dexscreener.com/latest/dex/search?q=SOL"
    req = urllib.request.Request(url, headers={"User-Agent": "MemeRadar/2.2"})
    with urllib.request.urlopen(req, timeout=6) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        pairs = data.get("pairs", [])
        check("DexScreener API", len(pairs) > 0, f"Respuesta correcta ({len(pairs)} pares)")
except Exception as e:
    check("DexScreener API", False, str(e))

# RugCheck
try:
    from rugcheck import audit_token
    # Probar con mint de token conocido en Solana (ej. BONK)
    res = audit_token("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263")
    check("RugCheck API", res.get("success", False), f"Risk rating: {res.get('risk_rating','?')} | Score: {res.get('score','?')}")
except Exception as e:
    check("RugCheck API", False, str(e))

# Solana RPC (Wallet Tracker)
try:
    from solana_tracker import rpc_call
    bh = rpc_call("getLatestBlockhash", [])
    check("Solana Public RPC", bool(bh and "value" in bh), "RPC Solana conectado y respondiendo")
except Exception as e:
    check("Solana Public RPC", False, str(e))

# three.ws (Pump.fun launches/bonding)
try:
    from three_ws_client import three_ws
    launches = three_ws.get_recent_launches(limit=3, max_age_min=300)
    check("three.ws (Pump.fun)", len(launches) > 0, f"Obtenidos {len(launches)} tokens recientes de Pump.fun sin API Key")
except Exception as e:
    check("three.ws (Pump.fun)", False, str(e))

# 4. Bitácora y Aprendizaje Autónomo
print("\n--- [4/6] SISTEMA DE BITÁCORA Y APRENDIZAJE ---")
try:
    from logger import get_daily_stats
    from learner import load_learned_weights
    b_stats = get_daily_stats()
    check("Bitácora Diaria", True, f"{b_stats['total']} alertas registradas hoy ({b_stats['tp']} TP, {b_stats['fp']} FP)")
    
    lw = load_learned_weights()
    check("Aprendizaje Autónomo", "layer_weights" in lw, f"5 Capas calibradas: {list(lw.get('layer_weights',{}).keys())}")
except Exception as e:
    check("Bitácora / Aprendizaje", False, str(e))

# 5. Cope API Guard (Nivel 2)
print("\n--- [5/6] ESTADO NIVEL 2 (VERIFICADOR FRANCOTIRADOR) ---")
try:
    from cope_client import CopeQuotaManager, cope_verifier
    q = CopeQuotaManager.get_quota_status()
    is_cfg = cope_verifier.is_configured()
    check("Cope API (Nivel 2)", True, f"{'Activo con Key' if is_cfg else 'Modo Standby (Sin Key - Opcional)'} | Cupo: {q['used']}/{q['limit']} llamadas usadas")
except Exception as e:
    check("Cope API", False, str(e))

# 6. PM2 y Scripts de Arranque
print("\n--- [6/6] AUTOMATIZACIÓN 24/7 (PM2) ---")
eco_file = PROJECT_ROOT / "ecosystem.config.js"
start_bat = PROJECT_ROOT / "start_radar_24_7.bat"
check("ecosystem.config.js", eco_file.exists(), "Archivo de configuración de PM2 listo")
check("start_radar_24_7.bat", start_bat.exists(), "Script de lanzamiento en 1-click listo")

print("\n" + "=" * 60)
failures = [r for r in report if not r[1]]
if not failures:
    print("  🏆 RESULTADO: SISTEMA 100% OPERATIVO — LISTO PARA PRODUCCIÓN")
else:
    print(f"  ⚠️ RESULTADO: {len(failures)} ADVERTENCIA(S) DETECTADA(S)")
print("=" * 60 + "\n")
