"""Smart Money Discovery Radar — Monitorea los traders élite en X para descubrir nuevos tokens.

Escanea las publicaciones directas de los priority traders de config/smart_money.json,
extrae cashtags ($TICKER) y contratos (solana:<address> o raw base58),
consulta DexScreener y opcionalmente dispara alertas de descubrimiento a Telegram.
"""

import os
import sys
import re
import json
import time
import datetime
from pathlib import Path

# Soporte UTF-8 en consola de Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "smart_money.json"

sys.path.insert(0, str(PROJECT_ROOT / "src" / "x-mcp"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "fomo"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "alertas"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "auditoria"))

COMMON_EXCLUSIONS = {
    "BTC", "ETH", "SOL", "USDC", "USDT", "BNB", "XRP", "ADA", "DOGE",
    "USD", "AI", "FOMO", "PUMP", "X", "NEW", "TOP", "ATH", "DEX", "K", "M", "B"
}

CASHTAG_REGEX = re.compile(r"\$([A-Za-z0-9_]{2,15})\b")
SOLANA_CA_REGEX = re.compile(r"(?:solana:)?\b([1-9A-HJ-NP-Za-km-z]{32,44})\b")


def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def load_smart_money_config():
    if not CONFIG_PATH.exists():
        log(f"❌ Error: {CONFIG_PATH} no encontrado.")
        return {}, []
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    priority = data.get("priority_handles", [])
    return data, priority


def scan_user_profiles(handles, max_tweets_per_user=4):
    """Escanea el perfil directo de cada trader prioritario usando una sola pestaña."""
    from tools_read import get_batch_user_tweets

    all_tweets = []

    def on_progress(idx, total, handle):
        log(f"[{idx}/{total}] Escaneando perfil de @{handle}...")

    log(f"Iniciando escaneo por lotes para {len(handles)} perfiles en segundo plano...")
    batch_results = get_batch_user_tweets(handles, max_results=max_tweets_per_user, progress_cb=on_progress)

    for idx, handle in enumerate(handles, 1):
        raw = batch_results.get(handle, "")
        if not raw or "No se encontraron" in raw or "Error" in raw or "No tweets" in raw:
            log(f"  -> Sin tweets obtenidos para @{handle}")
            continue

        try:
            parsed = parse_profile_tweets(raw, default_handle=handle)
            log(f"  -> {len(parsed)} tweet(s) extraídos de @{handle}")
            all_tweets.extend(parsed)
        except Exception as e:
            log(f"  -> Error parseando tweets de @{handle}: {e}")

    return all_tweets


def parse_profile_tweets(raw_text, default_handle=""):
    """Parsea el formato devuelto por get_user_tweets y search_tweets."""
    tweets = []
    blocks = re.split(r"\n(?=\d+\.\s+Author:)|Tweet \d+:", raw_text)

    for block in blocks:
        block = block.strip()
        if not block or "Tweets from " in block:
            continue

        tweet = {"handle": default_handle, "author": default_handle}

        # Extraer Author
        author_m = re.search(r"Author:\s*(.+)", block)
        if author_m:
            tweet["author"] = author_m.group(1).strip()

        # Extraer Handle
        handle_m = re.search(r"Handle:\s*@?([A-Za-z0-9_]+)", block)
        if handle_m:
            tweet["handle"] = handle_m.group(1).strip()

        # Extraer Text
        text_m = re.search(r"Text:\s*(.*?)(?=\n\s*(?:Timestamp|Replies|Likes|Time):|$)", block, re.DOTALL)
        if text_m:
            tweet["text"] = text_m.group(1).strip()
        else:
            # Fallback a buscar entre líneas
            lines = [l.strip() for l in block.split("\n") if l.strip()]
            for l in lines:
                if l.startswith("Text:"):
                    tweet["text"] = l.replace("Text:", "").strip()

        # Extraer Time
        time_m = re.search(r"(?:Timestamp|Time):\s*(.+)", block)
        if time_m:
            tweet["time"] = time_m.group(1).strip()

        # Extraer Likes
        likes_m = re.search(r"Likes:\s*(\d+)", block)
        if likes_m:
            tweet["likes"] = likes_m.group(1).strip()

        if tweet.get("text"):
            tweets.append(tweet)

    return tweets


def extract_signals_from_tweets(tweets):
    """Extrae cashtags, contratos y menciones de traders."""
    from collections import defaultdict
    token_mentions = defaultdict(lambda: {"count": 0, "traders": set(), "tweets": [], "cas": set()})

    for tw in tweets:
        text = tw.get("text", "")
        author = tw.get("author", "")
        handle = tw.get("handle", "").replace("@", "").strip()

        cashtags = CASHTAG_REGEX.findall(text)
        potential_cas = SOLANA_CA_REGEX.findall(text)

        # Filtrar CAs validos
        valid_cas = [ca for ca in potential_cas if not ca.isdigit() and len(ca) >= 32 and len(ca) <= 44]

        sender = f"@{handle}" if handle else f"@{author}"

        for tag in cashtags:
            tag_upper = tag.upper()
            # Ignorar si es un monto monetario ($16k, $20m, $10, etc.)
            if re.match(r"^\d+[KkMmBbTt]?$", tag):
                continue
            # Ignorar si no contiene letras
            if not any(c.isalpha() for c in tag):
                continue
            if tag_upper in COMMON_EXCLUSIONS:
                continue

            token_mentions[tag_upper]["count"] += 1
            token_mentions[tag_upper]["traders"].add(sender)
            token_mentions[tag_upper]["tweets"].append({
                "author": sender,
                "text": text[:140],
                "time": tw.get("time", "")
            })

        # Registrar contratos de Solana individuales detectados
        for ca in valid_cas:
            # Asociar nombre amigable si es contrato conocido
            ca_label = f"CA:{ca[:6]}...{ca[-4:]}"
            if "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr" in ca:
                ca_label = "POPCAT"
            elif "Dz9mQ9NzkBcCsuGPFJ3r1bS4wgqKMHBPiVuniW8Mbonk" in ca:
                ca_label = "BONK"

            token_mentions[ca_label]["count"] += 1
            token_mentions[ca_label]["traders"].add(sender)
            token_mentions[ca_label]["cas"].add(ca)
            token_mentions[ca_label]["tweets"].append({
                "author": sender,
                "text": text[:140],
                "time": tw.get("time", "")
            })

    return token_mentions


def check_tokens_onchain(token_mentions):
    """Consulta métricas rápidas de DexScreener para los tokens descubiertos."""
    from fomo_tracker import FomoTracker
    tracker = FomoTracker()

    enriched = {}
    for symbol, data in token_mentions.items():
        log(f"Consultando DexScreener para ${symbol}...")
        mdata = None
        # Si tiene CA registrado, consultar por CA
        if data.get("cas"):
            ca = list(data["cas"])[0]
            mdata = tracker.get_token_market_data(ca)
        if not mdata:
            mdata = tracker.get_token_market_data(symbol)

        enriched[symbol] = {
            "mention_data": data,
            "market_data": mdata
        }
    return enriched

DISCOVERED_TOKENS_PATH = PROJECT_ROOT / "config" / "discovered_tokens.json"


def load_discovered_tokens():
    """Carga tokens descubiertos previamente."""
    if not DISCOVERED_TOKENS_PATH.exists():
        return {}
    try:
        with open(DISCOVERED_TOKENS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_discovered_tokens(data):
    """Guarda tokens descubiertos."""
    try:
        with open(DISCOVERED_TOKENS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        log(f"Error guardando {DISCOVERED_TOKENS_PATH}: {e}")


def run_discovery_scan(target_handles=None, send_to_telegram=False, force_alert=False):
    log("=" * 60)
    log("MEME RADAR // SMART MONEY PROFILE DISCOVERY SCAN")
    log("=" * 60)

    sm_data, priority_handles = load_smart_money_config()
    handles_to_scan = target_handles or priority_handles[:5]

    log(f"Traders seleccionados para este ciclo ({len(handles_to_scan)}):")
    log(", ".join("@" + h for h in handles_to_scan))

    tweets = scan_user_profiles(handles_to_scan, max_tweets_per_user=4)
    log(f"\nTotal tweets capturados: {len(tweets)}")

    for idx, tw in enumerate(tweets, 1):
        h = tw.get("handle", "")
        t = tw.get("text", "").replace("\n", " ")
        log(f"  [{idx}] @{h}: \"{t[:120]}...\"")

    if not tweets:
        log("ℹ️ No se pudieron capturar tweets en este ciclo.")
        return []

    token_mentions = extract_signals_from_tweets(tweets)
    log(f"\nTokens / CAs detectados en los tweets: {len(token_mentions)}")

    for sym, d in token_mentions.items():
        traders_str = ", ".join(d["traders"])
        cas_str = ", ".join(d["cas"]) if d["cas"] else "N/A"
        log(f"  • ${sym}: {d['count']} mención(es) por {traders_str} (CA: {cas_str})")

    # Enriquecer con DexScreener
    enriched = check_tokens_onchain(token_mentions)
    discovered = load_discovered_tokens()

    log("\n" + "=" * 60)
    log("RESUMEN DE INTELIGENCIA DESCUBIERTA")
    log("=" * 60)

    for symbol, item in enriched.items():
        m_info = item["mention_data"]
        onchain = item["market_data"]
        traders_str = ", ".join(m_info["traders"])

        mc = onchain.get("market_cap", "N/A") if onchain else "Sin par en DexScreener"
        liq = onchain.get("liquidity", "N/A") if onchain else "N/A"
        vol = onchain.get("volume_5m", "N/A") if onchain else "N/A"
        pair = onchain.get("pair_url", "") if onchain else ""

        is_new = symbol not in discovered

        log(f"\n[CALL DESCUBIERTO] ${symbol} {'🔥 [NUEVO]' if is_new else '[CONOCIDO]'}")
        log(f"  Smart Money: {traders_str}")
        log(f"  Menciones:   {m_info['count']}")
        log(f"  Market Cap:  {mc}")
        log(f"  Liquidez:    {liq}")
        log(f"  Volumen 5m:  {vol}")
        if pair:
            log(f"  Enlace:      {pair}")

        if is_new:
            discovered[symbol] = {
                "first_seen": datetime.datetime.now().isoformat(),
                "traders": list(m_info["traders"]),
                "mention_count": m_info["count"],
                "market_cap": mc,
                "liquidity": liq
            }
            save_discovered_tokens(discovered)

        if send_to_telegram and onchain and (is_new or force_alert):
            try:
                from telegram_bot import send_discovery_alert
                actions = {}
                if pair:
                    actions["DexScreener"] = pair

                # Auditoría on-chain con RugCheck si tiene CA
                ca_candidate = None
                if m_info.get("cas"):
                    ca_candidate = list(m_info["cas"])[0]
                elif onchain and onchain.get("address"):
                    ca_candidate = onchain["address"]

                audit_dict = {}
                if ca_candidate and len(ca_candidate) >= 32 and len(ca_candidate) <= 44:
                    try:
                        from rugcheck import audit_token, format_audit_for_alert
                        audit_res = audit_token(ca_candidate)
                        if audit_res.get("success"):
                            audit_dict = format_audit_for_alert(audit_res)
                            if audit_res.get("rugcheck_url"):
                                actions["RugCheck"] = audit_res["rugcheck_url"]
                            log(f"  RugCheck: {audit_res['risk_rating']} | Freeze: {audit_res['freeze_authority']} | Top10: {audit_res['top10_supply_pct']}%")
                    except Exception as e:
                        log(f"  Error en RugCheck para ${symbol}: {e}")

                tweet_preview = m_info["tweets"][0]["text"] if m_info["tweets"] else f"Mencionado por {traders_str}"
                sent = send_discovery_alert(
                    asset=symbol,
                    chain=onchain.get("chain", "Solana"),
                    traders=traders_str,
                    tweet_snippet=tweet_preview,
                    metrics={
                        "market_cap": mc,
                        "liquidity": liq,
                        "volume_5m": vol
                    },
                    audit=audit_dict if audit_dict else None,
                    actions=actions
                )
                if sent:
                    log(f"  ✅ Alerta enviada a Telegram para ${symbol}")
                    try:
                        sys.path.insert(0, str(PROJECT_ROOT / "src" / "bitacora"))
                        from logger import log_alert, SIGNAL_DISCOVERY, LAYER_X, LAYER_DEXSCREENER, LAYER_SEGURIDAD
                        disc_layers = [LAYER_X]
                        if onchain:
                            disc_layers.append(LAYER_DEXSCREENER)
                        if audit_dict:
                            disc_layers.append(LAYER_SEGURIDAD)
                        c_mint = ca_candidate or (onchain.get("address", "") if onchain else "")
                        c_price = onchain.get("price_usd", "") if onchain else ""
                        aid = log_alert(
                            token=symbol,
                            signal_type=SIGNAL_DISCOVERY,
                            mint=c_mint,
                            chain=onchain.get("chain", "Solana") if onchain else "Solana",
                            score=65,
                            layers=disc_layers,
                            signals=[f"Discovery por {traders_str}", f"Menciones: {m_info['count']}"],
                            traders_involved=list(m_info.get("traders", [])),
                            metrics={"market_cap": mc, "liquidity": liq, "volume_5m": vol},
                            audit=audit_dict,
                            price_at_alert=c_price
                        )
                        log(f"  [BITACORA] Discovery registrado ID: {aid} (Capas: {'+'.join(disc_layers)})")
                    except Exception as ble:
                        log(f"  [BITACORA] Error registrando discovery: {ble}")
                else:
                    log(f"  ❌ No se pudo enviar alerta a Telegram para ${symbol}")
            except Exception as e:
                log(f"  ❌ Error enviando a Telegram: {e}")
        elif not is_new and send_to_telegram and not force_alert:
            log(f"  ℹ️ Token ${symbol} ya alertado previamente (omitido para evitar spam)")

    return enriched


if __name__ == "__main__":
    send_tg = "--telegram" in sys.argv
    force = "--force" in sys.argv
    custom_handles = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    run_discovery_scan(target_handles=custom_handles if custom_handles else None, send_to_telegram=send_tg, force_alert=force)
