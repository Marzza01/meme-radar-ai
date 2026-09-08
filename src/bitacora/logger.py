"""Bitácora — Logger de alertas de Meme Radar AI (v2.2).

Registra cada alerta generada (convergencia, discovery, copytrade) en un archivo
JSON diario, incluyendo las 5 Capas de Análisis y el tipo de señal.
Además, actualiza automáticamente el precio 24h después de la alerta
para medir el PnL real y permitir el aprendizaje autónomo.

Estructura del log: config/bitacora/YYYY-MM-DD.json
"""

import os
import sys
import json
import time
import uuid
import ssl
import datetime
import urllib.request
from pathlib import Path

# Soporte UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).parent.parent.parent
BITACORA_DIR = PROJECT_ROOT / "config" / "bitacora"
BITACORA_DIR.mkdir(parents=True, exist_ok=True)

# Tipos de señal
SIGNAL_CONVERGENCE = "convergence"
SIGNAL_DISCOVERY   = "discovery"
SIGNAL_COPYTRADE   = "copytrade"

# Capas estándar del radar
LAYER_X           = "X"
LAYER_FOMO        = "FOMO"
LAYER_PUMPFUN     = "Pump.fun"
LAYER_DEXSCREENER = "DexScreener"
LAYER_SEGURIDAD   = "Seguridad"

ALL_LAYERS = [LAYER_X, LAYER_FOMO, LAYER_PUMPFUN, LAYER_DEXSCREENER, LAYER_SEGURIDAD]

# Outcomes posibles
OUTCOME_TP      = "true_positive"
OUTCOME_FP      = "false_positive"
OUTCOME_PARTIAL = "partial"
OUTCOME_PENDING = None


def log(msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[BITACORA][{ts}] {msg}")


def _today_path() -> Path:
    """Devuelve la ruta al archivo de log del día actual."""
    date_str = datetime.date.today().isoformat()
    return BITACORA_DIR / f"{date_str}.json"


def _date_path(date: datetime.date) -> Path:
    return BITACORA_DIR / f"{date.isoformat()}.json"


def load_daily_log(date: datetime.date = None) -> list:
    """Carga el log del día. Devuelve lista de entradas."""
    path = _date_path(date) if date else _today_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_daily_log(entries: list, date: datetime.date = None):
    """Guarda el log del día."""
    path = _date_path(date) if date else _today_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"Error guardando log: {e}")


def generate_alert_id(token: str, signal_type: str) -> str:
    """Genera un ID único para la alerta."""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    short = token.upper()[:8].replace("/", "").replace("$", "")
    prefix = signal_type[:3] if signal_type else "alt"
    suffix = uuid.uuid4().hex[:4]
    return f"{prefix}_{ts}_{short}_{suffix}"


def log_alert(
    token: str,
    signal_type: str = SIGNAL_CONVERGENCE,
    alert_type: str = None,  # compatibilidad hacia atrás
    mint: str = "",
    chain: str = "solana",
    score: int = 0,
    layers: list = None,
    signals: list = None,
    traders_involved: list = None,
    metrics: dict = None,
    audit: dict = None,
    price_at_alert: str = "",
    notes: str = ""
) -> str:
    """
    Registra una nueva alerta en la bitácora del día con trazabilidad de 5 Capas.

    Args:
        token: Símbolo o nombre del token ($BONK, PEPE)
        signal_type: 'convergence' | 'discovery' | 'copytrade'
        layers: Lista de capas participantes, ej: ["X", "FOMO", "DexScreener", "Seguridad"]
        signals: Lista de detonantes o motivos
        traders_involved: Lista de handles de traders elite involucrados
        metrics: Dict con métricas on-chain (mc, liq, vol)
        audit: Dict con auditoría de RugCheck
        price_at_alert: Precio USD al disparar alerta

    Returns:
        str: ID único de la alerta
    """
    stype = signal_type or alert_type or SIGNAL_CONVERGENCE
    alert_id = generate_alert_id(token, stype)
    now = datetime.datetime.now().isoformat()

    # Si no se especificaron capas, inferir capas por defecto según el tipo de señal
    inferred_layers = layers or []
    if not inferred_layers:
        if stype == SIGNAL_CONVERGENCE:
            inferred_layers = [LAYER_X, LAYER_FOMO, LAYER_DEXSCREENER, LAYER_SEGURIDAD]
        elif stype == SIGNAL_DISCOVERY:
            inferred_layers = [LAYER_X, LAYER_DEXSCREENER]
        elif stype == SIGNAL_COPYTRADE:
            inferred_layers = [LAYER_PUMPFUN, LAYER_DEXSCREENER]

    entry = {
        "id": alert_id,
        "timestamp": now,
        "date": datetime.date.today().isoformat(),
        "signal_type": stype,
        "type": stype,  # redundancia para compatibilidad
        "token": token.upper().lstrip("$"),
        "mint": mint or "",
        "chain": chain,
        "score": score,
        "layers": inferred_layers,
        "signals": signals or [],
        "traders_involved": traders_involved or [],
        "metrics_at_alert": metrics or {},
        "audit": audit or {},
        "price_at_alert": str(price_at_alert) if price_at_alert else "",
        "price_24h_later": None,
        "pnl_pct": None,
        "outcome": None,
        "feedback": None,
        "feedback_timestamp": None,
        "notes": notes,
        "auto_evaluated": False
    }

    entries = load_daily_log()
    entries.append(entry)
    save_daily_log(entries)

    layers_str = "+".join(inferred_layers)
    log(f"Alerta registrada: {alert_id} | ${token} | score={score} | tipo={stype} | capas=[{layers_str}]")
    return alert_id


def set_feedback(alert_id: str, outcome: str, notes: str = "") -> bool:
    """
    Actualiza el outcome de una alerta por feedback manual del usuario.

    Args:
        alert_id: ID de la alerta
        outcome: 'true_positive', 'false_positive', 'partial'
        notes: comentario adicional

    Returns:
        bool: True si se encontró y actualizó la alerta
    """
    valid_outcomes = {OUTCOME_TP, OUTCOME_FP, OUTCOME_PARTIAL}
    if outcome not in valid_outcomes:
        log(f"Outcome inválido: {outcome}. Usar: {valid_outcomes}")
        return False

    # Buscar en los logs de los últimos 5 días
    for days_back in range(5):
        date = datetime.date.today() - datetime.timedelta(days=days_back)
        entries = load_daily_log(date)
        for entry in entries:
            if entry.get("id") == alert_id:
                entry["outcome"] = outcome
                entry["feedback"] = "manual"
                entry["feedback_timestamp"] = datetime.datetime.now().isoformat()
                if notes:
                    entry["notes"] = notes
                save_daily_log(entries, date)
                log(f"Feedback aplicado: {alert_id} → {outcome}")
                return True

    log(f"Alerta no encontrada: {alert_id}")
    return False


def _get_ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _fetch_price_dex(mint: str) -> str | None:
    """Obtiene el precio actual desde DexScreener."""
    if not mint or len(mint) < 20:
        return None
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
        req = urllib.request.Request(url, headers={"User-Agent": "MemeRadar/2.2"})
        with urllib.request.urlopen(req, context=_get_ssl_ctx(), timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pairs = data.get("pairs", [])
            if pairs:
                price = pairs[0].get("priceUsd", "")
                return str(price) if price else None
    except Exception:
        pass
    return None


def _calculate_pnl(price_then: str, price_now: str) -> float | None:
    """Calcula el % de cambio entre dos precios."""
    try:
        p0 = float(price_then)
        p1 = float(price_now)
        if p0 <= 0:
            return None
        return round(((p1 - p0) / p0) * 100, 2)
    except Exception:
        return None


def _classify_outcome_by_pnl(pnl_pct: float) -> str:
    """Clasifica automáticamente el resultado según el PnL."""
    if pnl_pct is None:
        return OUTCOME_PENDING
    if pnl_pct >= 20:
        return OUTCOME_TP       # +20%+ es un verdadero positivo
    if pnl_pct >= -10:
        return OUTCOME_PARTIAL  # Entre -10% y +20% es parcial
    return OUTCOME_FP           # Caída de más de -10% es falso positivo


def run_price_updater(days_back: int = 2) -> int:
    """
    Revisa las alertas de los últimos N días sin precio 24h y las actualiza.
    Llamar periódicamente (cada hora o ciclo) desde el engine.
    """
    now = datetime.datetime.now()
    updated = 0

    for d in range(days_back + 1):
        date = datetime.date.today() - datetime.timedelta(days=d)
        entries = load_daily_log(date)
        changed = False

        for entry in entries:
            # Ya tiene precio o no tiene mint → skip
            if entry.get("price_24h_later") or not entry.get("mint"):
                continue

            # Solo actualizar si han pasado al menos 23 horas
            try:
                alert_time = datetime.datetime.fromisoformat(entry["timestamp"])
                hours_since = (now - alert_time).total_seconds() / 3600
                if hours_since < 23:
                    continue
            except Exception:
                continue

            # Obtener precio actual
            price_now = _fetch_price_dex(entry["mint"])
            if not price_now:
                continue

            entry["price_24h_later"] = price_now
            pnl = _calculate_pnl(entry.get("price_at_alert", ""), price_now)
            entry["pnl_pct"] = pnl
            entry["auto_evaluated"] = True

            # Solo poner outcome automático si el usuario no ha dado feedback manual
            if not entry.get("feedback"):
                entry["outcome"] = _classify_outcome_by_pnl(pnl)

            changed = True
            updated += 1
            pnl_str = f"{pnl:+.1f}%" if pnl is not None else "N/A"
            log(f"Precio 24h actualizado: {entry['id']} | ${entry['token']} | PnL: {pnl_str} | Outcome: {entry['outcome']}")

        if changed:
            save_daily_log(entries, date)

    return updated


def get_recent_alerts(n: int = 15, days_back: int = 3) -> list:
    """Devuelve las N alertas más recientes de los últimos días."""
    all_entries = []
    for d in range(days_back):
        date = datetime.date.today() - datetime.timedelta(days=d)
        entries = load_daily_log(date)
        all_entries.extend(entries)

    all_entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return all_entries[:n]


def get_multi_day_entries(days_back: int = 7) -> list:
    """Devuelve todas las entradas de los últimos N días agregadas."""
    all_entries = []
    for d in range(days_back):
        date = datetime.date.today() - datetime.timedelta(days=d)
        entries = load_daily_log(date)
        all_entries.extend(entries)
    return all_entries


def get_daily_stats(date: datetime.date = None) -> dict:
    """
    Calcula estadísticas del día para el reporter y learner, incluyendo
    desglose por 5 capas, tipos de señal, traders y señales individuales.
    """
    entries = load_daily_log(date)
    if not entries:
        return {
            "total": 0, "tp": 0, "fp": 0, "partial": 0, "pending": 0,
            "accuracy": 0.0, "by_type": {}, "by_signal_type": {},
            "by_layer": {}, "by_trader": {}, "by_signal": {},
            "pnl_list": [], "best_alert": None, "worst_alert": None
        }

    stats = {
        "total": len(entries),
        "tp": 0,
        "fp": 0,
        "partial": 0,
        "pending": 0,
        "by_type": {SIGNAL_CONVERGENCE: 0, SIGNAL_DISCOVERY: 0, SIGNAL_COPYTRADE: 0},
        "by_signal_type": {},  # type -> {tp, fp, partial, total, accuracy}
        "by_layer": {},        # layer -> {tp, fp, partial, total, accuracy}
        "by_trader": {},       # handle -> {tp, fp, partial, total, accuracy}
        "by_signal": {},       # signal_text -> {tp, fp, partial, total}
        "pnl_list": [],
        "best_alert": None,
        "worst_alert": None,
    }

    best_pnl = None
    worst_pnl = None

    for entry in entries:
        outcome = entry.get("outcome")
        pnl = entry.get("pnl_pct")
        stype = entry.get("signal_type") or entry.get("type", SIGNAL_CONVERGENCE)
        layers = entry.get("layers") or []

        if outcome == OUTCOME_TP:
            stats["tp"] += 1
        elif outcome == OUTCOME_FP:
            stats["fp"] += 1
        elif outcome == OUTCOME_PARTIAL:
            stats["partial"] += 1
        else:
            stats["pending"] += 1

        # Count by type
        if stype in stats["by_type"]:
            stats["by_type"][stype] += 1
        else:
            stats["by_type"][stype] = 1

        # Stats by signal_type (con TP/FP)
        if stype not in stats["by_signal_type"]:
            stats["by_signal_type"][stype] = {"tp": 0, "fp": 0, "partial": 0, "total": 0}
        stats["by_signal_type"][stype]["total"] += 1
        if outcome == OUTCOME_TP:
            stats["by_signal_type"][stype]["tp"] += 1
        elif outcome == OUTCOME_FP:
            stats["by_signal_type"][stype]["fp"] += 1
        elif outcome == OUTCOME_PARTIAL:
            stats["by_signal_type"][stype]["partial"] += 1

        # Stats by layer (evaluación de las 5 capas)
        for lyr in layers:
            if lyr not in stats["by_layer"]:
                stats["by_layer"][lyr] = {"tp": 0, "fp": 0, "partial": 0, "total": 0}
            stats["by_layer"][lyr]["total"] += 1
            if outcome == OUTCOME_TP:
                stats["by_layer"][lyr]["tp"] += 1
            elif outcome == OUTCOME_FP:
                stats["by_layer"][lyr]["fp"] += 1
            elif outcome == OUTCOME_PARTIAL:
                stats["by_layer"][lyr]["partial"] += 1

        # PnL tracking
        if pnl is not None:
            stats["pnl_list"].append(pnl)
            if best_pnl is None or pnl > best_pnl:
                best_pnl = pnl
                stats["best_alert"] = entry
            if worst_pnl is None or pnl < worst_pnl:
                worst_pnl = pnl
                stats["worst_alert"] = entry

        # Stats por trader
        for trader in entry.get("traders_involved", []):
            t = trader.lstrip("@").lower()
            if t not in stats["by_trader"]:
                stats["by_trader"][t] = {"tp": 0, "fp": 0, "partial": 0, "total": 0}
            stats["by_trader"][t]["total"] += 1
            if outcome == OUTCOME_TP:
                stats["by_trader"][t]["tp"] += 1
            elif outcome == OUTCOME_FP:
                stats["by_trader"][t]["fp"] += 1
            elif outcome == OUTCOME_PARTIAL:
                stats["by_trader"][t]["partial"] += 1

        # Stats por señal específica
        for signal in entry.get("signals", []):
            s = signal[:50]
            if s not in stats["by_signal"]:
                stats["by_signal"][s] = {"tp": 0, "fp": 0, "partial": 0, "total": 0}
            stats["by_signal"][s]["total"] += 1
            if outcome == OUTCOME_TP:
                stats["by_signal"][s]["tp"] += 1
            elif outcome == OUTCOME_FP:
                stats["by_signal"][s]["fp"] += 1
            elif outcome == OUTCOME_PARTIAL:
                stats["by_signal"][s]["partial"] += 1

    # Calcular accuracy general
    evaluated = stats["tp"] + stats["fp"] + stats["partial"]
    stats["accuracy"] = round((stats["tp"] + 0.5 * stats["partial"]) / max(evaluated, 1) * 100, 1) if evaluated > 0 else 0.0

    return stats


if __name__ == "__main__":
    aid = log_alert(
        token="TESTCOIN",
        signal_type=SIGNAL_CONVERGENCE,
        mint="So11111111111111111111111111111111111111112",
        score=75,
        layers=[LAYER_X, LAYER_FOMO, LAYER_DEXSCREENER, LAYER_SEGURIDAD],
        signals=["Smart Money x2", "Volume spike 3.5x", "RugCheck: Good"],
        traders_involved=["@Cupseyy", "@notdecu"],
        metrics={"market_cap": "$500K", "liquidity": "$80K"},
        price_at_alert="0.000005"
    )
    print(f"\nAlerta test registrada: {aid}")
    print(f"Log guardado en: {_today_path()}")
    stats = get_daily_stats()
    print(f"Total: {stats['total']} | Capas: {list(stats['by_layer'].keys())}")
