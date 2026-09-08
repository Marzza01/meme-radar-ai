"""Motor de convergencia — monitorea Twitter + DexScreener + Smart Money y dispara alertas a Telegram.

Lee la watchlist de config/watchlist.json y los traders de config/smart_money.json.
Escanea cada token en loop, cruza con actividad de smart money,
puntua la convergencia de senales y envia alertas cuando supera el umbral.
"""

import os
import sys
import json
import time
import datetime
from pathlib import Path
from collections import defaultdict

# Soporte UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Paths del proyecto
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "watchlist.json"
SMART_MONEY_PATH = PROJECT_ROOT / "config" / "smart_money.json"

# Agregar paths de los modulos
sys.path.insert(0, str(PROJECT_ROOT / "src" / "x-mcp"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "fomo"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "alertas"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "auditoria"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "bitacora"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "pumpfun"))


def load_config():
    """Carga la configuracion de la watchlist."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_smart_money():
    """Carga la base de datos de smart money traders."""
    if not SMART_MONEY_PATH.exists():
        return {}
    with open(SMART_MONEY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_trader_index(smart_money_data):
    """Construye un indice rapido: handle_lower -> {tier, alias, score_weight, ...}"""
    index = {}
    for tier_key, tier_data in smart_money_data.get("traders", {}).items():
        weight = tier_data.get("score_weight", 5)
        label = tier_data.get("label", tier_key)
        for member in tier_data.get("members", []):
            handle = member.get("handle", "").lower()
            alias = member.get("alias", handle)
            if handle:
                index[handle] = {
                    "tier": tier_key,
                    "tier_label": label,
                    "alias": alias,
                    "weight": weight,
                    "platform": member.get("platform", ""),
                    "handle_original": member.get("handle", ""),
                }
            # Tambien indexar por alias en minusculas
            alias_lower = alias.lower()
            if alias_lower and alias_lower != handle:
                index[alias_lower] = index.get(handle, {
                    "tier": tier_key,
                    "tier_label": label,
                    "alias": alias,
                    "weight": weight,
                    "platform": member.get("platform", ""),
                    "handle_original": member.get("handle", ""),
                })
    return index


def scan_twitter(search_term, max_results=10):
    """Busca tweets sobre un token. Devuelve lista de tweets parseados."""
    try:
        from tools_read import search_tweets
        raw = search_tweets(search_term, max_results)

        if not raw or "Error" in raw or "No se encontraron" in raw or "No tweets" in raw:
            return []

        # Parsear los tweets del formato texto
        tweets = []
        current_tweet = {}
        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                if current_tweet:
                    tweets.append(current_tweet)
                    current_tweet = {}
                continue

            if line and line[0].isdigit() and ". Author:" in line:
                if current_tweet:
                    tweets.append(current_tweet)
                parts = line.split("Author:", 1)
                current_tweet = {"author": parts[1].strip() if len(parts) > 1 else ""}
            elif line.startswith("Handle:"):
                current_tweet["handle"] = line.split(":", 1)[1].strip()
            elif line.startswith("Text:"):
                current_tweet["text"] = line.split(":", 1)[1].strip()
            elif line.startswith("Timestamp:"):
                current_tweet["timestamp"] = line.split(":", 1)[1].strip()
            elif line.startswith("Replies:"):
                parts = line.replace(",", "").split()
                current_tweet["replies"] = parts[1] if len(parts) > 1 else "0"
                current_tweet["retweets"] = parts[3] if len(parts) > 3 else "0"
                current_tweet["likes"] = parts[5] if len(parts) > 5 else "0"
            elif current_tweet.get("text") is not None:
                # Linea adicional del texto del tweet
                current_tweet["text"] += " " + line

        if current_tweet:
            tweets.append(current_tweet)

        return tweets

    except Exception as e:
        log(f"  Error escaneando Twitter para '{search_term}': {e}")
        return []


def scan_dexscreener(symbol):
    """Obtiene datos on-chain de DexScreener."""
    try:
        from fomo_tracker import FomoTracker
        tracker = FomoTracker()
        return tracker.get_token_market_data(symbol)
    except Exception as e:
        log(f"  Error consultando DexScreener para '{symbol}': {e}")
        return None


def detect_smart_money(tweets, trader_index):
    """Detecta si alguno de los tweets proviene de un trader de smart money.

    Retorna:
        smart_money_hits: lista de {trader_info, tweet} para cada match
        total_weight: suma de pesos de los traders detectados
    """
    hits = []
    seen_traders = set()

    for tweet in tweets:
        # Revisar handle y author del tweet
        tweet_handle = tweet.get("handle", "").lower().replace("@", "").strip()
        tweet_author = tweet.get("author", "").lower().strip()

        matched_trader = None

        # Match directo por handle
        if tweet_handle in trader_index:
            matched_trader = trader_index[tweet_handle]
        # Match por author name
        elif tweet_author in trader_index:
            matched_trader = trader_index[tweet_author]
        else:
            # Match parcial: el handle del trader aparece en el handle/author del tweet
            for trader_handle, trader_info in trader_index.items():
                if len(trader_handle) >= 4:  # evitar matches falsos con handles cortos
                    if trader_handle in tweet_handle or trader_handle in tweet_author:
                        matched_trader = trader_info
                        break

        if matched_trader and matched_trader.get("handle_original", "") not in seen_traders:
            seen_traders.add(matched_trader.get("handle_original", ""))
            hits.append({
                "trader": matched_trader,
                "tweet": tweet,
            })

    total_weight = sum(h["trader"]["weight"] for h in hits)
    return hits, total_weight


def calculate_score(tweets, market_data, thresholds, smart_money_hits=None, smart_money_weight=0, audit_res=None):
    """Calcula un score de convergencia (0-100) basado en las senales y auditoria de seguridad."""
    score = 0
    signals = []

    # --- SEGURIDAD & AUDITORIA (VETO PREVENTIVO) ---
    if audit_res and audit_res.get("success"):
        if not audit_res.get("safe", True) or audit_res.get("rugged"):
            score = 0
            signals.append(f"❌ RUGCHECK PELIGRO: {audit_res.get('risk_rating', 'PELIGRO')} (Score anulado por seguridad)")
            return 0, signals

        if "REVOCADO" in audit_res.get("freeze_authority", ""):
            score += 10
            signals.append("Seguridad: Freeze Revocado / Anti-Honeypot (+10pts)")
        if "REVOCADO" in audit_res.get("mint_authority", ""):
            score += 5
            signals.append("Seguridad: Mint Revocado (+5pts)")

        top10 = audit_res.get("top10_supply_pct", 0)
        if top10 > 65:
            score -= 15
            signals.append(f"Riesgo insider: Top 10 posee {top10}% del supply (-15pts)")
        elif top10 < 35 and top10 > 0:
            score += 5
            signals.append(f"Distribucion saludable: Top 10 posee {top10}% (+5pts)")

        lp = audit_res.get("lp_locked_pct", 0)
        if lp > 80:
            score += 5
            signals.append(f"Liquidez protegida: {lp}% LP bloqueada (+5pts)")

    # --- SMART MONEY SIGNALS (prioridad maxima) ---
    if smart_money_hits:
        score += smart_money_weight
        for hit in smart_money_hits:
            trader = hit["trader"]
            tweet_text = hit["tweet"].get("text", "")[:80]
            signals.append(
                f"SMART MONEY [{trader['tier'].upper()}]: @{trader['handle_original']} "
                f"({trader['alias']}) +{trader['weight']}pts — \"{tweet_text}...\""
            )

    # --- TWITTER SIGNALS ---
    tweet_count = len(tweets)

    if tweet_count >= thresholds.get("min_tweets_for_buzz", 3):
        buzz_score = min(30, tweet_count * 3)
        score += buzz_score
        signals.append(f"Twitter buzz: {tweet_count} tweets recientes (+{buzz_score}pts)")

    # Engagement total
    total_likes = 0
    total_retweets = 0
    for t in tweets:
        try:
            likes_str = str(t.get("likes", "0")).replace(",", "").strip()
            rt_str = str(t.get("retweets", "0")).replace(",", "").strip()
            total_likes += int(likes_str) if likes_str.isdigit() else 0
            total_retweets += int(rt_str) if rt_str.isdigit() else 0
        except (ValueError, TypeError):
            pass

    if total_likes > 50:
        eng_score = min(15, total_likes // 10)
        score += eng_score
        signals.append(f"Engagement alto: {total_likes} likes, {total_retweets} RTs (+{eng_score}pts)")
    elif total_likes > 10:
        score += 5
        signals.append(f"Engagement moderado: {total_likes} likes (+5pts)")

    # --- ON-CHAIN SIGNALS ---
    if market_data:
        # Market Cap
        try:
            mcap = float(market_data.get("market_cap", "$0").replace("$", "").replace(",", ""))
        except (ValueError, TypeError):
            mcap = 0

        min_mcap = thresholds.get("min_market_cap_usd", 100000)
        if mcap >= min_mcap:
            if mcap >= 10_000_000:
                score += 15
                signals.append(f"Market Cap fuerte: {market_data['market_cap']} (+15pts)")
            elif mcap >= 1_000_000:
                score += 10
                signals.append(f"Market Cap creciente: {market_data['market_cap']} (+10pts)")
            else:
                score += 5
                signals.append(f"Market Cap base: {market_data['market_cap']} (+5pts)")

        # Liquidez
        try:
            liq = float(market_data.get("liquidity", "$0").replace("$", "").replace(",", ""))
        except (ValueError, TypeError):
            liq = 0

        min_liq = thresholds.get("min_liquidity_usd", 50000)
        if liq >= min_liq:
            if liq >= 1_000_000:
                score += 15
                signals.append(f"Liquidez alta: {market_data['liquidity']} (+15pts)")
            elif liq >= 100_000:
                score += 10
                signals.append(f"Liquidez moderada: {market_data['liquidity']} (+10pts)")
            else:
                score += 5
                signals.append(f"Liquidez base: {market_data['liquidity']} (+5pts)")
        else:
            signals.append(f"Liquidez baja: {market_data.get('liquidity', 'N/A')} (riesgo)")

        # Volumen 5 minutos
        try:
            vol = float(market_data.get("volume_5m", "$0").replace("$", "").replace(",", ""))
        except (ValueError, TypeError):
            vol = 0

        if vol > 10000:
            score += 10
            signals.append(f"Volumen 5m alto: {market_data['volume_5m']} (+10pts)")
        elif vol > 1000:
            score += 5
            signals.append(f"Volumen 5m activo: {market_data['volume_5m']} (+5pts)")

        # Bonus: convergencia multi-signal
        convergence_count = 0
        if tweet_count >= 3:
            convergence_count += 1
        if liq >= min_liq:
            convergence_count += 1
        if vol > 1000:
            convergence_count += 1
        if smart_money_hits:
            convergence_count += 1
        if audit_res and audit_res.get("safe", False):
            convergence_count += 1

        if convergence_count >= 3:
            bonus = 10 if convergence_count == 3 else 15
            score += bonus
            label = "TRIPLE" if convergence_count == 3 else "FULL"
            signals.append(f"CONVERGENCIA {label}: {convergence_count} senales simultaneas (+{bonus}pts)")

    return min(score, 100), signals


# Rate limiting de alertas por token
_alert_history = defaultdict(list)


def can_send_alert(symbol, max_per_hour):
    """Verifica si podemos enviar alerta sin exceder el limite por hora."""
    now = time.time()
    one_hour_ago = now - 3600

    # Limpiar historial viejo
    _alert_history[symbol] = [t for t in _alert_history[symbol] if t > one_hour_ago]

    if len(_alert_history[symbol]) >= max_per_hour:
        return False

    _alert_history[symbol].append(now)
    return True


def send_alert(symbol, market_data, score, signals, config, smart_money_hits=None, audit_res=None):
    """Envia la alerta a Telegram si cumple el umbral."""
    max_per_hour = config.get("thresholds", {}).get("max_alerts_per_token_per_hour", 2)
    if not can_send_alert(symbol, max_per_hour):
        log(f"  Rate limit: ya se enviaron {max_per_hour} alertas de {symbol} en la ultima hora")
        return False

    try:
        from telegram_bot import send_radar_alert

        metrics = {}
        audit = {}
        actions = {}

        if market_data:
            metrics = {
                "market_cap": market_data.get("market_cap", "N/A"),
                "liquidity": market_data.get("liquidity", "N/A"),
                "volume_5m": market_data.get("volume_5m", "N/A"),
            }
            address = market_data.get("address", "")
            if address:
                audit["contract"] = address[:10] + "..." + address[-6:]
            if market_data.get("pair_url"):
                actions["DexScreener"] = market_data["pair_url"]

        # Auditoria de seguridad de RugCheck
        if audit_res and audit_res.get("success"):
            from rugcheck import format_audit_for_alert
            audit_fmt = format_audit_for_alert(audit_res)
            audit.update(audit_fmt)
            if audit_res.get("rugcheck_url"):
                actions["RugCheck"] = audit_res["rugcheck_url"]

        # Agregar smart money info a las senales
        if smart_money_hits:
            sm_names = [f"@{h['trader']['handle_original']}" for h in smart_money_hits]
            audit["smart_money"] = ", ".join(sm_names)

        chain = market_data.get("chain", "unknown") if market_data else "unknown"

        result = send_radar_alert(
            asset=symbol,
            chain=chain,
            score=score,
            signals=signals,
            metrics=metrics,
            audit=audit,
            actions=actions,
        )

        if result:
            try:
                from logger import log_alert, SIGNAL_CONVERGENCE, LAYER_X, LAYER_FOMO, LAYER_PUMPFUN, LAYER_DEXSCREENER, LAYER_SEGURIDAD
                layers = [LAYER_X]
                if any("fomo" in str(s).lower() or "spike" in str(s).lower() or "volumen" in str(s).lower() for s in signals):
                    layers.append(LAYER_FOMO)
                if market_data:
                    layers.append(LAYER_DEXSCREENER)
                    if "pump" in str(actions.get("DexScreener", "")).lower() or str(market_data.get("address", "")).endswith("pump"):
                        layers.append(LAYER_PUMPFUN)
                if audit_res and audit_res.get("success"):
                    layers.append(LAYER_SEGURIDAD)

                trader_names = [f"@{h['trader']['handle_original']}" for h in (smart_money_hits or [])]
                mint_addr = market_data.get("address", "") if market_data else ""
                price_val = market_data.get("price_usd", "") if market_data else ""

                aid = log_alert(
                    token=symbol,
                    signal_type=SIGNAL_CONVERGENCE,
                    mint=mint_addr,
                    chain=chain,
                    score=score,
                    layers=layers,
                    signals=signals,
                    traders_involved=trader_names,
                    metrics=metrics,
                    audit=audit,
                    price_at_alert=price_val
                )
                log(f"  [BITACORA] Alerta registrada ID: {aid} (Capas: {'+'.join(layers)})")
            except Exception as be:
                log(f"  [BITACORA] Error registrando alerta: {be}")

        return result
    except Exception as e:
        log(f"  Error enviando alerta de {symbol}: {e}")
        return False


def log(msg):
    """Log con timestamp."""
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def run_scan_cycle(config, trader_index):
    """Ejecuta un ciclo completo de escaneo."""
    watchlist = [w for w in config.get("watchlist", []) if w.get("enabled", True)]
    thresholds = config.get("thresholds", {})
    alert_min = thresholds.get("alert_score_min", 50)
    try:
        from learner import load_learned_weights
        lw = load_learned_weights()
        if lw.get("threshold_score"):
            alert_min = lw["threshold_score"]
    except Exception:
        pass

    log(f"Escaneando {len(watchlist)} tokens...")

    for token_config in watchlist:
        symbol = token_config["symbol"]
        search_terms = token_config.get("search_terms", [f"${symbol}"])

        log(f"--- {symbol} ---")

        # 1. Escanear Twitter
        all_tweets = []
        for term in search_terms[:2]:  # Max 2 terminos para no saturar
            log(f"  Twitter: buscando '{term}'...")
            tweets = scan_twitter(term, max_results=10)
            all_tweets.extend(tweets)
            if tweets:
                log(f"  -> {len(tweets)} tweets encontrados")
            else:
                log(f"  -> Sin resultados")

        # Deduplicar por texto
        seen_texts = set()
        unique_tweets = []
        for t in all_tweets:
            text_key = t.get("text", "")[:50]
            if text_key and text_key not in seen_texts:
                seen_texts.add(text_key)
                unique_tweets.append(t)

        # 2. Detectar Smart Money en los tweets
        smart_money_hits, sm_weight = detect_smart_money(unique_tweets, trader_index)
        if smart_money_hits:
            log(f"  SMART MONEY detectado: {len(smart_money_hits)} trader(s)")
            for hit in smart_money_hits:
                trader = hit["trader"]
                log(f"    -> @{trader['handle_original']} ({trader['alias']}) [{trader['tier_label']}]")
        else:
            log(f"  Smart Money: ninguno detectado en estos tweets")

        # 3. Consultar DexScreener
        log(f"  DexScreener: consultando {symbol}...")
        market_data = scan_dexscreener(symbol)
        if market_data:
            log(f"  -> MC: {market_data.get('market_cap', 'N/A')} | Liq: {market_data.get('liquidity', 'N/A')} | Vol5m: {market_data.get('volume_5m', 'N/A')}")
        else:
            log(f"  -> Sin datos on-chain")

        # 4. Auditoria de Seguridad On-Chain (RugCheck solo para Solana)
        audit_res = None
        if market_data and market_data.get("address"):
            addr = market_data["address"]
            chain = str(market_data.get("chain", "")).lower()
            if not addr.startswith("0x") and ("solana" in chain or (len(addr) >= 32 and len(addr) <= 44)):
                log(f"  RugCheck: auditando seguridad on-chain ({addr[:6]}...{addr[-4:]})...")
                try:
                    from rugcheck import audit_token
                    audit_res = audit_token(addr)
                    if audit_res.get("success"):
                        log(f"    -> Rating: {audit_res['risk_rating']} | Score: {audit_res['score']} | Freeze: {audit_res['freeze_authority']} | Top10: {audit_res['top10_supply_pct']}%")
                    else:
                        log(f"    -> Auditoria parcial: {audit_res.get('error', 'N/A')}")
                except Exception as e:
                    log(f"    -> Error en RugCheck: {e}")

        # 5. Calcular score integrando seguridad
        score, signals = calculate_score(
            unique_tweets, market_data, thresholds,
            smart_money_hits=smart_money_hits,
            smart_money_weight=sm_weight,
            audit_res=audit_res
        )
        log(f"  Score: {score}/100 (umbral: {alert_min})")
        for s in signals:
            log(f"    {s}")

        # 6. Enriquecimiento Nivel 1 (three.ws Pump.fun) y Nivel 2 (Cope API Verificación Francotirador)
        if score >= alert_min:
            # Nivel 1: Si es token de Pump.fun, consultar estado de la curva de enlace gratis vía three.ws
            addr = market_data.get("address", "") if market_data else ""
            if addr and addr.endswith("pump"):
                try:
                    from three_ws_client import three_ws
                    b_curve = three_ws.get_bonding_curve(addr)
                    if b_curve and b_curve.get("progress_pct"):
                        pct = b_curve["progress_pct"]
                        signals.append(f"Curva Pump.fun: {pct}% completada ({b_curve.get('sol_in_curve', 0)} SOL)")
                        if pct >= 80:
                            signals.append("🔥 ¡Próximo a graduar a Raydium (+80%)!")
                except Exception:
                    pass

            # Nivel 2: Verificación de Alta Convicción con Cope API (solo si score >= 70, protegiendo cuota diaria)
            if score >= 70:
                try:
                    from cope_client import cope_verifier, CopeQuotaManager
                    if cope_verifier.is_configured() and CopeQuotaManager.can_make_call():
                        c_res = cope_verifier.verify_token_smart_money(symbol)
                        if c_res.get("verified"):
                            sm_holders = c_res.get("smart_money_holders", 0)
                            conv = c_res.get("conviction_label", "Media")
                            signals.append(f"Cope Verifier: {sm_holders} Smart Money holders ({conv} convicción)")
                            log(f"  [NIVEL 2 - COPE] Verificado: {sm_holders} holders | Convicción: {conv}")
                except Exception:
                    pass

            log(f"  ALERTA: Score {score} >= {alert_min}, enviando a Telegram...")
            sent = send_alert(symbol, market_data, score, signals, config, smart_money_hits, audit_res=audit_res)
            log(f"  -> {'Enviada' if sent else 'No enviada (rate limit o error)'}")
        else:
            log(f"  Sin alerta (score {score} < {alert_min})")

        log("")


def _launch_telegram_bot():
    """Lanza el bot interactivo de Telegram en un hilo daemon."""
    try:
        import threading
        bot_path = PROJECT_ROOT / "src" / "alertas" / "telegram_commander.py"
        if not bot_path.exists():
            log("[BOT] telegram_commander.py no encontrado — bot interactivo no iniciado")
            return

        # Importar y lanzar el polling en un hilo separado
        import importlib.util
        spec = importlib.util.spec_from_file_location("telegram_commander", str(bot_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        bot_thread = threading.Thread(target=mod.run_polling, kwargs={"poll_once": False}, daemon=True)
        bot_thread.name = "TelegramBotThread"
        bot_thread.start()
        log("[BOT] Bot interactivo de Telegram iniciado en hilo daemon")
    except Exception as e:
        log(f"[BOT] Error al iniciar bot interactivo: {e}")


def main():
    """Loop principal del motor de convergencia."""
    log("=" * 60)
    log("MEME RADAR — Motor de Convergencia + Bot Interactivo")
    log("=" * 60)

    config = load_config()
    smart_money = load_smart_money()
    trader_index = build_trader_index(smart_money)

    interval = config.get("scan_interval_seconds", 300)
    watchlist = [w for w in config.get("watchlist", []) if w.get("enabled", True)]

    log(f"Tokens monitoreados: {', '.join(w['symbol'] for w in watchlist)}")
    log(f"Smart Money trackeados: {len(trader_index)} traders")
    log(f"Intervalo de escaneo: {interval}s ({interval // 60}min)")
    log(f"Umbral de alerta: {config.get('thresholds', {}).get('alert_score_min', 50)}/100")
    log("")

def _launch_wallet_tracker():
    """Lanza el Wallet Tracker de Solana en un hilo daemon paralelo."""
    try:
        import threading
        tracker_path = PROJECT_ROOT / "src" / "wallet_tracker" / "solana_tracker.py"
        if not tracker_path.exists():
            log("[TRACKER] solana_tracker.py no encontrado — wallet tracker no iniciado")
            return

        import importlib.util
        spec = importlib.util.spec_from_file_location("solana_tracker", str(tracker_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        tracker_thread = threading.Thread(
            target=mod.run_wallet_tracker,
            kwargs={"send_telegram": True, "loop": True, "interval_seconds": 15},
            daemon=True
        )
        tracker_thread.name = "WalletTrackerThread"
        tracker_thread.start()
        log("[TRACKER] Wallet Tracker Solana iniciado en hilo daemon (intervalo: 15s)")
    except Exception as e:
        log(f"[TRACKER] Error al iniciar wallet tracker: {e}")


def main():
    """Loop principal del motor de convergencia."""
    log("=" * 60)
    log("MEME RADAR — Motor de Convergencia + Bot Interactivo + Wallet Tracker")
    log("=" * 60)

    config = load_config()
    smart_money = load_smart_money()
    trader_index = build_trader_index(smart_money)

    interval = config.get("scan_interval_seconds", 300)
    watchlist = [w for w in config.get("watchlist", []) if w.get("enabled", True)]

    log(f"Tokens monitoreados: {', '.join(w['symbol'] for w in watchlist)}")
    log(f"Smart Money trackeados: {len(trader_index)} traders")
    log(f"Intervalo de escaneo: {interval}s ({interval // 60}min)")
    log(f"Umbral de alerta: {config.get('thresholds', {}).get('alert_score_min', 50)}/100")
    log("")

    # Hilo 1 — Bot interactivo de Telegram
    bot_enabled = config.get("telegram_bot", {}).get("enabled", True)
    if bot_enabled:
        _launch_telegram_bot()

    # Hilo 2 — Wallet Tracker Solana (copytrade)
    tracker_enabled = config.get("wallet_tracker", {}).get("enabled", True)
    if tracker_enabled:
        _launch_wallet_tracker()

    log("")


    last_report_date = None
    last_learn_date = None
    last_price_update_hour = -1

    cycle = 0
    while True:
        cycle += 1
        now = datetime.datetime.now()
        today_date = datetime.date.today()

        # ─── 1. Actualización horaria de precios 24h de alertas previas
        if now.hour != last_price_update_hour:
            try:
                from logger import run_price_updater
                updated_count = run_price_updater(days_back=2)
                if updated_count > 0:
                    log(f"[BITACORA] {updated_count} precio(s) 24h evaluados con DexScreener")
                last_price_update_hour = now.hour
            except Exception as pe:
                log(f"[BITACORA] Error en actualizador de precios: {pe}")

        # ─── 2. Informe diario a las 23:50
        if now.hour == 23 and now.minute >= 50 and last_report_date != today_date:
            try:
                from reporter import generate_daily_report
                log("\n[REPORTER] Generando informe diario de cierre de jornada...")
                generate_daily_report(date=today_date, send_telegram=True)
                last_report_date = today_date
            except Exception as re:
                log(f"[REPORTER] Error generando informe diario: {re}")

        # ─── 3. Aprendizaje autónomo diario a las 23:55
        if now.hour == 23 and now.minute >= 55 and last_learn_date != today_date:
            try:
                from learner import apply_daily_learning
                log("\n[LEARNER] Ejecutando calibracion autonoma de pesos (capas + traders)...")
                apply_daily_learning(date=today_date, send_telegram=True)
                last_learn_date = today_date
            except Exception as le:
                log(f"[LEARNER] Error en aprendizaje autonomo: {le}")

        log(f"=== CICLO {cycle} ===")

        try:
            # Recargar configs en cada ciclo (permite editar sin reiniciar)
            config = load_config()
            smart_money = load_smart_money()
            trader_index = build_trader_index(smart_money)
            run_scan_cycle(config, trader_index)

            # Escaneo proactivo de Smart Money cada X ciclos
            disc_cfg = config.get("discovery", {})
            if disc_cfg.get("enabled", True):
                disc_interval = disc_cfg.get("interval_cycles", 3)
                if cycle % disc_interval == 1 or cycle == 1:
                    log("\n--- DISCOVERY RADAR: Escaneo Proactivo de Smart Money ---")
                    try:
                        from smart_money_radar import run_discovery_scan
                        disc_traders = disc_cfg.get("active_traders", None)
                        send_tg = disc_cfg.get("send_telegram_alerts", True)
                        run_discovery_scan(target_handles=disc_traders, send_to_telegram=send_tg)
                    except Exception as e:
                        log(f"Error en Discovery Scan: {e}")
        except KeyboardInterrupt:
            log("Detenido por el usuario.")
            break
        except Exception as e:
            log(f"Error en ciclo {cycle}: {e}")

        interval = config.get("scan_interval_seconds", 300)
        log(f"Siguiente escaneo en {interval}s...")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            log("Detenido por el usuario.")
            break


if __name__ == "__main__":
    # Si se pasa --once, ejecuta un solo ciclo y sale
    if "--once" in sys.argv:
        config = load_config()
        smart_money = load_smart_money()
        trader_index = build_trader_index(smart_money)
        log("MEME RADAR — Escaneo unico")
        log(f"Smart Money trackeados: {len(trader_index)} traders")
        run_scan_cycle(config, trader_index)

        disc_cfg = config.get("discovery", {})
        if "--discovery" in sys.argv or disc_cfg.get("enabled", False):
            log("\n--- DISCOVERY RADAR: Escaneo Proactivo de Smart Money ---")
            try:
                from smart_money_radar import run_discovery_scan
                disc_traders = disc_cfg.get("active_traders", None)
                send_tg = disc_cfg.get("send_telegram_alerts", True)
                run_discovery_scan(target_handles=disc_traders, send_to_telegram=send_tg)
            except Exception as e:
                log(f"Error en Discovery Scan: {e}")
    else:
        main()
