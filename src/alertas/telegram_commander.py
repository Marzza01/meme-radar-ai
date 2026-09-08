"""Bot Interactivo de Telegram — Comandos bidireccionales para Meme Radar AI.

Permite controlar el sistema completo desde Telegram (móvil o escritorio):
  /scan [handle]       — Escanea un trader específico o todos los priority traders
  /smartmoney          — Lista todos los traders de Smart Money configurados
  /add @handle         — Agrega un nuevo trader a la lista de priority handles
  /remove @handle      — Elimina un trader de la lista de priority handles
  /status              — Estado actual del sistema y última actividad
  /tokens              — Lista los tokens descubiertos recientemente
  /wallets             — Lista las wallets trackeadas
  /help                — Muestra todos los comandos disponibles

Uso:
    python src/alertas/telegram_commander.py           # Modo polling (daemon)
    python src/alertas/telegram_commander.py --once    # Procesa mensajes pendientes y sale
"""

import os
import sys
import json
import time
import ssl
import datetime
import traceback
import urllib.request
import urllib.parse
from pathlib import Path

# Soporte UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "smart_money.json"
WATCHLIST_PATH = PROJECT_ROOT / "config" / "watchlist.json"
DISCOVERED_PATH = PROJECT_ROOT / "config" / "discovered_tokens.json"
TRACKER_STATE_PATH = PROJECT_ROOT / "config" / "wallet_tracker_state.json"
OFFSET_PATH = PROJECT_ROOT / "config" / "tg_bot_offset.json"

# Agregar módulos
sys.path.insert(0, str(PROJECT_ROOT / "src" / "x-mcp"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "fomo"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "alertas"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "auditoria"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "bitacora"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "pumpfun"))

# Cargar .env
ENV_FILE = PROJECT_ROOT / ".env"
if ENV_FILE.exists():
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


# ─────────────────────────────────────────────
# Helpers HTTP (sin dependencias externas)
# ─────────────────────────────────────────────

_ssl_ctx = None


def _get_ssl():
    global _ssl_ctx
    if _ssl_ctx:
        return _ssl_ctx
    try:
        ctx = ssl.create_default_context()
        _ssl_ctx = ctx
    except Exception:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _ssl_ctx = ctx
    return _ssl_ctx


def _api(method: str, params: dict = None, timeout: int = 20) -> dict:
    """Llama a la API de Telegram y devuelve el JSON resultante."""
    if not BOT_TOKEN:
        return {"ok": False, "description": "No BOT_TOKEN configurado"}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(params or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, context=_get_ssl(), timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "description": str(e)}


def get_updates(offset: int = None, timeout: int = 30) -> list:
    """Long-polling: obtiene actualizaciones desde Telegram."""
    params = {"timeout": timeout, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    result = _api("getUpdates", params, timeout=timeout + 5)
    if result.get("ok"):
        return result.get("result", [])
    return []


def send(chat_id, text: str, parse_mode: str = "Markdown") -> bool:
    """Envía un mensaje a un chat."""
    if len(text) > 4000:
        text = text[:3990] + "\n…(truncado)"
    result = _api("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    })
    return result.get("ok", False)


# ─────────────────────────────────────────────
# Gestión de Offset (persistencia entre reinicios)
# ─────────────────────────────────────────────

def load_offset() -> int:
    if OFFSET_PATH.exists():
        try:
            with open(OFFSET_PATH, "r") as f:
                return json.load(f).get("offset", 0)
        except Exception:
            pass
    return 0


def save_offset(offset: int):
    try:
        with open(OFFSET_PATH, "w") as f:
            json.dump({"offset": offset}, f)
    except Exception:
        pass


# ─────────────────────────────────────────────
# Carga de configuraciones
# ─────────────────────────────────────────────

def load_smart_money() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_smart_money(data: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_discovered() -> dict:
    if DISCOVERED_PATH.exists():
        with open(DISCOVERED_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_tracker_state() -> dict:
    if TRACKER_STATE_PATH.exists():
        with open(TRACKER_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def log(msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


# ─────────────────────────────────────────────
# Handlers de comandos
# ─────────────────────────────────────────────

def cmd_help(chat_id, _args):
    msg = """*MEME RADAR AI — Comandos*
────────────────────────────────────
*Escaneo y Discovery*
`/scan` — Escanea todos los priority traders
`/scan @handle` — Escanea un trader especifico
`/tokens` — Tokens descubiertos recientemente

*Smart Money y Wallets*
`/smartmoney` — Lista traders configurados
`/wallets` — Wallets trackeadas on-chain
`/add @handle alias` — Agrega trader
`/remove @handle` — Elimina trader
`/status` — Estado del sistema

*Bitácora y Aprendizaje (IA)*
`/feedback <id> true|false|partial` — Calificar alerta
`/report [YYYY-MM-DD]` — Informe diario (5 capas)
`/accuracy` — Precisión acumulada (capas y señales)
`/history [N]` — Ver últimas alertas con ID
`/weights` — Ver pesos y umbrales aprendidos

*Verificación Francotirador (Niveles 1 y 2)*
`/verify $TOKEN` — Verificar token on-chain y Smart Money
`/quota` — Consultar cupo restante de Cope API hoy

`/help` — Este menú
────────────────────────────────────
_Meme Radar AI v2.2_"""
    send(chat_id, msg)


def cmd_status(chat_id, _args):
    """Muestra el estado actual del sistema."""
    sm_data = load_smart_money()
    discovered = load_discovered()
    tracker = load_tracker_state()

    total_traders = 0
    priority_handles = sm_data.get("priority_handles", [])
    for tier_data in sm_data.get("traders", {}).values():
        total_traders += len(tier_data.get("members", []))

    last_discovery = "\u2014"
    if discovered:
        timestamps = [v.get("first_seen", "") for v in discovered.values() if isinstance(v, dict)]
        timestamps = [t for t in timestamps if t]
        if timestamps:
            last_discovery = sorted(timestamps)[-1][:16]

    wallets_in_state = tracker.get("wallets", {})
    n_wallets = len(wallets_in_state)
    last_scan = tracker.get("last_scan", "\u2014")

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    msg = (
        "*MEME RADAR // SYSTEM STATUS*\n"
        "\u2500" * 36 + "\n"
        f"*Estado:*        \U0001f7e2 Operativo\n"
        f"*Hora:*          `{now}`\n\n"
        "*Smart Money*\n"
        f"  Traders totales:  `{total_traders}`\n"
        f"  Priority handles: `{len(priority_handles)}`\n\n"
        "*Descubrimiento*\n"
        f"  Tokens en cache:  `{len(discovered)}`\n"
        f"  Ultimo discovery: `{last_discovery}`\n\n"
        "*Wallet Tracker*\n"
        f"  Wallets activas:  `{n_wallets}`\n"
        f"  Ultimo scan:      `{last_scan}`\n"
        "\u2500" * 36
    )
    send(chat_id, msg)


def cmd_smartmoney(chat_id, _args):
    """Lista todos los traders de Smart Money configurados."""
    sm_data = load_smart_money()
    traders_data = sm_data.get("traders", {})
    priority = [p.lower() for p in sm_data.get("priority_handles", [])]

    lines = ["*SMART MONEY \u2014 Traders*\n" + "\u2500" * 36]
    for tier_key, tier_info in traders_data.items():
        label = tier_info.get("label", tier_key)
        members = tier_info.get("members", [])
        weight = tier_info.get("score_weight", "?")
        lines.append(f"\n*{label}* (peso: {weight})")
        for m in members:
            handle = m.get("handle", "?")
            alias = m.get("alias", "")
            star = " \u2b50" if handle.lower() in priority else ""
            lines.append(f"  \u2022 `@{handle}` \u2014 {alias}{star}")

    lines.append(f"\n\u2b50 = Priority | Total: `{len(priority)}`")
    lines.append("\u2500" * 36)
    send(chat_id, "\n".join(lines))


def cmd_scan(chat_id, args):
    """Escanea un trader o todos los priority traders."""
    try:
        from smart_money_radar import (
            load_smart_money_config,
            scan_user_profiles,
            extract_signals_from_tweets,
            query_dexscreener,
        )
    except ImportError as e:
        send(chat_id, f"\u274c Error importando radar: `{e}`")
        return

    sm_data, priority_handles = load_smart_money_config()

    if args:
        target = args[0].lstrip("@").lower()
        handles_to_scan = [target]
        send(chat_id, f"\U0001f50d Escaneando `@{target}`... espera un momento.")
    else:
        if not priority_handles:
            send(chat_id, "\u26a0\ufe0f No hay priority handles. Usa `/add @handle alias`.")
            return
        handles_to_scan = priority_handles[:10]
        send(chat_id, f"\U0001f50d Escaneando `{len(handles_to_scan)}` priority traders... espera.")

    try:
        tweets = scan_user_profiles(handles_to_scan, max_tweets_per_user=3)
        token_mentions = extract_signals_from_tweets(tweets)

        if not token_mentions:
            send(chat_id, "\U0001f4ed No se encontraron menciones de tokens.")
            return

        sorted_tokens = sorted(token_mentions.items(), key=lambda x: x[1]["count"], reverse=True)
        top_tokens = sorted_tokens[:10]

        lines = [f"*SCAN \u2014 {len(handles_to_scan)} trader(s)*\n" + "\u2500" * 36]
        for token, data in top_tokens:
            count = data["count"]
            traders = ", ".join(list(data["traders"])[:3])
            ca_list = list(data.get("cas", set()))
            ca_str = f"\n    CA: `{ca_list[0][:8]}...{ca_list[0][-4:]}`" if ca_list else ""

            dex_info = ""
            if ca_list:
                try:
                    dex = query_dexscreener(ca=ca_list[0], ticker=token)
                    if dex and dex.get("price_usd"):
                        dex_info = f"\n    \U0001f4b0 ${dex.get('price_usd', '?')} | MC: {dex.get('market_cap', '?')}"
                except Exception:
                    pass

            lines.append(
                f"\n`${token}` \u2014 {count}x\n"
                f"    \U0001f464 {traders}{ca_str}{dex_info}"
            )

        lines.append("\n" + "\u2500" * 36 + "\n_Usa `/tokens` para ver descubrimientos_")
        send(chat_id, "\n".join(lines))

    except Exception as e:
        send(chat_id, f"\u274c Error durante el escaneo:\n`{str(e)[:200]}`")


def cmd_tokens(chat_id, _args):
    """Muestra tokens descubiertos recientemente."""
    discovered = load_discovered()

    if not discovered:
        send(chat_id, "\U0001f4ed No hay tokens en cache. Usa `/scan` para descubrir nuevos.")
        return

    items = []
    for token, data in discovered.items():
        if isinstance(data, dict):
            items.append((token, data))
        else:
            items.append((token, {"first_seen": str(data), "traders": [], "count": 1}))

    items.sort(key=lambda x: x[1].get("first_seen", ""), reverse=True)
    top = items[:15]

    lines = [f"*TOKENS DESCUBIERTOS \u2014 {len(top)} recientes*\n" + "\u2500" * 36]
    for token, data in top:
        traders = data.get("traders", [])
        first_seen = data.get("first_seen", "?")[:16]
        count = data.get("count", 1)
        trader_str = ", ".join(str(t) for t in traders[:2]) if traders else "?"
        ca = data.get("contract", "")
        ca_str = f"\n    CA: `{ca[:8]}...{ca[-4:]}`" if ca and len(ca) > 12 else ""
        dex_link = f"\n    \U0001f517 [DexScreener](https://dexscreener.com/solana/{ca})" if ca else ""

        lines.append(
            f"\n`${token}` \u2014 {count}x\n"
            f"    \U0001f464 {trader_str}\n"
            f"    \U0001f550 {first_seen}{ca_str}{dex_link}"
        )

    lines.append("\n" + "\u2500" * 36)
    send(chat_id, "\n".join(lines))


def cmd_wallets(chat_id, _args):
    """Lista wallets trackeadas con estado."""
    tracker = load_tracker_state()
    wallets_state = tracker.get("wallets", {})

    # Si hay estado del tracker, mostrarlo
    if wallets_state:
        lines = [f"*WALLET TRACKER \u2014 {len(wallets_state)} wallets*\n" + "\u2500" * 36]
        for alias, w_data in list(wallets_state.items())[:20]:
            addr = w_data.get("address", alias)
            tx_count = w_data.get("tx_count", 0)
            short = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
            lines.append(f"\n\u2022 *{alias}*\n  `{short}` | txs: {tx_count}")
        lines.append("\n" + "\u2500" * 36)
        send(chat_id, "\n".join(lines))
        return

    # Fallback: leer wallets del smart_money.json
    sm_data = load_smart_money()
    all_wallets = []
    for tier_data in sm_data.get("traders", {}).values():
        for m in tier_data.get("members", []):
            for w in m.get("wallets", []):
                all_wallets.append({
                    "alias": m.get("alias", m.get("handle", "?")),
                    "handle": m.get("handle", "?"),
                    "address": w
                })

    if not all_wallets:
        send(chat_id, "\U0001f4ed No hay wallets configuradas aun.\n\nAgrega wallets en `config/smart_money.json`.")
        return

    lines = [f"*WALLETS CONFIGURADAS \u2014 {len(all_wallets)}*\n" + "\u2500" * 36]
    for w in all_wallets[:20]:
        addr = w["address"]
        short = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
        solscan = f"https://solscan.io/account/{addr}"
        lines.append(f"\n\u2022 `@{w['handle']}` ({w['alias']})\n  `{short}` \u2014 [Solscan]({solscan})")
    lines.append("\n" + "\u2500" * 36)
    send(chat_id, "\n".join(lines))


def cmd_add(chat_id, args):
    """Agrega un nuevo trader a priority handles."""
    if not args:
        send(chat_id, "\u26a0\ufe0f Uso: `/add @handle alias`\nEjemplo: `/add @cobratrader CobraTrader`")
        return

    handle = args[0].lstrip("@").lower()
    alias = " ".join(args[1:]) if len(args) > 1 else handle.capitalize()

    sm_data = load_smart_money()
    priority = sm_data.get("priority_handles", [])

    if handle in [p.lower() for p in priority]:
        send(chat_id, f"\u2139\ufe0f `@{handle}` ya esta en la priority list.")
        return

    priority.append(handle)
    sm_data["priority_handles"] = priority

    # Agregar al tier mas bajo si existe
    traders = sm_data.get("traders", {})
    tier_keys = list(traders.keys())
    tier_entry_key = None
    for k in tier_keys:
        if "3" in k or "otro" in k.lower() or "other" in k.lower() or k == tier_keys[-1]:
            tier_entry_key = k
            break

    if tier_entry_key:
        members = traders[tier_entry_key].get("members", [])
        existing = [m for m in members if m.get("handle", "").lower() == handle]
        if not existing:
            members.append({"handle": handle, "alias": alias, "platform": "x", "wallets": []})
            traders[tier_entry_key]["members"] = members
            sm_data["traders"] = traders

    save_smart_money(sm_data)
    log(f"[CMD] /add -> @{handle} ({alias}) agregado")
    send(chat_id, f"\u2705 `@{handle}` ({alias}) agregado a priority list.\n\nUsa `/scan @{handle}` para escanearlo.")


def cmd_remove(chat_id, args):
    """Elimina un trader de la priority list."""
    if not args:
        send(chat_id, "\u26a0\ufe0f Uso: `/remove @handle`\nEjemplo: `/remove @cobratrader`")
        return

    handle = args[0].lstrip("@").lower()
    sm_data = load_smart_money()
    priority = sm_data.get("priority_handles", [])
    new_priority = [p for p in priority if p.lower() != handle]

    if len(new_priority) == len(priority):
        send(chat_id, f"\u26a0\ufe0f `@{handle}` no esta en la priority list.")
        return

    sm_data["priority_handles"] = new_priority
    save_smart_money(sm_data)
    log(f"[CMD] /remove -> @{handle} eliminado")
    send(chat_id, f"🗑️ `@{handle}` eliminado de priority list.\n_Sigue en la DB de traders pero no se escaneará automáticamente._")


def cmd_feedback(chat_id, args):
    """
    /feedback <alert_id> <true|false|partial> [notas]
    Registra el feedback del usuario sobre una alerta para aprendizaje continuo.
    """
    if len(args) < 2:
        send(chat_id, "⚠️ *Uso:* `/feedback <id_alerta> <true|false|partial> [notas]`\n\n*Ejemplo:*\n`/feedback cnv_20260906_BONK_1234 true fue buen call x3`\n\n_Puedes consultar IDs con `/history`._")
        return

    alert_id = args[0]
    raw_outcome = args[1].lower()
    notes = " ".join(args[2:]) if len(args) > 2 else ""

    outcome_map = {
        "true": "true_positive",
        "tp": "true_positive",
        "cierto": "true_positive",
        "false": "false_positive",
        "fp": "false_positive",
        "falso": "false_positive",
        "partial": "partial",
        "medio": "partial"
    }

    outcome = outcome_map.get(raw_outcome)
    if not outcome:
        send(chat_id, "⚠️ Resultado inválido. Usa `true`, `false` o `partial`.")
        return

    try:
        from logger import set_feedback
        ok = set_feedback(alert_id, outcome, notes)
        if ok:
            icon = "✅" if outcome == "true_positive" else ("❌" if outcome == "false_positive" else "⚠️")
            send(chat_id, f"{icon} *Feedback registrado exitosamente*\n\n• Alerta: `{alert_id}`\n• Resultado: `{outcome}`\n• Notas: {notes or 'Ninguna'}\n\n_Este feedback optimizará los pesos de capas y traders hoy a las 23:55._")
        else:
            send(chat_id, f"❌ No se encontró ninguna alerta con ID `{alert_id}` en los últimos 5 días.\nUsa `/history` para ver IDs recientes.")
    except Exception as e:
        send(chat_id, f"❌ Error guardando feedback: {e}")


def cmd_report(chat_id, args):
    """
    /report [YYYY-MM-DD]
    Genera y envía el informe del día con análisis de 5 capas.
    """
    target_date = None
    if args:
        try:
            target_date = datetime.date.fromisoformat(args[0])
        except Exception:
            send(chat_id, "⚠️ Fecha inválida. Usa formato `YYYY-MM-DD` (ej. `/report 2026-09-06`).")
            return

    send(chat_id, "⏳ Generando informe de bitácora con análisis de 5 capas...")
    try:
        from reporter import generate_daily_report
        report_md = generate_daily_report(date=target_date, send_telegram=False)
        if len(report_md) > 3800:
            for i in range(0, len(report_md), 3800):
                send(chat_id, report_md[i:i+3800])
        else:
            send(chat_id, report_md)
    except Exception as e:
        send(chat_id, f"❌ Error generando informe: {e}")


def cmd_accuracy(chat_id, _args):
    """
    /accuracy
    Muestra la precisión acumulada de los últimos 7 días con desglose por tipo de señal y 5 capas.
    """
    try:
        from logger import get_multi_day_entries
        entries = get_multi_day_entries(days_back=7)

        if not entries:
            send(chat_id, "ℹ️ No hay alertas registradas en los últimos 7 días.")
            return

        evaluated = [e for e in entries if e.get("outcome")]
        tp = sum(1 for e in evaluated if e.get("outcome") == "true_positive")
        fp = sum(1 for e in evaluated if e.get("outcome") == "false_positive")
        partial = sum(1 for e in evaluated if e.get("outcome") == "partial")

        acc = round((tp + 0.5 * partial) / max(len(evaluated), 1) * 100, 1)

        lines = [
            "*PRECISIÓN ACUMULADA (ÚLTIMOS 7 DÍAS)*",
            "─" * 36,
            f"Alertas totales:   `{len(entries)}`",
            f"Evaluadas:         `{len(evaluated)}`",
            f"Precisión global:  `{acc}%` (✅{tp} ❌{fp} ⚠️{partial})",
            "",
            "*Por Tipo de Señal:*"
        ]

        # Por señal
        by_type = {}
        for e in evaluated:
            st = e.get("signal_type", e.get("type", "convergence"))
            by_type.setdefault(st, {"tp": 0, "fp": 0, "partial": 0})
            if e.get("outcome") == "true_positive":
                by_type[st]["tp"] += 1
            elif e.get("outcome") == "false_positive":
                by_type[st]["fp"] += 1
            elif e.get("outcome") == "partial":
                by_type[st]["partial"] += 1

        for st, sd in by_type.items():
            ev = sd["tp"] + sd["fp"] + sd["partial"]
            st_acc = round((sd["tp"] + 0.5 * sd["partial"]) / max(ev, 1) * 100, 1)
            icon = "🟢" if st_acc >= 70 else ("🟡" if st_acc >= 40 else "🔴")
            lines.append(f"{icon} `{st}`: {st_acc}% ({sd['tp']}/{ev} aciertos)")

        # Por capa (5 capas)
        lines.append("\n*Por Capa de Análisis (5 Capas):*")
        by_layer = {}
        for e in evaluated:
            for lyr in e.get("layers", []):
                by_layer.setdefault(lyr, {"tp": 0, "fp": 0, "partial": 0})
                if e.get("outcome") == "true_positive":
                    by_layer[lyr]["tp"] += 1
                elif e.get("outcome") == "false_positive":
                    by_layer[lyr]["fp"] += 1
                elif e.get("outcome") == "partial":
                    by_layer[lyr]["partial"] += 1

        for lyr, ld in sorted(by_layer.items(), key=lambda x: (x[1]["tp"] + 0.5 * x[1]["partial"]) / max(x[1]["tp"] + x[1]["fp"] + x[1]["partial"], 1), reverse=True):
            ev = ld["tp"] + ld["fp"] + ld["partial"]
            l_acc = round((ld["tp"] + 0.5 * ld["partial"]) / max(ev, 1) * 100, 1)
            l_icon = "✅" if l_acc >= 70 else ("⚠️" if l_acc >= 40 else "❌")
            lines.append(f"{l_icon} Capa `{lyr}`: {l_acc}% ({ld['tp']}/{ev})")

        lines.append("─" * 36)
        send(chat_id, "\n".join(lines))
    except Exception as e:
        send(chat_id, f"❌ Error calculando precisión: {e}")


def cmd_history(chat_id, args):
    """
    /history [N]
    Muestra las últimas N alertas registradas con ID para feedback.
    """
    n = 10
    if args:
        try:
            n = min(25, int(args[0]))
        except Exception:
            pass

    try:
        from logger import get_recent_alerts
        recent = get_recent_alerts(n=n, days_back=5)

        if not recent:
            send(chat_id, "ℹ️ No hay alertas registradas en la bitácora aún.")
            return

        lines = [f"*ÚLTIMAS {len(recent)} ALERTAS (BITÁCORA)*\n" + "─" * 36]
        for a in recent:
            ts = a.get("timestamp", "")[11:16]
            tok = a.get("token", "?")
            sc = a.get("score", "?")
            st = a.get("signal_type", a.get("type", "cnv"))
            out = a.get("outcome")
            icon = "✅" if out == "true_positive" else ("❌" if out == "false_positive" else ("⚠️" if out == "partial" else "⏳"))
            aid = a.get("id", "?")
            pnl = a.get("pnl_pct")
            pnl_str = f" | {pnl:+.1f}%" if pnl is not None else ""
            lines.append(f"\n{icon} `[{ts}]` *${tok}* (score:{sc}, {st}){pnl_str}\n  ID: `{aid}`")

        lines.append("\n" + "─" * 36)
        lines.append("_Para evaluar: `/feedback <ID> true|false|partial`_")
        send(chat_id, "\n".join(lines))
    except Exception as e:
        send(chat_id, f"❌ Error obteniendo historial: {e}")


def cmd_weights(chat_id, _args):
    """
    /weights
    Muestra los pesos aprendidos actuales (capas, traders, umbrales).
    """
    try:
        from learner import load_learned_weights
        w = load_learned_weights()

        layer_w = w.get("layer_weights", {})
        l_lines = [f"• `{k}`: {v} pts" for k, v in layer_w.items()]

        mults = w.get("signal_multipliers", {})
        m_lines = [f"• `{k}`: {v}x" for k, v in mults.items()]

        traders = w.get("trader_weights", {})
        top_t = sorted(traders.items(), key=lambda x: x[1], reverse=True)[:6]
        t_lines = [f"• `@{k}`: {v} pts" for k, v in top_t]

        msg = (
            f"*PESOS ACTIVOS (APRENDIZAJE AUTÓNOMO)*\n"
            f"─" * 36 + "\n"
            f"*Umbral de Alerta:* `{w.get('threshold_score', 65)}/100`\n"
            f"*Última calibración:* `{w.get('updated_at', 'N/A')[:16]}`\n\n"
            f"*Pesos por Capa (5 Capas):*\n" + "\n".join(l_lines) + "\n\n"
            f"*Multiplicadores de Señal:*\n" + "\n".join(m_lines) + "\n\n"
            f"*Top Traders Calibrados:*\n" + "\n".join(t_lines) + "\n"
            f"─" * 36 + "\n"
            f"_Ajustados automáticamente cada noche a las 23:55._"
        )
        send(chat_id, msg)
    except Exception as e:
        send(chat_id, f"❌ Error leyendo pesos: {e}")


def cmd_quota(chat_id, _args):
    """
    /quota
    Muestra el estado del presupuesto de llamadas de Cope API (Nivel 2).
    """
    try:
        from cope_client import CopeQuotaManager, cope_verifier
        st = CopeQuotaManager.get_quota_status()
        cfg_str = "✅ Configurada" if cope_verifier.is_configured() else "⚠️ Pendiente en .env"

        msg = (
            f"*CUPO DE VERIFICACIÓN (COPE API / NIVEL 2)*\n"
            f"─" * 36 + "\n"
            f"*Estado API:* `{cfg_str}`\n"
            f"*Fecha UTC:*  `{st['date_utc']}`\n"
            f"*Consumidas:* `{st['used']} / {st['limit']}` llamadas hoy\n"
            f"*Disponibles:* `{st['remaining']}` llamadas restantes\n"
            f"─" * 36 + "\n"
            f"_El cupo se reinicia a medianoche UTC (250 llamadas diarias gratis)._"
        )
        send(chat_id, msg)
    except Exception as e:
        send(chat_id, f"❌ Error leyendo cuota: {e}")


def cmd_verify(chat_id, args):
    """
    /verify <token_o_mint>
    Ejecuta una verificación de alta convicción bajo demanda combinando Nivel 1 (Pump.fun) y Nivel 2 (Cope API).
    """
    if not args:
        send(chat_id, "⚠️ *Uso:* `/verify $TOKEN` o `/verify <MINT_ADDRESS>`\n*Ejemplo:* `/verify BONK`")
        return

    query = args[0].lstrip("$").strip()
    send(chat_id, f"🔍 *Verificando ${query.upper()} en Nivel 1 (three.ws/Dex) y Nivel 2 (Cope API)...*")

    lines = [f"*REPORTE DE VERIFICACIÓN // ${query.upper()}*", "─" * 36]

    # 1. Datos on-chain (DexScreener)
    try:
        from fomo_tracker import FomoTracker
        ft = FomoTracker()
        mkt = ft.get_token_market_data(query)
        if mkt:
            lines.append(f"*Market Cap:* `{mkt.get('market_cap','N/A')}` | *Liq:* `{mkt.get('liquidity','N/A')}`")
            lines.append(f"*Precio:* `{mkt.get('price_usd','N/A')}` | *Vol 5m:* `{mkt.get('volume_5m','N/A')}`")
            mint_addr = mkt.get("address", "")
            if mint_addr.endswith("pump"):
                # Nivel 1: Pump.fun Curva vía three.ws
                try:
                    from three_ws_client import three_ws
                    b = three_ws.get_bonding_curve(mint_addr)
                    if b and b.get("progress_pct"):
                        lines.append(f"*Curva Pump.fun:* `{b.get('progress_pct', 0)}%` ({b.get('sol_in_curve', 0)} SOL)")
                        if b.get("progress_pct", 0) >= 80:
                            lines.append("🔥 *¡Próximo a graduar a Raydium (+80%)!*")
                except Exception:
                    pass
    except Exception as e:
        log(f"Error verificando mercado: {e}")

    # 2. Verificación Nivel 2 (Cope API Smart Money)
    try:
        from cope_client import cope_verifier, CopeQuotaManager
        if not cope_verifier.is_configured():
            lines.append("\n*Cope API (Nivel 2):* ⚠️ `COPE_API_KEY` pendiente en .env (solo Nivel 1 activo)")
        elif not CopeQuotaManager.can_make_call():
            lines.append("\n*Cope API (Nivel 2):* ⚠️ Cupo diario agotado hoy. Preservando límite gratuito.")
        else:
            c_res = cope_verifier.verify_token_smart_money(query)
            if c_res.get("verified"):
                holders = c_res.get("smart_money_holders", 0)
                conv = c_res.get("conviction_label", "Baja")
                lines.append(f"\n*Cope Smart Money:* ✅ `{holders} holders élite` (Convicción: *{conv}*)")
                if c_res.get("net_flow"):
                    lines.append(f"*Flujo Neto 24h:* `{c_res['net_flow']}`")
            else:
                lines.append(f"\n*Cope API:* {c_res.get('message', 'Sin datos adicionales')}")

        # Cuota restante
        q = CopeQuotaManager.get_quota_status()
        lines.append(f"\n_Cuota Cope hoy: {q['used']}/{q['limit']} llamadas usadas._")
    except Exception as ce:
        lines.append(f"\n*Error Cope:* `{ce}`")

    lines.append("─" * 36)
    send(chat_id, "\n".join(lines))


# ─────────────────────────────────────────────
# Router de comandos
# ─────────────────────────────────────────────

COMMANDS = {
    "/help":        cmd_help,
    "/start":       cmd_help,
    "/status":      cmd_status,
    "/smartmoney":  cmd_smartmoney,
    "/scan":        cmd_scan,
    "/tokens":      cmd_tokens,
    "/wallets":     cmd_wallets,
    "/add":         cmd_add,
    "/remove":      cmd_remove,
    "/feedback":    cmd_feedback,
    "/report":      cmd_report,
    "/accuracy":    cmd_accuracy,
    "/history":     cmd_history,
    "/weights":     cmd_weights,
    "/quota":       cmd_quota,
    "/verify":      cmd_verify,
}


def process_update(update: dict):
    """Procesa un update de Telegram y despacha el comando correspondiente."""
    message = update.get("message", {})
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    from_user = message.get("from", {})
    sender_id = str(from_user.get("id", ""))
    text = message.get("text", "").strip()

    if not chat_id or not text or not text.startswith("/"):
        return

    # Verificar que sea el admin
    if ADMIN_CHAT_ID and sender_id != ADMIN_CHAT_ID and str(chat_id) != ADMIN_CHAT_ID:
        send(chat_id, "\U0001f512 Acceso denegado. Este bot es privado.")
        log(f"[SECURITY] Mensaje rechazado de chat_id={chat_id}, sender={sender_id}")
        return

    parts = text.split()
    raw_cmd = parts[0].split("@")[0].lower()
    args = parts[1:] if len(parts) > 1 else []

    username = from_user.get("username", from_user.get("first_name", "User"))
    log(f"[CMD] {raw_cmd} de @{username} | args={args}")

    handler = COMMANDS.get(raw_cmd)
    if handler:
        try:
            handler(chat_id, args)
        except Exception as e:
            log(f"[ERROR] Handler {raw_cmd}: {e}")
            send(chat_id, f"\u274c Error ejecutando `{raw_cmd}`:\n`{str(e)[:200]}`")
    else:
        available = " ".join(f"`{c}`" for c in sorted(COMMANDS.keys()))
        send(chat_id, f"\u2753 Comando no reconocido: `{raw_cmd}`\n\nDisponibles:\n{available}")


# ─────────────────────────────────────────────
# Loop principal de polling
# ─────────────────────────────────────────────

def run_polling(poll_once: bool = False):
    """Inicia el polling de mensajes de Telegram."""
    if not BOT_TOKEN:
        print("\u274c TELEGRAM_BOT_TOKEN no configurado en .env")
        sys.exit(1)
    if not ADMIN_CHAT_ID:
        print("\u26a0\ufe0f TELEGRAM_CHAT_ID no configurado — bot acepta mensajes de cualquier chat")

    offset = load_offset()
    log(f"\u2705 Bot Interactivo iniciado | offset={offset} | admin_chat={ADMIN_CHAT_ID}")

    # Anunciar inicio al admin
    if ADMIN_CHAT_ID:
        startup_msg = (
            "*MEME RADAR AI \u2014 Bot Online* \U0001f7e2\n"
            "\u2500" * 36 + "\n"
            "Bot interactivo conectado y listo.\n"
            "Usa `/help` para ver los comandos disponibles."
        )
        send(ADMIN_CHAT_ID, startup_msg)

    consecutive_errors = 0

    while True:
        try:
            updates = get_updates(offset=offset if offset > 0 else None, timeout=30)

            for update in updates:
                update_id = update.get("update_id", 0)
                try:
                    process_update(update)
                except Exception as e:
                    log(f"[ERROR] Procesando update {update_id}: {e}")
                finally:
                    if update_id >= offset:
                        offset = update_id + 1
                        save_offset(offset)

            consecutive_errors = 0

            if poll_once:
                log("Modo --once: mensajes pendientes procesados.")
                break

        except KeyboardInterrupt:
            log("Bot detenido por usuario (Ctrl+C)")
            break
        except Exception as e:
            consecutive_errors += 1
            wait = min(30, 5 * consecutive_errors)
            log(f"[ERROR] Polling: {e} | reintentando en {wait}s")
            time.sleep(wait)
            if poll_once:
                break


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    once = "--once" in sys.argv
    run_polling(poll_once=once)
