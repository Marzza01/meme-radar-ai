"""Sistema de Bitácora y Aprendizaje Autónomo de Meme Radar AI.

Módulos:
- logger: Registro de alertas con 5 capas y precio 24h
- reporter: Generación y envío del informe diario EOD
- learner: Calibración autónoma de pesos de capas, traders y umbrales
"""

from .logger import (
    log_alert,
    set_feedback,
    run_price_updater,
    get_daily_stats,
    get_recent_alerts,
    get_multi_day_entries,
    SIGNAL_CONVERGENCE,
    SIGNAL_DISCOVERY,
    SIGNAL_COPYTRADE,
    LAYER_X,
    LAYER_FOMO,
    LAYER_PUMPFUN,
    LAYER_DEXSCREENER,
    LAYER_SEGURIDAD,
    OUTCOME_TP,
    OUTCOME_FP,
    OUTCOME_PARTIAL
)

from .reporter import (
    generate_daily_report,
    get_last_n_days_stats
)

from .learner import (
    apply_daily_learning,
    load_learned_weights,
    get_current_weights
)

__all__ = [
    "log_alert",
    "set_feedback",
    "run_price_updater",
    "get_daily_stats",
    "get_recent_alerts",
    "get_multi_day_entries",
    "generate_daily_report",
    "get_last_n_days_stats",
    "apply_daily_learning",
    "load_learned_weights",
    "get_current_weights",
    "SIGNAL_CONVERGENCE",
    "SIGNAL_DISCOVERY",
    "SIGNAL_COPYTRADE",
    "LAYER_X",
    "LAYER_FOMO",
    "LAYER_PUMPFUN",
    "LAYER_DEXSCREENER",
    "LAYER_SEGURIDAD",
    "OUTCOME_TP",
    "OUTCOME_FP",
    "OUTCOME_PARTIAL"
]
