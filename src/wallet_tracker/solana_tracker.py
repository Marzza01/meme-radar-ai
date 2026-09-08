"""Smart Money Solana Wallet Tracker — Monitoreo on-chain en tiempo real (v2.1).

Rastrea COMPRAS y SWAPS de las wallets de traders elite en Solana:
  @Cupseyy    → suqh5sHtr8HyJ7q8scBimULPkPpA557prMG47xCHQfK
  @Cented7    → CyaE1VxvBrahnPWkqm5VsdCvyS2QmNht2UFrKJHga54o
  @0xdetweiler → Bi4rd5FH5bYEN8scZ7wevxNZyNmKHdaBcvewdPFxYdLt
  @notdecu    → 4vw54BmAogeRV3vPKWyFet5yf8DTLcREzdSzx4rw9Ud9

Mejoras v2.1:
  - Soporte de wallets[] (array) + wallet (string) en smart_money.json
  - Filtro de programas: Raydium V4, Pump.fun, Jupiter V6, Orca Whirlpool
  - Dedup de mints alertados (ventana 5 min) para evitar spam
  - Detección de SELL (bajada de balance de token)
  - Metadata enriquecida desde DexScreener como fallback de RugCheck
  - Intervalo de poll reducido: 15s por defecto
  - Compatible con hilo daemon del convergence_engine.py

Uso:
    python src/wallet_tracker/solana_tracker.py          # 1 ciclo
    python src/wallet_tracker/solana_tracker.py --watch  # Modo daemon (loop)
    python src/wallet_tracker/solana_tracker.py --test   # Forzar alerta con tx mas reciente
    python src/wallet_tracker/solana_tracker.py --no-telegram  # Sin alertas
"""

import os
import sys
import json
import time
import datetime
import ssl
import urllib.request
import urllib.error
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
STATE_PATH = PROJECT_ROOT / "config" / "wallet_tracker_state.json"

sys.path.insert(0, str(PROJECT_ROOT / "src" / "alertas"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "auditoria"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "fomo"))

# Cargar .env si existe
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

# ─────────────────────────────────────────────
# Endpoints RPC con fallback
# ─────────────────────────────────────────────

DEFAULT_RPCS = [
    os.environ.get("SOLANA_RPC_URL", "").strip(),
    "https://api.mainnet-beta.solana.com",
    "https://rpc.ankr.com/solana",
    "https://solana-mainnet.g.alchemy.com/v2/demo",
]
RPCS = [r for r in DEFAULT_RPCS if r]

# ─────────────────────────────────────────────
# Programas de Solana que nos interesan
# (Solo alertamos si la tx involucra uno de estos)
# ─────────────────────────────────────────────

SWAP_PROGRAMS = {
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium V4",
    "5quBtoiQqxF9Jv6KYKctB59NT3gtJD2Y65kdnB1Uev3h": "Raydium CLMM",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P":  "Pump.fun",
    "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg": "Pump.fun Migrate",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4":  "Jupiter V6",
    "JUP4Pb2UinarKuNNx2xenSMNrnQjeVzjkWGrmyaxNnF":   "Jupiter V4",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc":   "Orca Whirlpool",
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP": "Orca V1",
}

# Ventana de dedup: si ya alertamos un mint en los últimos N segundos, ignorar
DEDUP_WINDOW_SECONDS = 300  # 5 minutos

# ─────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────

def log(msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


# ─────────────────────────────────────────────
# RPC de Solana
# ─────────────────────────────────────────────

_ssl_ctx = None

def _get_ssl():
    global _ssl_ctx
    if _ssl_ctx:
        return _ssl_ctx
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    _ssl_ctx = ctx
    return ctx


def rpc_call(method: str, params: list, max_retries: int = 2) -> object:
    """Ejecuta una llamada JSON-RPC a Solana con fallback entre nodos."""
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params
    }).encode("utf-8")

    for rpc_url in RPCS:
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    rpc_url, data=payload,
                    headers={"Content-Type": "application/json", "User-Agent": "MemeRadar/2.1"}
                )
                with urllib.request.urlopen(req, context=_get_ssl(), timeout=8) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    if "result" in res:
                        return res["result"]
            except Exception:
                time.sleep(0.3 * (attempt + 1))
    return None


# ─────────────────────────────────────────────
# Carga de wallets desde config
# ─────────────────────────────────────────────

def load_smart_money_wallets() -> list:
    """Extrae traders con wallets configuradas. Soporta campo wallet (str) y wallets (list)."""
    if not CONFIG_PATH.exists():
        log(f"Error: {CONFIG_PATH} no encontrado.")
        return []

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    tracked = []
    for tier_key, tier_data in data.get("traders", {}).items():
        weight = tier_data.get("score_weight", 10)
        for m in tier_data.get("members", []):
            handle = m.get("handle", "?")
            alias = m.get("alias", handle)

            # Soportar tanto "wallet": "addr" como "wallets": ["addr1", "addr2"]
            wallets_raw = []
            if m.get("wallets"):
                wallets_raw = m["wallets"] if isinstance(m["wallets"], list) else [m["wallets"]]
            elif m.get("wallet"):
                wallets_raw = [m["wallet"]]

            for wallet in wallets_raw:
                if wallet and 32 <= len(wallet) <= 44:
                    tracked.append({
                        "handle": handle,
                        "alias": alias,
                        "wallet": wallet,
                        "tier": tier_key,
                        "score_weight": weight,
                        "platform": m.get("platform", "solana"),
                        "style": m.get("style", "")
                    })

    return tracked


# ─────────────────────────────────────────────
# Estado persistente
# ─────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"Error guardando estado: {e}")


# ─────────────────────────────────────────────
# Deduplicación de alertas por mint
# ─────────────────────────────────────────────

# Caché en memoria: mint -> timestamp de ultima alerta
_alerted_mints: dict = {}


def is_recently_alerted(mint: str) -> bool:
    """Devuelve True si ya alertamos este mint en los últimos DEDUP_WINDOW_SECONDS."""
    last = _alerted_mints.get(mint, 0)
    return (time.time() - last) < DEDUP_WINDOW_SECONDS


def mark_alerted(mint: str):
    _alerted_mints[mint] = time.time()


# ─────────────────────────────────────────────
# Análisis de transacciones
# ─────────────────────────────────────────────

def get_wallet_signatures(wallet: str, limit: int = 10) -> list:
    """Obtiene las firmas de transacciones más recientes de una wallet."""
    res = rpc_call("getSignaturesForAddress", [wallet, {"limit": limit}])
    return res or []


def get_parsed_transaction(signature: str) -> dict:
    """Obtiene los detalles parseados de una transacción."""
    params = [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    return rpc_call("getTransaction", params) or {}


def detect_swap_program(tx_data: dict) -> str:
    """Detecta si la tx involucra un programa de swap conocido. Devuelve el nombre o ''."""
    try:
        inner_instr = tx_data.get("meta", {}).get("innerInstructions", [])
        account_keys = tx_data.get("transaction", {}).get("message", {}).get("accountKeys", [])

        all_keys = set()
        for ak in account_keys:
            key = ak.get("pubkey") if isinstance(ak, dict) else str(ak)
            if key:
                all_keys.add(key)

        # Revisar también programIds de instrucciones internas
        for inner in inner_instr:
            for instr in inner.get("instructions", []):
                prog_id = instr.get("programId", "")
                if prog_id:
                    all_keys.add(prog_id)

        # Instrucciones del mensaje principal
        main_instrs = tx_data.get("transaction", {}).get("message", {}).get("instructions", [])
        for instr in main_instrs:
            prog_id = instr.get("programId", "")
            if prog_id:
                all_keys.add(prog_id)

        for program_id, name in SWAP_PROGRAMS.items():
            if program_id in all_keys:
                return name
    except Exception:
        pass
    return ""


def analyze_transaction(tx_data: dict, target_wallet: str) -> dict | None:
    """Analiza la transacción para detectar el token y la acción (BUY/SELL/SWAP)."""
    if not tx_data or not tx_data.get("meta"):
        return None

    meta = tx_data["meta"]
    if meta.get("err") is not None:
        return None  # Transacción fallida

    # Detectar programa de swap
    program_name = detect_swap_program(tx_data)

    # Calcular cambio neto de SOL
    pre_bals = meta.get("preBalances", [])
    post_bals = meta.get("postBalances", [])
    account_keys = tx_data.get("transaction", {}).get("message", {}).get("accountKeys", [])

    wallet_idx = -1
    for idx, acc in enumerate(account_keys):
        pubkey = acc.get("pubkey") if isinstance(acc, dict) else str(acc)
        if pubkey == target_wallet:
            wallet_idx = idx
            break

    sol_change = 0.0
    if wallet_idx != -1 and wallet_idx < len(pre_bals) and wallet_idx < len(post_bals):
        diff = pre_bals[wallet_idx] - post_bals[wallet_idx]
        sol_change = round(diff / 1e9, 4)

    # Analizar balances de tokens SPL
    post_tokens = meta.get("postTokenBalances", [])
    pre_tokens = meta.get("preTokenBalances", [])

    pre_map: dict = {}
    for pt in pre_tokens:
        owner = pt.get("owner", "")
        mint = pt.get("mint", "")
        amt = float(pt.get("uiTokenAmount", {}).get("uiAmount") or 0.0)
        if mint:
            pre_map[(owner, mint)] = amt

    bought_mint = None
    sold_mint = None
    action = "SWAP"

    for pt in post_tokens:
        owner = pt.get("owner", "")
        mint = pt.get("mint", "")
        if not mint or mint == "So11111111111111111111111111111111111111112":
            continue

        post_amt = float(pt.get("uiTokenAmount", {}).get("uiAmount") or 0.0)
        pre_amt = pre_map.get((owner, mint), 0.0)

        # Wallet aumentó su posición en este token → COMPRA
        if owner == target_wallet and post_amt > pre_amt and post_amt > 0:
            bought_mint = mint
            action = "BUY"
            break
        # Wallet disminuyó o cerró posición → VENTA
        elif owner == target_wallet and pre_amt > 0 and post_amt < pre_amt:
            sold_mint = mint
            action = "SELL"

    # Fallback: cualquier mint en la transacción
    target_mint = bought_mint or sold_mint
    if not target_mint and post_tokens:
        target_mint = post_tokens[0].get("mint")
        if target_mint == "So11111111111111111111111111111111111111112" and len(post_tokens) > 1:
            target_mint = post_tokens[1].get("mint")

    if not target_mint:
        return None

    # Si el sol_change es 0 y la acción es SELL, ajustar
    sol_received = 0.0
    if action == "SELL" and sol_change < 0:
        sol_received = abs(sol_change)
        sol_change = 0.0

    return {
        "mint": target_mint,
        "action": action,
        "sol_spent": max(sol_change, 0.0),
        "sol_received": sol_received,
        "program": program_name,
        "block_time": tx_data.get("blockTime")
    }


# ─────────────────────────────────────────────
# Enriquecimiento de metadata del token
# ─────────────────────────────────────────────

def get_token_metadata(mint: str) -> dict:
    """Obtiene nombre y símbolo del token desde DexScreener como fallback."""
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
        req = urllib.request.Request(url, headers={"User-Agent": "MemeRadar/2.1"})
        with urllib.request.urlopen(req, context=_get_ssl(), timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pairs = data.get("pairs", [])
            if pairs:
                pair = pairs[0]
                base = pair.get("baseToken", {})
                return {
                    "symbol": base.get("symbol", mint[:6]),
                    "name": base.get("name", "Unknown"),
                    "price_usd": pair.get("priceUsd", ""),
                    "market_cap": pair.get("fdv", ""),
                    "liquidity": pair.get("liquidity", {}).get("usd", ""),
                    "volume_5m": pair.get("volume", {}).get("m5", ""),
                    "pair_url": pair.get("url", ""),
                    "is_pump": "pump.fun" in (pair.get("url", "") or "").lower()
                }
    except Exception:
        pass
    return {"symbol": mint[:6], "name": "Unknown Token", "price_usd": "", "market_cap": "", "liquidity": "", "volume_5m": "", "pair_url": ""}


# ─────────────────────────────────────────────
# Procesamiento de una wallet
# ─────────────────────────────────────────────

def process_wallet(trader_info: dict, state: dict, send_telegram: bool = True, force_alert: bool = False) -> list:
    """
    Revisa una wallet para detectar transacciones nuevas de swap/compra.
    Solo alerta si la transacción involucra un programa de swap conocido.
    """
    wallet = trader_info["wallet"]
    alias = trader_info["alias"]
    handle = trader_info["handle"]

    log(f"  Revisando @{handle} [{wallet[:6]}...{wallet[-4:]}]")

    signatures = get_wallet_signatures(wallet, limit=8)
    if not signatures:
        log(f"    -> Sin respuesta RPC")
        return []

    last_seen = state.get(f"sig_{wallet}")
    new_sigs = []

    if not last_seen and not force_alert:
        # Primera ejecución: guardar punto de partida sin alertar
        state[f"sig_{wallet}"] = signatures[0]["signature"]
        save_state(state)
        log(f"    -> Inicializado en sig {signatures[0]['signature'][:12]}...")
        return []

    # Recolectar firmas nuevas desde el ultimo punto
    for sig_info in signatures:
        sig = sig_info["signature"]
        if sig == last_seen and not force_alert:
            break
        if sig_info.get("err") is None:
            new_sigs.append(sig_info)

    if not new_sigs:
        log(f"    -> Sin transacciones nuevas")
        return []

    log(f"    \U0001f525 {len(new_sigs)} tx nueva(s) detectada(s)!")

    # Actualizar punto de partida
    state[f"sig_{wallet}"] = signatures[0]["signature"]
    state["last_scan"] = datetime.datetime.now().isoformat()
    save_state(state)

    processed = []

    for sig_info in new_sigs[:3]:  # Máx 3 txs por ciclo
        sig = sig_info["signature"]
        tx_data = get_parsed_transaction(sig)
        analysis = analyze_transaction(tx_data, wallet)

        if not analysis:
            continue

        mint = analysis["mint"]
        action = analysis["action"]
        sol_spent = analysis["sol_spent"]
        program = analysis.get("program", "")

        # FILTRO CLAVE: solo alertar si es un swap en programa conocido
        # (Si program está vacío, es otra cosa: staking, governance, NFT, etc.)
        if not program and not force_alert:
            log(f"    -> Ignorando tx sin programa de swap reconocido (sig: {sig[:12]}...)")
            continue

        # Deduplicación: no alertar el mismo mint dos veces en 5 min
        if is_recently_alerted(mint) and not force_alert:
            log(f"    -> Mint {mint[:8]}... ya alertado recientemente (dedup)")
            continue

        log(f"\n    [ON-CHAIN] @{handle} | {action} | {program} | Mint: {mint[:12]}... | {sol_spent:.3f} SOL")

        # 1. Enriquecer metadata del token
        token_meta = get_token_metadata(mint)
        asset_symbol = token_meta.get("symbol", mint[:6])
        asset_name = token_meta.get("name", "Unknown")
        pair_url = token_meta.get("pair_url", "")

        # 2. Auditoría RugCheck (solo para tokens Solana)
        audit_fmt = None
        try:
            from rugcheck import audit_token, format_audit_for_alert
            audit_res = audit_token(mint)
            if audit_res.get("success"):
                raw = audit_res.get("raw_audit", {})
                t_meta = raw.get("tokenMeta", {}) or raw.get("fileMeta", {}) or {}
                if t_meta.get("name"):
                    asset_name = t_meta["name"]
                if t_meta.get("symbol"):
                    asset_symbol = t_meta["symbol"]
                audit_fmt = format_audit_for_alert(audit_res)
                log(f"    RugCheck: {audit_res.get('risk_rating','?')} | Freeze: {audit_res.get('freeze_authority','?')}")
        except Exception as e:
            log(f"    RugCheck error: {e}")

        # 3. Métricas de mercado
        metrics = {}
        if token_meta.get("market_cap"):
            mc = token_meta["market_cap"]
            metrics["market_cap"] = f"${mc:,.0f}" if isinstance(mc, (int, float)) else str(mc)
        if token_meta.get("liquidity"):
            liq = token_meta["liquidity"]
            metrics["liquidity"] = f"${liq:,.0f}" if isinstance(liq, (int, float)) else str(liq)
        if token_meta.get("volume_5m"):
            vol = token_meta["volume_5m"]
            metrics["volume_5m"] = f"${vol:,.0f}" if isinstance(vol, (int, float)) else str(vol)
        if token_meta.get("price_usd"):
            metrics["price"] = f"${token_meta['price_usd']}"

        # Fallback a FomoTracker si DexScreener no tiene data
        if not metrics:
            try:
                from fomo_tracker import FomoTracker
                tracker = FomoTracker()
                mkt = tracker.get_token_market_data(mint)
                if mkt:
                    metrics = {
                        "market_cap": mkt.get("market_cap", "N/A"),
                        "liquidity": mkt.get("liquidity", "N/A"),
                        "volume_5m": mkt.get("volume_5m", "N/A")
                    }
                    if not pair_url and mkt.get("pair_url"):
                        pair_url = mkt["pair_url"]
            except Exception:
                pass

        # 4. Construir enlaces de ejecución directa (1-click)
        actions = {}
        if mint.endswith("pump"):
            actions["Pump.fun"] = f"https://pump.fun/coin/{mint}"
        actions["Photon"] = f"https://photon-sol.tinyastro.io/en/lp/{mint}"
        actions["BullX"] = f"https://bullx.io/terminal?chainId=1399811149&address={mint}"
        actions["Trojan"] = f"https://t.me/solana_trojanbot?start=r-{mint}"
        if pair_url:
            actions["DexScreener"] = pair_url
        else:
            actions["DexScreener"] = f"https://dexscreener.com/solana/{mint}"
        actions["Solscan TX"] = f"https://solscan.io/tx/{sig}"

        # 5. Enviar Alerta Copytrade a Telegram
        if send_telegram:
            try:
                from telegram_bot import send_copytrade_alert
                sent = send_copytrade_alert(
                    trader_alias=alias,
                    trader_handle=handle,
                    wallet=wallet,
                    action_type=f"{action} ({program})" if program else action,
                    asset_name=asset_name,
                    asset_symbol=asset_symbol,
                    mint_address=mint,
                    sol_amount=sol_spent,
                    metrics=metrics,
                    audit=audit_fmt,
                    actions=actions
                )
                if sent:
                    log(f"    \u2705 Alerta COPYTRADE enviada: ${asset_symbol} ({action})")
                    mark_alerted(mint)
                    try:
                        sys.path.insert(0, str(PROJECT_ROOT / "src" / "bitacora"))
                        from logger import log_alert, SIGNAL_COPYTRADE, LAYER_PUMPFUN, LAYER_DEXSCREENER, LAYER_SEGURIDAD
                        ct_layers = [LAYER_DEXSCREENER]
                        if "pump" in str(program).lower() or mint.endswith("pump"):
                            ct_layers.insert(0, LAYER_PUMPFUN)
                        if audit_fmt:
                            ct_layers.append(LAYER_SEGURIDAD)
                        price_num = str(metrics.get("price", "")).lstrip("$")
                        aid = log_alert(
                            token=asset_symbol,
                            signal_type=SIGNAL_COPYTRADE,
                            mint=mint,
                            chain="solana",
                            score=70,
                            layers=ct_layers,
                            signals=[f"Copytrade {action} en {program}", f"{sol_spent:.3f} SOL por @{handle}"],
                            traders_involved=[f"@{handle}"],
                            metrics=metrics,
                            audit=audit_fmt,
                            price_at_alert=price_num
                        )
                        log(f"    [BITACORA] Copytrade registrado ID: {aid} (Capas: {'+'.join(ct_layers)})")
                    except Exception as cle:
                        log(f"    [BITACORA] Error registrando copytrade: {cle}")
                else:
                    log(f"    \u274c Fallo el envio a Telegram")
            except Exception as e:
                log(f"    \u274c Error enviando alerta: {e}")
        else:
            log(f"    [SIN TELEGRAM] {action} ${asset_symbol} ({asset_name}) | {sol_spent:.3f} SOL | {program}")
            mark_alerted(mint)

        processed.append({
            "trader": handle,
            "token": asset_symbol,
            "mint": mint,
            "action": action,
            "program": program,
            "sol": sol_spent
        })

    return processed


# ─────────────────────────────────────────────
# Runner principal
# ─────────────────────────────────────────────

def run_wallet_tracker(
    send_telegram: bool = True,
    loop: bool = False,
    interval_seconds: int = 15,
    force_first_alert: bool = False,
    target_handles: list = None
) -> None:
    """
    Ejecuta el ciclo de monitoreo sobre las wallets de Smart Money.

    Args:
        send_telegram:       Si True, envía alertas de Copytrade a Telegram.
        loop:                Si True, corre en bucle indefinido.
        interval_seconds:    Segundos entre ciclos de sondeo (default: 15s).
        force_first_alert:   Si True, fuerza alerta con la tx más reciente.
        target_handles:      Lista de handles para filtrar. None = todos los que tienen wallet.
    """
    log("=" * 60)
    log("MEME RADAR // SMART MONEY WALLET TRACKER v2.1 (Solana)")
    log("=" * 60)

    wallets = load_smart_money_wallets()

    # Filtrar por handles si se especificaron
    if target_handles:
        targets_lower = [h.lower().lstrip("@") for h in target_handles]
        wallets = [w for w in wallets if w["handle"].lower() in targets_lower]

    if not wallets:
        log("\u26a0\ufe0f No se encontraron wallets configuradas.")
        log("  Verifica que los traders tengan el campo 'wallet' o 'wallets' en smart_money.json")
        return

    log(f"Wallets monitoreadas ({len(wallets)}):")
    for w in wallets:
        prog_filter = " | Solo swaps en: Raydium, Pump.fun, Jupiter, Orca"
        log(f"  \u2022 @{w['handle']} ({w['alias']}): {w['wallet'][:8]}...{w['wallet'][-6:]}")
    log(f"Intervalo de sondeo: {interval_seconds}s")
    log(f"Programas filtrados: Raydium V4, Pump.fun, Jupiter V6, Orca")
    log(f"Dedup ventana: {DEDUP_WINDOW_SECONDS}s")
    log("")

    state = load_state()
    cycle = 0

    while True:
        cycle += 1
        log(f"\n[Ciclo {cycle}] {datetime.datetime.now().strftime('%H:%M:%S')} — Escaneando {len(wallets)} wallet(s)...")

        for w_info in wallets:
            try:
                results = process_wallet(
                    w_info, state,
                    send_telegram=send_telegram,
                    force_alert=(force_first_alert and cycle == 1)
                )
                if results:
                    for r in results:
                        log(f"  \U0001f3af {r['action']} ${r['token']} | {r['sol']:.3f} SOL | {r['program']}")
            except Exception as e:
                log(f"  Error en @{w_info['handle']}: {e}")
            time.sleep(0.8)  # Pausa breve entre wallets

        if not loop:
            log("\nEscaneo unico completado.")
            break

        log(f"\nProximo scan en {interval_seconds}s...")
        try:
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            log("\nWallet Tracker detenido.")
            break


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    send_tg = "--no-telegram" not in args
    is_loop = "--watch" in args or "-w" in args
    force = "--test" in args or "--force" in args
    interval = 15

    # Leer intervalo custom: --interval 30
    if "--interval" in args:
        try:
            idx = args.index("--interval")
            interval = int(args[idx + 1])
        except Exception:
            pass

    # Filtrar handles: --handles cupseyy cented7
    target_handles = None
    if "--handles" in args:
        try:
            idx = args.index("--handles")
            target_handles = args[idx + 1:]
        except Exception:
            pass

    run_wallet_tracker(
        send_telegram=send_tg,
        loop=is_loop,
        interval_seconds=interval,
        force_first_alert=force,
        target_handles=target_handles
    )
