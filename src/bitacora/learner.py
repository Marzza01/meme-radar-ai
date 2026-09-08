"""Bitácora — Motor de Aprendizaje Autónomo de Meme Radar AI (v2.2).

Analiza las alertas evaluadas (por feedback manual o PnL real 24h) y calibra:
1. layer_weights: Pesos de las 5 Capas de Análisis (X, FOMO, Pump.fun, DexScreener, Seguridad)
2. trader_weights: Pesos individuales de los traders elite
3. threshold_score: Umbral mínimo de score para disparar alertas
4. signal_multipliers: Multiplicador según tipo de señal (convergence, discovery, copytrade)

Se ejecuta cada noche a las 23:55 tras la generación del informe diario.
"""

import os
import sys
import json
import datetime
from pathlib import Path

# Soporte UTF-8 en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
WEIGHTS_FILE = CONFIG_DIR / "learned_weights.json"
SMART_MONEY_FILE = CONFIG_DIR / "smart_money.json"

sys.path.insert(0, str(PROJECT_ROOT / "src" / "alertas"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "bitacora"))


def log(msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[LEARNER][{ts}] {msg}")


def load_learned_weights() -> dict:
    """Carga los pesos aprendidos actuales."""
    if not WEIGHTS_FILE.exists():
        return {
            "updated_at": datetime.datetime.now().isoformat(),
            "trader_weights": {},
            "layer_weights": {
                "X": 30,
                "FOMO": 30,
                "Pump.fun": 20,
                "DexScreener": 10,
                "Seguridad": 10
            },
            "threshold_score": 65,
            "signal_multipliers": {
                "convergence": 1.5,
                "discovery": 1.0,
                "copytrade": 0.8
            },
            "history": []
        }

    try:
        with open(WEIGHTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"Error cargando learned_weights: {e}")
        return {}


def save_learned_weights(weights: dict):
    """Guarda los pesos aprendidos actualizados."""
    try:
        with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
            json.dump(weights, f, indent=2, ensure_ascii=False)
        log(f"Pesos actualizados guardados en: {WEIGHTS_FILE}")
    except Exception as e:
        log(f"Error guardando learned_weights: {e}")


def _calc_acc(tp: int, fp: int, partial: int) -> float:
    ev = tp + fp + partial
    if ev == 0:
        return 0.0
    return round((tp + 0.5 * partial) / ev * 100, 1)


def apply_daily_learning(date: datetime.date = None, send_telegram: bool = True) -> dict:
    """
    Aplica el ciclo diario de aprendizaje autónomo analizando los últimos 7 días.

    Returns:
        dict: Resumen de los ajustes aplicados
    """
    from logger import get_daily_stats, get_multi_day_entries

    if date is None:
        date = datetime.date.today()

    weights = load_learned_weights()
    adjustments = []

    # Cargar histórico de los últimos 7 días
    recent_entries = get_multi_day_entries(days_back=7)

    # ─────────────────────────────────────────────────────────────
    # 1. APRENDIZAJE POR CAPAS (5 CAPAS)
    # ─────────────────────────────────────────────────────────────
    layer_stats = {}
    for entry in recent_entries:
        outcome = entry.get("outcome")
        if not outcome:
            continue
        for lyr in entry.get("layers", []):
            if lyr not in layer_stats:
                layer_stats[lyr] = {"tp": 0, "fp": 0, "partial": 0}
            if outcome == "true_positive":
                layer_stats[lyr]["tp"] += 1
            elif outcome == "false_positive":
                layer_stats[lyr]["fp"] += 1
            elif outcome == "partial":
                layer_stats[lyr]["partial"] += 1

    current_layer_weights = weights.setdefault("layer_weights", {
        "X": 30, "FOMO": 30, "Pump.fun": 20, "DexScreener": 10, "Seguridad": 10
    })

    for lyr, sdata in layer_stats.items():
        ev = sdata["tp"] + sdata["fp"] + sdata["partial"]
        if ev >= 3:  # Mínimo 3 observaciones evaluadas
            acc = _calc_acc(sdata["tp"], sdata["fp"], sdata["partial"])
            old_w = current_layer_weights.get(lyr, 20)

            # Si precisión > 70% -> subir peso +2 (max 40)
            if acc > 70 and old_w < 40:
                new_w = min(40, old_w + 2)
                current_layer_weights[lyr] = new_w
                adjustments.append(f"Capa '{lyr}' peso: {old_w} → {new_w} (+2 por {acc}% acierto en 7d)")
            # Si precisión < 30% -> bajar peso -2 (min 5)
            elif acc < 30 and old_w > 5:
                new_w = max(5, old_w - 2)
                current_layer_weights[lyr] = new_w
                adjustments.append(f"Capa '{lyr}' peso: {old_w} → {new_w} (-2 por {acc}% acierto en 7d)")

    # ─────────────────────────────────────────────────────────────
    # 2. APRENDIZAJE POR TRADER
    # ─────────────────────────────────────────────────────────────
    trader_stats = {}
    for entry in recent_entries:
        outcome = entry.get("outcome")
        if not outcome:
            continue
        for tr in entry.get("traders_involved", []):
            handle = tr.lstrip("@")
            if handle not in trader_stats:
                trader_stats[handle] = {"tp": 0, "fp": 0, "partial": 0}
            if outcome == "true_positive":
                trader_stats[handle]["tp"] += 1
            elif outcome == "false_positive":
                trader_stats[handle]["fp"] += 1
            elif outcome == "partial":
                trader_stats[handle]["partial"] += 1

    current_trader_weights = weights.setdefault("trader_weights", {})

    for handle, sdata in trader_stats.items():
        ev = sdata["tp"] + sdata["fp"] + sdata["partial"]
        if ev >= 2:  # Mínimo 2 alertas
            acc = _calc_acc(sdata["tp"], sdata["fp"], sdata["partial"])
            old_w = current_trader_weights.get(handle, 20)

            if acc > 70 and old_w < 35:
                new_w = min(35, old_w + 2)
                current_trader_weights[handle] = new_w
                adjustments.append(f"Trader @{handle} peso: {old_w} → {new_w} (+2 por {acc}% precisión)")
            elif acc < 30 and old_w > 5:
                new_w = max(5, old_w - 2)
                current_trader_weights[handle] = new_w
                adjustments.append(f"Trader @{handle} peso: {old_w} → {new_w} (-2 por {acc}% precisión)")

    # ─────────────────────────────────────────────────────────────
    # 3. APRENDIZAJE DE UMBRAL DE SCORE (THRESHOLD)
    # ─────────────────────────────────────────────────────────────
    today_stats = get_daily_stats(date)
    ev_today = today_stats["tp"] + today_stats["fp"] + today_stats["partial"]
    old_threshold = weights.get("threshold_score", 65)

    if ev_today >= 3:
        fp_rate = (today_stats["fp"] / ev_today) * 100
        # Demasiados falsos positivos (>60%) -> ser más estricto (+5 pts)
        if fp_rate > 60 and old_threshold < 80:
            new_th = min(80, old_threshold + 5)
            weights["threshold_score"] = new_th
            adjustments.append(f"Umbral de score subido: {old_threshold} → {new_th} (+5 por {fp_rate:.0f}% FP hoy)")
        # Alta precisión (FP < 20%) -> permitir capturar más oportunidades (-2 pts)
        elif fp_rate < 20 and old_threshold > 45:
            new_th = max(45, old_threshold - 2)
            weights["threshold_score"] = new_th
            adjustments.append(f"Umbral de score bajado: {old_threshold} → {new_th} (-2 por alta precisión)")

    # ─────────────────────────────────────────────────────────────
    # 4. APRENDIZAJE POR TIPO DE SEÑAL (MULTIPLIERS)
    # ─────────────────────────────────────────────────────────────
    sig_type_stats = {}
    for entry in recent_entries:
        outcome = entry.get("outcome")
        if not outcome:
            continue
        stype = entry.get("signal_type") or entry.get("type", "convergence")
        if stype not in sig_type_stats:
            sig_type_stats[stype] = {"tp": 0, "fp": 0, "partial": 0}
        if outcome == "true_positive":
            sig_type_stats[stype]["tp"] += 1
        elif outcome == "false_positive":
            sig_type_stats[stype]["fp"] += 1
        elif outcome == "partial":
            sig_type_stats[stype]["partial"] += 1

    current_multipliers = weights.setdefault("signal_multipliers", {
        "convergence": 1.5, "discovery": 1.0, "copytrade": 0.8
    })

    for stype, sdata in sig_type_stats.items():
        ev = sdata["tp"] + sdata["fp"] + sdata["partial"]
        if ev >= 3:
            acc = _calc_acc(sdata["tp"], sdata["fp"], sdata["partial"])
            old_mult = current_multipliers.get(stype, 1.0)
            if acc > 75 and old_mult < 2.0:
                new_mult = round(min(2.0, old_mult + 0.1), 2)
                current_multipliers[stype] = new_mult
                adjustments.append(f"Multiplicador '{stype}': {old_mult}x → {new_mult}x (+0.1 por {acc}%)")
            elif acc < 35 and old_mult > 0.5:
                new_mult = round(max(0.5, old_mult - 0.1), 2)
                current_multipliers[stype] = new_mult
                adjustments.append(f"Multiplicador '{stype}': {old_mult}x → {new_mult}x (-0.1 por {acc}%)")

    # ─────────────────────────────────────────────────────────────
    # GUARDAR Y REGISTRAR HISTÓRICO
    # ─────────────────────────────────────────────────────────────
    now_str = datetime.datetime.now().isoformat()
    weights["updated_at"] = now_str

    if adjustments:
        history_entry = {
            "timestamp": now_str,
            "date": date.isoformat(),
            "adjustments": adjustments
        }
        weights.setdefault("history", []).append(history_entry)
        save_learned_weights(weights)
        log(f"Aprendizaje aplicado: {len(adjustments)} cambios realizados")

        if send_telegram:
            _notify_learning_telegram(adjustments, weights)
    else:
        log("Aprendizaje completado: sin ajustes necesarios hoy (métricas estables o pocos datos evaluados)")

    return {
        "date": date.isoformat(),
        "adjustments_count": len(adjustments),
        "adjustments": adjustments,
        "weights": weights
    }


def _notify_learning_telegram(adjustments: list, weights: dict):
    """Envía un resumen de los ajustes de aprendizaje a Telegram."""
    try:
        from telegram_bot import send_message

        lines = [
            "🧠 *MEME RADAR // APRENDIZAJE AUTÓNOMO*",
            "─" * 36,
            f"*Ajustes aplicados hoy ({len(adjustments)}):*"
        ]
        for adj in adjustments[:8]:
            lines.append(f"• `{adj}`")

        # Resumen de pesos de capas
        layer_w = weights.get("layer_weights", {})
        l_str = " | ".join([f"{k}:{v}" for k, v in layer_w.items()])
        lines.append(f"\n*Pesos de Capas:* `{l_str}`")
        lines.append(f"*Umbral Score:* `{weights.get('threshold_score', 65)}`")
        lines.append("─" * 36)
        lines.append("_El sistema continúa optimizando sus predicciones día a día._")

        msg = "\n".join(lines)
        send_message(msg)
    except Exception as e:
        log(f"Error notificando aprendizaje a Telegram: {e}")


def get_current_weights() -> dict:
    """Función de conveniencia para consultar los pesos activos."""
    return load_learned_weights()


if __name__ == "__main__":
    print("Probando ciclo de aprendizaje autónomo...")
    res = apply_daily_learning(send_telegram=False)
    print(f"\nResultado: {res['adjustments_count']} ajustes aplicados.")
    for a in res["adjustments"]:
        print(f" - {a}")
