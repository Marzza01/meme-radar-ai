"""Módulo de envío de alertas a Telegram.

Utiliza la API oficial de Telegram vía HTTP (sin dependencias externas pesadas).
Permite enviar alertas estructuradas de alta prioridad directamente a tu chat.
"""

import os
import sys
import json
import ssl
import urllib.request
import urllib.parse
from pathlib import Path


_cached_ssl_ctx = None

def _get_ssl_context():
    """Obtiene y cachea un contexto SSL que funcione en el entorno actual."""
    global _cached_ssl_ctx
    if _cached_ssl_ctx is not None:
        return _cached_ssl_ctx

    try:
        ctx = ssl.create_default_context()
        urllib.request.urlopen("https://api.telegram.org", context=ctx, timeout=5)
        _cached_ssl_ctx = ctx
        return ctx
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _cached_ssl_ctx = ctx
        return ctx

# Soporte UTF-8 en consola de Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Cargar variables de entorno desde .env si existe
ENV_FILE = Path(__file__).parent.parent.parent / ".env"
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


def send_message(text: str, token: str = None, chat_id: str = None, retries: int = 2) -> bool:
    """Envía un mensaje de texto formateado a Telegram con reintentos."""
    bot_token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    target_chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not target_chat:
        print("❌ Error: Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID.")
        print("Configúralos en tu archivo .env o pásalos como argumentos.")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"}
    )

    for attempt in range(retries):
        try:
            ssl_ctx = _get_ssl_context()
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                if res_data.get("ok"):
                    return True
                else:
                    print(f"Error de Telegram API: {res_data}")
                    return False
        except urllib.error.HTTPError as e:
            err_content = e.read().decode("utf-8", errors="ignore")
            print(f"❌ Error HTTP de Telegram ({e.code}): {err_content}")
            return False
        except Exception as e:
            if attempt < retries - 1:
                import time
                time.sleep(1.5)
                continue
            print(f"❌ Error al conectar con Telegram: {e}")
            return False


def generate_actionable_plan(
    alert_type: str,  # "CONVERGENCE", "DISCOVERY", "COPYTRADE"
    score: int = None,
    audit: dict = None,
    metrics: dict = None,
    trader: str = None,
    action_type: str = None,
) -> str:
    """Genera un veredicto en lenguaje humano y un plan de acción concreto para principiantes."""
    audit = audit or {}
    metrics = metrics or {}

    risk_raw = str(audit.get("risk", "")).lower()
    honeypot_raw = str(audit.get("honeypot", "")).lower()
    auth_raw = str(audit.get("authorities", "")).lower()

    is_danger = (
        any(w in risk_raw for w in ["danger", "peligro", "rug", "malicioso"])
        or "yes" in honeypot_raw
        or "sí" in honeypot_raw
        or "si" in honeypot_raw
    )
    is_warning = (
        any(w in risk_raw for w in ["warning", "medio", "advertencia"])
        or "not revoked" in auth_raw
        or "activa" in auth_raw
    )

    if is_danger:
        badge = "🔴 *SEGURIDAD: PELIGRO CRÍTICO*"
        verdict = "⛔ *VEREDICTO: NO COMPRAR (Riesgo de Rugpull o Honeypot)*"
        explan = "• El contrato tiene alertas rojas: pueden bloquear ventas o robar liquidez."
        plan = "• *Plan sugerido:* NO entrar. Tu capital está a salvo no operando este token."
    elif alert_type == "COPYTRADE":
        is_buy = "BUY" in str(action_type).upper() or "COMPRA" in str(action_type).upper()
        if is_buy:
            badge = "🟢 *SEGURIDAD: AUDITADO*" if not is_warning else "🟡 *SEGURIDAD: PRECAUCIÓN*"
            verdict = "🟢 *VEREDICTO: COMPRA EN VIVO DE SMART MONEY*"
            explan = f"• La wallet elite `{trader or 'Smart Money'}` acaba de meter dinero real a este token."
            plan = (
                "📋 *PLAN DE ACCIÓN (Principiantes):*\n"
                "  1. *Tamaño:* Entrada chica (0.05 a 0.2 SOL / máx 1-2% de tu cartera).\n"
                "  2. *Take Profit (TP):* Vende el 50% al duplicar (+100%) para recuperar tu capital y deja correr el resto gratis.\n"
                "  3. *Stop Loss (SL):* Si cae -25%, vende de inmediato para proteger tu balance.\n"
                "  4. *Ejecución:* Usa los enlaces de 1 clic abajo para abrirlo en tu DEX."
            )
        else:
            badge = "🟡 *AVISO DE SALIDA*"
            verdict = "🟡 *VEREDICTO: VENTA / TOMA DE GANANCIAS*"
            explan = f"• `{trader or 'Smart Money'}` está vendiendo o reduciendo posición."
            plan = "• *Plan sugerido:* No compres en este momento; el trader experto está saliendo."
    elif alert_type == "DISCOVERY":
        badge = "🟢 *SEGURIDAD: AUDITORÍA APROBADA*" if not is_warning else "🟡 *SEGURIDAD: REVISIÓN PREVENTIVA*"
        verdict = "🔥 *VEREDICTO: LLAMADA TEMPRANA (X/Twitter)*"
        explan = f"• Mención detectada de `{trader or 'Smart Money'}`. Suele atraer volumen e impulso rápido."
        plan = (
            "📋 *PLAN DE ACCIÓN (Principiantes):*\n"
            "  1. *Tamaño:* Posición ligera de prueba (0.05 a 0.1 SOL).\n"
            "  2. *Take Profit (TP):* Toma ganancias rápido (+50% a +100%) con la primera ola de compras.\n"
            "  3. *Stop Loss (SL):* Salida estricta si retrocede -20%."
        )
    else:  # CONVERGENCE
        sc = score or 0
        if sc >= 75:
            badge = "🟢 *SEGURIDAD: CONVERGENCIA FUERTE*"
            verdict = f"🟢 *VEREDICTO: OPORTUNIDAD ALTA ({sc}/100)*"
            explan = "• Volumen activo, sentimiento social positivo y métricas en sincronía."
        else:
            badge = "🟡 *SEGURIDAD: CONVERGENCIA MODERADA*"
            verdict = f"🟡 *VEREDICTO: SEÑAL EN DESARROLLO ({sc}/100)*"
            explan = "• Señal válida pero con menor volumen; vigilar gráfica antes de entrar fuerte."
        plan = (
            "📋 *PLAN DE ACCIÓN (Principiantes):*\n"
            "  1. *Tamaño:* 1% a 2% del total de tu capital.\n"
            "  2. *Take Profit (TP):* Vende 50% al +100% y pon el resto en 'moonbag'.\n"
            "  3. *Stop Loss (SL):* -25% desde tu precio de entrada."
        )

    return f"""{badge}
{verdict}
{explan}

{plan}"""


def send_radar_alert(
    asset: str,
    chain: str,
    score: int,
    signals: list,
    metrics: dict,
    audit: dict,
    actions: dict,
    token: str = None,
    chat_id: str = None
) -> bool:
    """Envía una alerta formateada con el estándar profesional y guía para principiantes."""
    signal_lines = "\n".join(f"• {s}" for s in signals) if signals else "• Sin señales"
    
    metric_lines = []
    if metrics:
        if "market_cap" in metrics:
            metric_lines.append(f"• MARKET CAP:    {metrics['market_cap']}")
        if "liquidity" in metrics:
            metric_lines.append(f"• LIQUIDITY:     {metrics['liquidity']}")
        if "volume_5m" in metrics:
            metric_lines.append(f"• VOLUME (5M):   {metrics['volume_5m']}")
        if "top_10" in metrics:
            metric_lines.append(f"• TOP 10 SUPPLY: {metrics['top_10']}")
    metrics_block = "\n".join(metric_lines) if metric_lines else "• Métricas en proceso"

    audit_lines = []
    if audit:
        if "contract" in audit:
            audit_lines.append(f"• CONTRACT:      {audit['contract']}")
        if "honeypot" in audit:
            audit_lines.append(f"• HONEYPOT:      {audit['honeypot']}")
        if "authorities" in audit:
            audit_lines.append(f"• AUTHORITIES:   {audit['authorities']}")
        if "risk" in audit:
            audit_lines.append(f"• RISK RATING:   {audit['risk']}")
        if "smart_money" in audit:
            audit_lines.append(f"• SMART MONEY:   {audit['smart_money']}")
    audit_block = "\n".join(audit_lines) if audit_lines else "• Auditoría pendiente"

    enhanced_actions = {}
    ca = audit.get("contract") if audit else None
    if ca and len(ca) >= 32 and not ca.startswith("0x"):
        enhanced_actions["📱 FOMO (Operar / Copiar)"] = f"https://fomo.family/token/{ca}"
        enhanced_actions["💊 Pump.fun (0% Comisiones)"] = f"https://pump.fun/coin/{ca}"
        enhanced_actions["📊 DexScreener (Gráfica)"] = f"https://dexscreener.com/solana/{ca}"

    if actions:
        for name, link in actions.items():
            if name not in enhanced_actions:
                enhanced_actions[name] = link

    action_lines = []
    for name, link in enhanced_actions.items():
        action_lines.append(f"• [{name}]({link})")
    actions_block = "\n".join(action_lines) if action_lines else "Sin enlaces"

    actionable_guide = generate_actionable_plan(
        alert_type="CONVERGENCE",
        score=score,
        audit=audit,
        metrics=metrics,
        trader=audit.get("smart_money") if audit else None,
    )

    message = f"""🎯 *MEME RADAR // CONVERGENCIA DETECTADA*
────────────────────────────────────────
*TOKEN:*        `{asset}` ({chain})
*SCORE:*        `{score} / 100`
────────────────────────────────────────

{actionable_guide}

────────────────────────────────────────
📊 *MÉTRICAS ON-CHAIN (Detalle)*
{metrics_block}

🛡️ *AUDITORÍA DE SEGURIDAD*
{audit_block}

⚡ *EJECUCIÓN DIRECTA (Elige plataforma)*
{actions_block}
────────────────────────────────────────"""

    return send_message(message, token=token, chat_id=chat_id)


def send_discovery_alert(
    asset: str,
    chain: str,
    traders: str,
    tweet_snippet: str,
    metrics: dict,
    audit: dict = None,
    actions: dict = None,
    token: str = None,
    chat_id: str = None
) -> bool:
    """Envía alerta prioritaria de nuevo token descubierto por Smart Money con veredicto y plan."""
    metric_lines = []
    if metrics:
        if "market_cap" in metrics:
            metric_lines.append(f"• MARKET CAP:    {metrics['market_cap']}")
        if "liquidity" in metrics:
            metric_lines.append(f"• LIQUIDITY:     {metrics['liquidity']}")
        if "volume_5m" in metrics:
            metric_lines.append(f"• VOLUME (5M):   {metrics['volume_5m']}")
    metrics_block = "\n".join(metric_lines) if metric_lines else "• Métricas en proceso"

    audit_lines = []
    if audit:
        if "contract" in audit:
            audit_lines.append(f"• CONTRACT:      {audit['contract']}")
        if "honeypot" in audit:
            audit_lines.append(f"• HONEYPOT:      {audit['honeypot']}")
        if "authorities" in audit:
            audit_lines.append(f"• AUTHORITIES:   {audit['authorities']}")
        if "top_10" in audit:
            audit_lines.append(f"• TOP 10 SUPPLY: {audit['top_10']}")
        if "risk" in audit:
            audit_lines.append(f"• RISK RATING:   {audit['risk']}")
    audit_block = "\n".join(audit_lines) if audit_lines else "• Auditoría pendiente"

    enhanced_actions = {}
    ca = audit.get("contract") if audit else None
    if not ca and actions:
        for v in actions.values():
            if "dexscreener.com/solana/" in v:
                ca = v.split("dexscreener.com/solana/")[1].split("?")[0]
                break

    if ca and len(ca) >= 32 and not ca.startswith("0x"):
        enhanced_actions["📱 FOMO (Operar / Copiar)"] = f"https://fomo.family/token/{ca}"
        enhanced_actions["💊 Pump.fun (0% Comisiones)"] = f"https://pump.fun/coin/{ca}"
        enhanced_actions["📊 DexScreener (Gráfica)"] = f"https://dexscreener.com/solana/{ca}"

    if actions:
        for name, link in actions.items():
            if name not in enhanced_actions:
                enhanced_actions[name] = link

    action_lines = []
    for name, link in enhanced_actions.items():
        action_lines.append(f"• [{name}]({link})")
    actions_block = "\n".join(action_lines) if action_lines else "Sin enlaces"

    actionable_guide = generate_actionable_plan(
        alert_type="DISCOVERY",
        audit=audit,
        metrics=metrics,
        trader=traders,
    )

    message = f"""🔥 *MEME RADAR // SMART MONEY EARLY CALL*
────────────────────────────────────────
*TOKEN:*        `${asset}` ({chain})
*SMART MONEY:*  `{traders}`
────────────────────────────────────────

{actionable_guide}

────────────────────────────────────────
💬 *DETECCIÓN SOCIAL*
• {tweet_snippet}

📊 *MÉTRICAS ON-CHAIN*
{metrics_block}

🛡️ *AUDITORÍA (RugCheck)*
{audit_block}

⚡ *EJECUCIÓN DIRECTA (Elige plataforma)*
{actions_block}
────────────────────────────────────────"""

    return send_message(message, token=token, chat_id=chat_id)


def send_copytrade_alert(
    trader_alias: str,
    trader_handle: str,
    wallet: str,
    action_type: str,
    asset_name: str,
    asset_symbol: str,
    mint_address: str,
    sol_amount: float = 0.0,
    metrics: dict = None,
    audit: dict = None,
    actions: dict = None,
    token: str = None,
    chat_id: str = None
) -> bool:
    """Envía alerta en tiempo real de movimiento on-chain de una wallet con veredicto y plan."""
    short_wallet = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) >= 10 else wallet
    action_icon = "🟢" if "BUY" in action_type.upper() or "COMPRA" in action_type.upper() else "🔄"

    metric_lines = []
    if metrics:
        if "market_cap" in metrics:
            metric_lines.append(f"• MARKET CAP:    {metrics['market_cap']}")
        if "liquidity" in metrics:
            metric_lines.append(f"• LIQUIDITY:     {metrics['liquidity']}")
        if "volume_5m" in metrics:
            metric_lines.append(f"• VOLUME (5M):   {metrics['volume_5m']}")
    metrics_block = "\n".join(metric_lines) if metric_lines else "• Métricas en proceso"

    audit_lines = []
    if audit:
        if "honeypot" in audit:
            audit_lines.append(f"• HONEYPOT:      {audit['honeypot']}")
        if "authorities" in audit:
            audit_lines.append(f"• AUTHORITIES:   {audit['authorities']}")
        if "top_10" in audit:
            audit_lines.append(f"• TOP 10 SUPPLY: {audit['top_10']}")
        if "risk" in audit:
            audit_lines.append(f"• RISK RATING:   {audit['risk']}")
    audit_block = "\n".join(audit_lines) if audit_lines else "• Auditoría pendiente"

    safe_name = str(asset_name).replace("*", "").replace("_", " ")
    safe_symbol = str(asset_symbol).replace("*", "").replace("_", "")
    safe_alias = str(trader_alias).replace("*", "").replace("_", " ")
    safe_handle = str(trader_handle).replace("*", "").replace("_", "\\_")
    clean_handle = safe_handle.replace("\\", "").lstrip("@")

    # Enlaces de ejecución rápida priorizando FOMO y Pump.fun
    enhanced_actions = {}
    if mint_address and len(mint_address) >= 32 and not mint_address.startswith("0x"):
        enhanced_actions["📱 FOMO (Operar / Copiar)"] = f"https://fomo.family/token/{mint_address}"
        enhanced_actions["💊 Pump.fun (0% Comisiones)"] = f"https://pump.fun/coin/{mint_address}"
        if clean_handle:
            enhanced_actions[f"👤 Perfil de @{clean_handle} en FOMO"] = f"https://fomo.family/u/{clean_handle}"
        enhanced_actions["📊 DexScreener (Gráfica)"] = f"https://dexscreener.com/solana/{mint_address}"
        enhanced_actions["⚡ Photon / BullX"] = f"https://photon-sol.tinyastro.io/en/r/@meme/{mint_address}"

    if actions:
        for k, v in actions.items():
            if k not in enhanced_actions:
                enhanced_actions[k] = v

    action_lines = []
    for name, link in enhanced_actions.items():
        action_lines.append(f"• [{name}]({link})")
    actions_block = "\n".join(action_lines) if action_lines else "Sin enlaces"

    sol_line = f"*SOL OPERADO:*  `{sol_amount:.2f} SOL`\n" if sol_amount > 0 else ""

    actionable_guide = generate_actionable_plan(
        alert_type="COPYTRADE",
        audit=audit,
        metrics=metrics,
        trader=f"@{safe_handle} ({safe_alias})",
        action_type=action_type,
    )

    message = f"""🎯 *MEME RADAR // COPYTRADE EN VIVO*
────────────────────────────────────────
*TRADER:*       @{safe_handle} ({safe_alias})
*ACCION:*       {action_icon} *{action_type}*
*TOKEN:*        `${safe_symbol}` ({safe_name})
{sol_line}*WALLET:*       `{short_wallet}`
*CONTRATO (CA):* `{mint_address}`
────────────────────────────────────────

{actionable_guide}

────────────────────────────────────────
📊 *MÉTRICAS ON-CHAIN*
{metrics_block}

🛡️ *AUDITORÍA (RugCheck)*
{audit_block}

⚡ *EJECUCIÓN DIRECTA (1-CLIC)*
{actions_block}
────────────────────────────────────────"""

    return send_message(message, token=token, chat_id=chat_id)


if __name__ == "__main__":
    # Test simple de conexión
    print("Iniciando prueba de conexión con Telegram...")
    if len(sys.argv) >= 3:
        tok = sys.argv[1]
        cid = sys.argv[2]
        test_msg = "*MEME RADAR // TEST EXITOSO*\n\nConexión con el bot establecida correctamente."
        if send_message(test_msg, token=tok, chat_id=cid):
            print("✅ Mensaje de prueba enviado con éxito a tu Telegram.")
        else:
            print("❌ Falló el envío del mensaje de prueba.")
    else:
        # Intento con variables de entorno
        test_msg = "*MEME RADAR // TEST*\n\nProbando conexión de alerta."
        if send_message(test_msg):
            print("✅ Mensaje enviado con éxito usando variables de entorno.")
        else:
            print("ℹ️ Para probar directamente por comando ejecuta:")
            print("    python src/alertas/telegram_bot.py <BOT_TOKEN> <CHAT_ID>")
