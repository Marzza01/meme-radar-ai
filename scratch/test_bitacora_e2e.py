"""Test E2E del Sistema de Bitácora + Aprendizaje Autónomo con 5 Capas."""

import sys
import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "bitacora"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "alertas"))

from bitacora.logger import (
    log_alert, set_feedback, get_daily_stats,
    SIGNAL_CONVERGENCE, SIGNAL_DISCOVERY, SIGNAL_COPYTRADE,
    LAYER_X, LAYER_FOMO, LAYER_PUMPFUN, LAYER_DEXSCREENER, LAYER_SEGURIDAD
)
from bitacora.reporter import generate_daily_report
from bitacora.learner import apply_daily_learning, load_learned_weights

print("=== 1. REGISTRANDO ALERTAS CON LAS 5 CAPAS ===")

# Alerta 1: Convergence BONK (X + FOMO + DexScreener + Seguridad)
a1 = log_alert(
    token="BONK",
    signal_type=SIGNAL_CONVERGENCE,
    mint="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    score=82,
    layers=[LAYER_X, LAYER_FOMO, LAYER_DEXSCREENER, LAYER_SEGURIDAD],
    signals=["Smart Money x3", "Volume spike 4.5x", "RugCheck: Good"],
    traders_involved=["@Cupseyy", "@notdecu"],
    metrics={"market_cap": "$1.8M", "liquidity": "$150K"},
    price_at_alert="0.000015"
)
print(f"Alerta 1 creada: {a1}")

# Alerta 2: Discovery PEPE2 (X + DexScreener)
a2 = log_alert(
    token="PEPE2",
    signal_type=SIGNAL_DISCOVERY,
    mint="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
    score=68,
    layers=[LAYER_X, LAYER_DEXSCREENER],
    signals=["Discovery por @theunipcs", "1 mención"],
    traders_involved=["@theunipcs"],
    metrics={"market_cap": "$350K", "liquidity": "$45K"},
    price_at_alert="0.000003"
)
print(f"Alerta 2 creada: {a2}")

# Alerta 3: Copytrade PUMP (Pump.fun + DexScreener)
a3 = log_alert(
    token="DOGE99",
    signal_type=SIGNAL_COPYTRADE,
    mint="6p6xgHyF7AeQHyMunfUWmFVCkg545V45p1mBSpump",
    score=75,
    layers=[LAYER_PUMPFUN, LAYER_DEXSCREENER],
    signals=["Copytrade BUY en Pump.fun", "1.500 SOL por @Cented7"],
    traders_involved=["@Cented7"],
    metrics={"market_cap": "$90K", "liquidity": "$12K"},
    price_at_alert="0.0000008"
)
print(f"Alerta 3 creada: {a3}")

print("\n=== 2. APLICANDO FEEDBACK MANUAL ===")
ok1 = set_feedback(a1, "true_positive", "Subio 3.2x")
ok2 = set_feedback(a2, "true_positive", "Subio 50%")
ok3 = set_feedback(a3, "false_positive", "Dumping rapido")
print(f"Feedback a1: {ok1} | a2: {ok2} | a3: {ok3}")

stats = get_daily_stats()
print(f"\nStats del dia: {stats['total']} alertas | TP: {stats['tp']} | FP: {stats['fp']}")
print(f"Precision por tipo de senal: {stats['by_signal_type']}")
print(f"Precision por capas: {list(stats['by_layer'].keys())}")

print("\n=== 3. GENERANDO INFORME DIARIO (5 CAPAS) ===")
report = generate_daily_report(send_telegram=False)
print("--- INICIO DEL INFORME ---")
print(report[:1200])
print("--- FIN FRAGMENTO INFORME ---")

print("\n=== 4. EJECUTANDO CICLO DE APRENDIZAJE AUTONOMO ===")
learn_res = apply_daily_learning(send_telegram=False)
print(f"Ajustes realizados: {learn_res['adjustments_count']}")
for adj in learn_res["adjustments"]:
    print(f"  • {adj}")

weights = load_learned_weights()
print(f"Pesos de Capas finales: {weights['layer_weights']}")
print(f"Umbral Score final: {weights['threshold_score']}")
print("\nTEST COMPLETADO CON EXITO!")
