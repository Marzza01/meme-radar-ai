"""Servidor Web Asíncrono para el Dashboard en Tiempo Real de Meme Radar AI.

Tecnología: aiohttp.web (Python 3 asíncrono, liviano y de alto rendimiento).
Puerto: 3000 (configurable con DASHBOARD_PORT)
Características:
- REST API completa para métricas, bitácora, tokens, wallets y 5 capas.
- WebSocket (/ws) para transmisión instantánea de nuevas alertas al navegador.
- Sirve estáticos con diseño profesional inspirado en Stakent (Awsmd).
"""

import os
import sys
import json
import re
import time
import asyncio
import datetime
from pathlib import Path
import aiohttp
from aiohttp import web

# Soporte UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
STATIC_DIR = Path(__file__).parent / "static"

sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "alertas"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "auditoria"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "bitacora"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "fomo"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "pumpfun"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "wallet_tracker"))

PORT = int(os.environ.get("DASHBOARD_PORT", 3000))

# Conjunto de clientes WebSocket activos
_ws_clients = set()
_start_time = time.time()


def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[DASHBOARD][{ts}] {msg}")


def _safe_json_response(data: dict, status: int = 200) -> web.Response:
    """Serializa un dict como JSON limpio, escapando caracteres Unicode problemáticos
    (como →, ✅, ⚠️) que pueden causar UnicodeEncodeError en Windows con cp1252.
    """
    try:
        body = json.dumps(data, ensure_ascii=True, default=str)
    except Exception:
        body = json.dumps({"success": False, "error": "Serialization error"}, ensure_ascii=True)
    return web.Response(
        body=body.encode("utf-8"),
        status=status,
        content_type="application/json",
        charset="utf-8"
    )


# ─────────────────────────────────────────────
# Endpoints REST API
# ─────────────────────────────────────────────

async def handle_index(request):
    """Sirve la página principal del dashboard."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return web.Response(text="Dashboard frontend no encontrado en static/index.html", status=404)
    return web.FileResponse(index_file)


async def api_status(request):
    """Devuelve el estado general del sistema y los 3 hilos."""
    uptime_sec = int(time.time() - _start_time)
    hours, remainder = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours}h {minutes}m {seconds}s"

    # Verificar si hay estado de wallet tracker
    state_file = CONFIG_DIR / "wallet_tracker_state.json"
    tracker_active = state_file.exists()
    last_tracker_scan = "N/A"
    if tracker_active:
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                st = json.load(f)
                last_tracker_scan = st.get("last_scan", "N/A")[:16].replace("T", " ")
        except Exception:
            pass

    # Cargar aprendidos para umbral activo
    lw_file = CONFIG_DIR / "learned_weights.json"
    threshold = 65
    if lw_file.exists():
        try:
            with open(lw_file, "r", encoding="utf-8") as f:
                lw = json.load(f)
                threshold = lw.get("threshold_score", 65)
        except Exception:
            pass

    return web.json_response({
        "status": "online",
        "version": "2.2",
        "uptime": uptime_str,
        "threads": {
            "radar": {"name": "Motor de Convergencia", "status": "active", "interval": "300s"},
            "telegram": {"name": "Bot Interactivo @Marzza_meme_bot", "status": "active", "interval": "30s"},
            "tracker": {"name": "Solana Wallet Tracker", "status": "active", "interval": "15s", "last_scan": last_tracker_scan}
        },
        "threshold_score": threshold,
        "connected_ws": len(_ws_clients)
    })


async def api_alerts(request):
    """Devuelve las alertas registradas en la bitácora."""
    limit = int(request.query.get("limit", 40))
    from logger import get_recent_alerts
    try:
        alerts = get_recent_alerts(n=limit, days_back=7)
        return web.json_response({"success": True, "count": len(alerts), "alerts": alerts})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def api_tokens(request):
    """Devuelve la lista de tokens descubiertos por Smart Money."""
    disc_file = CONFIG_DIR / "discovered_tokens.json"
    if not disc_file.exists():
        return web.json_response({"tokens": []})
    try:
        with open(disc_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Convertir a lista ordenada por timestamp
        token_list = []
        for symbol, item in data.items():
            if isinstance(item, dict):
                item_copy = dict(item)
                item_copy["symbol"] = symbol
                token_list.append(item_copy)
        
        token_list.sort(key=lambda x: x.get("first_seen", ""), reverse=True)
        return web.json_response({"success": True, "count": len(token_list), "tokens": token_list})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def api_wallets(request):
    """Devuelve las wallets monitoreadas y las últimas transacciones on-chain."""
    sm_file = CONFIG_DIR / "smart_money.json"
    state_file = CONFIG_DIR / "wallet_tracker_state.json"
    
    wallets = []
    if sm_file.exists():
        try:
            with open(sm_file, "r", encoding="utf-8") as f:
                sm = json.load(f)
                for tier, tdata in sm.get("traders", {}).items():
                    weight = tdata.get("score_weight", 5)
                    for m in tdata.get("members", []):
                        for w in m.get("wallets", []):
                            wallets.append({
                                "handle": m.get("handle", ""),
                                "alias": m.get("alias", m.get("handle", "")),
                                "tier": tier,
                                "weight": weight,
                                "address": w,
                                "platform": m.get("platform", "pumpfun"),
                                "style": m.get("style", "smart-money")
                            })
        except Exception:
            pass

    return web.json_response({
        "success": True,
        "count": len(wallets),
        "wallets": wallets
    })


async def api_weights(request):
    """Devuelve los pesos de las 5 capas y ranking de traders aprendidos."""
    from learner import load_learned_weights
    try:
        w = load_learned_weights()
        # Eliminar campos pesados o con Unicode problemático (historial extenso)
        w_clean = {
            "layer_weights": w.get("layer_weights", {}),
            "trader_weights": w.get("trader_weights", {}),
            "threshold_score": w.get("threshold_score", 65),
            "signal_multipliers": w.get("signal_multipliers", {}),
            "updated_at": w.get("updated_at", ""),
        }
        return _safe_json_response({"success": True, "weights": w_clean})
    except Exception as e:
        return _safe_json_response({"success": False, "error": str(e)}, status=500)


async def api_stats(request):
    """Devuelve las estadísticas acumuladas del día y de los últimos 7 días."""
    from logger import get_daily_stats
    from reporter import get_last_n_days_stats
    try:
        today_stats = get_daily_stats()
        weekly_stats = get_last_n_days_stats(7)

        # Limpiar campos muy pesados para mantener la respuesta ligera
        def _trim_stats(s: dict) -> dict:
            return {
                "total":         s.get("total", 0),
                "tp":            s.get("tp", 0),
                "fp":            s.get("fp", 0),
                "partial":       s.get("partial", 0),
                "pending":       s.get("pending", 0),
                "accuracy":      s.get("accuracy", 0.0),
                "pnl_list":      s.get("pnl_list", []),
                "by_type":       s.get("by_type", {}),
                "by_signal_type": s.get("by_signal_type", {}),
                "by_layer":      s.get("by_layer", {}),
            }

        return _safe_json_response({
            "success": True,
            "today":   _trim_stats(today_stats),
            "weekly":  _trim_stats(weekly_stats)
        })
    except Exception as e:
        return _safe_json_response({"success": False, "error": str(e)}, status=500)


async def api_feedback(request):
    """Recibe feedback manual desde un botón del dashboard."""
    try:
        body = await request.json()
        alert_id = body.get("alert_id")
        outcome = body.get("outcome")
        notes = body.get("notes", "Web Dashboard Feedback")

        if not alert_id or not outcome:
            return web.json_response({"success": False, "error": "Faltan parámetros alert_id o outcome"}, status=400)

        from logger import set_feedback
        ok = set_feedback(alert_id, outcome, notes)
        
        # Notificar a los WebSockets conectados
        if ok:
            asyncio.create_task(broadcast_ws({
                "type": "feedback_applied",
                "alert_id": alert_id,
                "outcome": outcome
            }))

        return web.json_response({"success": ok})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def api_verify(request):
    """Ejecuta una verificación de alta convicción bajo demanda."""
    try:
        body = await request.json()
        query = body.get("query", "").lstrip("$").strip()
        if not query:
            return web.json_response({"success": False, "error": "Query requerida"}, status=400)

        result = {"query": query, "timestamp": datetime.datetime.now().isoformat()}

        # 1. DexScreener
        from fomo_tracker import FomoTracker
        ft = FomoTracker()
        mkt = ft.get_token_market_data(query)
        result["market"] = mkt

        # 2. three.ws Bonding Curve (Nivel 1)
        if mkt and mkt.get("address", "").endswith("pump"):
            try:
                from three_ws_client import three_ws
                b = three_ws.get_bonding_curve(mkt["address"])
                result["bonding_curve"] = b
            except Exception:
                pass

        # 3. Cope API (Nivel 2)
        try:
            from cope_client import cope_verifier, CopeQuotaManager
            if cope_verifier.is_configured() and CopeQuotaManager.can_make_call():
                c_res = cope_verifier.verify_token_smart_money(query)
                result["cope"] = c_res
            else:
                result["cope"] = {"verified": False, "reason": "No configurada o cupo diario preservado"}
        except Exception:
            pass

        return web.json_response({"success": True, "result": result})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


# ─────────────────────────────────────────────
# WebSockets para actualizaciones en tiempo real
# ─────────────────────────────────────────────

async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    _ws_clients.add(ws)
    log(f"Cliente WebSocket conectado (Total activos: {len(_ws_clients)})")

    try:
        # Enviar estado inicial inmediato al cliente conectado
        await ws.send_str(json.dumps({"type": "connection_established", "time": time.time()}))
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                # Si el cliente manda un ping o solicitud
                data = json.loads(msg.data)
                if data.get("action") == "ping":
                    await ws.send_str(json.dumps({"type": "pong", "time": time.time()}))
            elif msg.type == aiohttp.WSMsgType.ERROR:
                log(f"WebSocket cerrado con error: {ws.exception()}")
    finally:
        _ws_clients.remove(ws)
        log(f"Cliente WebSocket desconectado (Restantes: {len(_ws_clients)})")

    return ws


async def broadcast_ws(payload: dict):
    """Envía un mensaje a todos los navegadores conectados."""
    if not _ws_clients:
        return
    msg_str = json.dumps(payload)
    for ws in list(_ws_clients):
        try:
            await ws.send_str(msg_str)
        except Exception:
            _ws_clients.discard(ws)


# ─────────────────────────────────────────────
# Background Watcher (Monitorea nuevas alertas)
# ─────────────────────────────────────────────

async def background_bitacora_watcher():
    """Detecta nuevas alertas en config/bitacora/ y las empuja al WebSocket."""
    last_known_count = 0
    from logger import load_daily_log

    while True:
        try:
            entries = load_daily_log()
            current_count = len(entries)
            if current_count > last_known_count and last_known_count > 0:
                new_alerts = entries[last_known_count:]
                for alert in new_alerts:
                    log(f"Emitiendo nueva alerta a WebSockets: ${alert.get('token')} ({alert.get('id')})")
                    await broadcast_ws({
                        "type": "new_alert",
                        "alert": alert
                    })
            last_known_count = current_count
        except Exception as e:
            pass
        await asyncio.sleep(2.5)


async def init_app():
    app = web.Application()

    # Rutas API
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/alerts", api_alerts)
    app.router.add_get("/api/tokens", api_tokens)
    app.router.add_get("/api/wallets", api_wallets)
    app.router.add_get("/api/weights", api_weights)
    app.router.add_get("/api/stats", api_stats)
    app.router.add_post("/api/feedback", api_feedback)
    app.router.add_post("/api/verify", api_verify)
    app.router.add_get("/ws", ws_handler)

    # Servir archivos estáticos (CSS, JS, iconos)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.router.add_static("/static/", path=str(STATIC_DIR), name="static")

    # Iniciar background watcher
    asyncio.create_task(background_bitacora_watcher())

    return app


def start_server():
    log(f"Iniciando Meme Radar Web Dashboard en http://localhost:{PORT}")
    app = init_app()
    web.run_app(app, host="0.0.0.0", port=PORT, access_log=None)


if __name__ == "__main__":
    start_server()
