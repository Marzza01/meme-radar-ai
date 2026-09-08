"""Bitácora — Reporter diario de Meme Radar AI (v2.2).

Genera un informe completo al final del día con:
- Resumen de alertas (TP/FP/Partial/Pending)
- Precisión por Tipo de Señal (convergence, discovery, copytrade)
- Precisión por Capa de Análisis (las 5 capas: X, FOMO, Pump.fun, DexScreener, Seguridad)
- Mejor y peor alerta del día (PnL, score, traders)
- Ranking de traders por precisión
- Señales más y menos efectivas
- PnL promedio y máximo

El informe se guarda como Markdown en config/reports/ y se envía a Telegram.
Se ejecuta automáticamente a las 23:50 vía el loop del convergence_engine.
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
REPORTS_DIR = PROJECT_ROOT / "config" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(PROJECT_ROOT / "src" / "alertas"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "bitacora"))


def log(msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[REPORTER][{ts}] {msg}")


def _accuracy_pct(tp: int, fp: int, partial: int) -> float:
    evaluated = tp + fp + partial
    if evaluated == 0:
        return 0.0
    return round((tp + 0.5 * partial) / evaluated * 100, 1)


def generate_daily_report(date: datetime.date = None, send_telegram: bool = True) -> str:
    """
    Genera el informe diario de la bitácora con análisis por 5 capas y por tipo de señal.

    Args:
        date: Fecha del informe. None = hoy.
        send_telegram: Si True, envía el informe a Telegram.

    Returns:
        str: Contenido del informe en Markdown.
    """
    from logger import get_daily_stats, load_daily_log

    if date is None:
        date = datetime.date.today()

    stats = get_daily_stats(date)
    entries = load_daily_log(date)
    date_str = date.strftime("%Y-%m-%d")
    weekday = date.strftime("%A")

    # ─── Cabecera
    lines = [
        f"# MEME RADAR // DAILY REPORT — {date_str} ({weekday})",
        "=" * 56,
        ""
    ]

    if stats["total"] == 0:
        lines.append("_Sin alertas registradas hoy._")
        report_text = "\n".join(lines)
        _save_report(date, report_text)
        return report_text

    # ─── Resumen General
    acc = _accuracy_pct(stats["tp"], stats["fp"], stats["partial"])
    pnl_avg = ""
    pnl_max = ""
    if stats["pnl_list"]:
        avg = sum(stats["pnl_list"]) / len(stats["pnl_list"])
        mx = max(stats["pnl_list"])
        pnl_avg = f"{avg:+.1f}%"
        pnl_max = f"{mx:+.1f}%"

    lines += [
        "## RESUMEN DEL DÍA",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Alertas totales   | **{stats['total']}** |",
        f"| Verdaderos (TP)   | ✅ {stats['tp']} |",
        f"| Falsos (FP)       | ❌ {stats['fp']} |",
        f"| Parciales         | ⚠️ {stats['partial']} |",
        f"| Sin evaluar       | ⏳ {stats['pending']} |",
        f"| **Precisión Global** | **{acc}%** |",
    ]

    if pnl_avg:
        lines += [
            f"| PnL Promedio      | {pnl_avg} |",
            f"| PnL Máximo        | {pnl_max} |",
        ]

    lines.append("")

    # ─── Precisión por Tipo de Señal (NUEVO)
    by_stype = stats.get("by_signal_type", {})
    if by_stype:
        lines += ["## PRECISIÓN POR TIPO DE SEÑAL", ""]
        for stype, sdata in sorted(by_stype.items(), key=lambda x: x[1]["total"], reverse=True):
            st_acc = _accuracy_pct(sdata["tp"], sdata["fp"], sdata["partial"])
            ev = sdata["tp"] + sdata["fp"] + sdata["partial"]
            icon = "🟢" if st_acc >= 70 else ("🟡" if st_acc >= 40 else "🔴")
            if ev == 0:
                icon = "⏳"
                lines.append(f"{icon} **{stype}** → {sdata['total']} alertas (pendientes de evaluación)")
            else:
                lines.append(f"{icon} **{stype}** → {sdata['tp']}/{ev} aciertos (**{st_acc}%**) | total: {sdata['total']}")
        lines.append("")

    # ─── Precisión por Capa de Análisis (5 CAPAS) (NUEVO)
    by_layer = stats.get("by_layer", {})
    if by_layer:
        lines += ["## PRECISIÓN POR CAPA DE ANÁLISIS (5 CAPAS)", ""]
        layer_rows = []
        for lname, ldata in by_layer.items():
            l_acc = _accuracy_pct(ldata["tp"], ldata["fp"], ldata["partial"])
            ev = ldata["tp"] + ldata["fp"] + ldata["partial"]
            layer_rows.append((lname, ldata, l_acc, ev))

        # Ordenar por precisión descendente
        layer_rows.sort(key=lambda x: x[2], reverse=True)

        for i, (lname, ldata, l_acc, ev) in enumerate(layer_rows, 1):
            badge = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f"{i}."))
            if ev == 0:
                lines.append(f"{badge} **Capa {lname}** — {ldata['total']} alertas (sin evaluar)")
            else:
                l_icon = "✅" if l_acc >= 70 else ("⚠️" if l_acc >= 40 else "❌")
                lines.append(
                    f"{badge} {l_icon} **Capa {lname}** — **{l_acc}%** | "
                    f"✅{ldata['tp']} ❌{ldata['fp']} ⚠️{ldata['partial']} ({ev} evaluadas)"
                )
        lines.append("")

    # ─── Mejor y Peor Alerta
    if stats.get("best_alert"):
        best = stats["best_alert"]
        pnl_b = f"{best.get('pnl_pct', 0):+.1f}%" if best.get("pnl_pct") is not None else "N/A"
        traders_b = ", ".join(best.get("traders_involved", [])[:3])
        layers_b = ", ".join(best.get("layers", []))
        lines += [
            "## MEJOR ALERTA",
            "",
            f"**${best.get('token','?')}** — Score: {best.get('score','?')} | PnL: {pnl_b}",
            f"Tipo: `{best.get('signal_type', best.get('type','?'))}` | Capas: `{layers_b or 'N/A'}`",
            f"Traders: {traders_b or 'N/A'}",
            f"Señales: {' | '.join(best.get('signals',[])[:3])}",
            f"ID: `{best.get('id','?')}`",
            ""
        ]

    if stats.get("worst_alert") and stats["worst_alert"] != stats.get("best_alert"):
        worst = stats["worst_alert"]
        pnl_w = f"{worst.get('pnl_pct', 0):+.1f}%" if worst.get("pnl_pct") is not None else "N/A"
        layers_w = ", ".join(worst.get("layers", []))
        lines += [
            "## PEOR ALERTA",
            "",
            f"**${worst.get('token','?')}** — Score: {worst.get('score','?')} | PnL: {pnl_w}",
            f"Tipo: `{worst.get('signal_type', worst.get('type','?'))}` | Capas: `{layers_w or 'N/A'}`",
            f"Señales: {' | '.join(worst.get('signals',[])[:3])}",
            f"ID: `{worst.get('id','?')}`",
            ""
        ]

    # ─── Ranking de Traders
    trader_stats = stats.get("by_trader", {})
    if trader_stats:
        ranked_traders = []
        for handle, ts in trader_stats.items():
            acc_t = _accuracy_pct(ts["tp"], ts["fp"], ts["partial"])
            ranked_traders.append((handle, ts, acc_t))
        ranked_traders.sort(key=lambda x: x[2], reverse=True)

        lines += ["## TRADERS — Ranking del Día", ""]
        for i, (handle, ts, acc_t) in enumerate(ranked_traders[:8], 1):
            ev = ts["tp"] + ts["fp"] + ts["partial"]
            icon = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f"{i}."))
            lines.append(
                f"{icon} **@{handle}** — {acc_t}% | "
                f"✅{ts['tp']} ❌{ts['fp']} ⚠️{ts['partial']} ({ev} evaluadas)"
            )
        lines.append("")

    # ─── Señales Efectivas vs Fallidas
    signal_stats = stats.get("by_signal", {})
    if signal_stats:
        qualified = [(s, sd) for s, sd in signal_stats.items() if sd["total"] >= 2]
        if qualified:
            qualified.sort(key=lambda x: _accuracy_pct(x[1]["tp"], x[1]["fp"], x[1]["partial"]), reverse=True)
            lines += ["## SEÑALES — Efectividad", ""]
            for sig, sd in qualified[:6]:
                acc_s = _accuracy_pct(sd["tp"], sd["fp"], sd["partial"])
                icon = "✅" if acc_s >= 60 else ("⚠️" if acc_s >= 40 else "❌")
                lines.append(f"{icon} `{sig}` — {acc_s}% ({sd['total']} ocurrencias)")
            lines.append("")

    # ─── Historial de Alertas del Día
    lines += ["## REGISTRO DE ALERTAS", ""]
    for entry in sorted(entries, key=lambda x: x.get("timestamp", ""), reverse=True):
        ts_short = entry.get("timestamp", "")[:16]
        token = entry.get("token", "?")
        score = entry.get("score", "?")
        outcome = entry.get("outcome", "?")
        stype = entry.get("signal_type", entry.get("type", "cnv"))
        layers_tag = "+".join(entry.get("layers", [])) or "all"
        pnl = entry.get("pnl_pct")
        pnl_str = f" | {pnl:+.1f}%" if pnl is not None else ""
        outcome_icon = {"true_positive": "✅", "false_positive": "❌", "partial": "⚠️"}.get(outcome, "⏳")
        lines.append(
            f"- {outcome_icon} `{ts_short}` **${token}** (score:{score}, {stype}, [{layers_tag}]){pnl_str} | ID: `{entry.get('id','?')}`"
        )

    lines += ["", "---", f"_Generado automáticamente por Meme Radar AI — {datetime.datetime.now().strftime('%H:%M')}_"]

    report_text = "\n".join(lines)

    # Guardar como Markdown
    _save_report(date, report_text)

    # Enviar a Telegram
    if send_telegram:
        _send_report_telegram(date, stats, report_text)

    return report_text


def _save_report(date: datetime.date, content: str):
    """Guarda el informe en config/reports/."""
    path = REPORTS_DIR / f"{date.isoformat()}_report.md"
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        log(f"Informe guardado: {path}")
    except Exception as e:
        log(f"Error guardando informe: {e}")


def _send_report_telegram(date: datetime.date, stats: dict, full_report: str):
    """Envía un resumen ejecutivo del informe a Telegram."""
    try:
        from telegram_bot import send_message

        acc = _accuracy_pct(stats["tp"], stats["fp"], stats["partial"])
        pnl_str = ""
        if stats.get("pnl_list"):
            avg = sum(stats["pnl_list"]) / len(stats["pnl_list"])
            mx = max(stats["pnl_list"])
            pnl_str = f"\n*PnL Promedio:* `{avg:+.1f}%` | Máximo: `{mx:+.1f}%`"

        best_token = ""
        if stats.get("best_alert"):
            b = stats["best_alert"]
            pnl_b = f"{b.get('pnl_pct', 0):+.1f}%" if b.get("pnl_pct") is not None else "?"
            best_token = f"\n*Mejor:* `${b.get('token','?')}` → `{pnl_b}`"

        # Resumen de señales y capas
        signals_summary = ""
        by_stype = stats.get("by_signal_type", {})
        if by_stype:
            s_lines = []
            for st, sd in by_stype.items():
                ev = sd["tp"] + sd["fp"] + sd["partial"]
                if ev > 0:
                    s_acc = _accuracy_pct(sd["tp"], sd["fp"], sd["partial"])
                    s_lines.append(f"• `{st}`: {s_acc}% ({sd['tp']}/{ev})")
            if s_lines:
                signals_summary = "\n*Por Señal:*\n" + "\n".join(s_lines)

        msg = (
            f"*MEME RADAR // INFORME DIARIO*\n"
            f"\u2500" * 36 + "\n"
            f"*Fecha:*     `{date.isoformat()}`\n"
            f"*Alertas:*   `{stats['total']}` totales\n"
            f"*Precisión:* `{acc}%` "
            f"(✅{stats['tp']} ❌{stats['fp']} ⚠️{stats['partial']} ⏳{stats['pending']})"
            f"{pnl_str}{best_token}{signals_summary}\n"
            f"\u2500" * 36 + "\n"
            f"_Informe detallado con 5 capas guardado en config/reports/{date.isoformat()}\\_report.md_"
        )

        sent = send_message(msg)
        if sent:
            log("Informe enviado a Telegram")
        else:
            log("Error enviando informe a Telegram")
    except Exception as e:
        log(f"Error en envío Telegram del informe: {e}")


def get_last_n_days_stats(n: int = 7) -> dict:
    """Devuelve estadísticas acumuladas de los últimos N días."""
    from logger import get_daily_stats

    totals = {"total": 0, "tp": 0, "fp": 0, "partial": 0, "pending": 0, "days": 0, "pnl_list": []}
    for i in range(n):
        date = datetime.date.today() - datetime.timedelta(days=i)
        day_stats = get_daily_stats(date)
        if day_stats["total"] > 0:
            totals["days"] += 1
            totals["total"] += day_stats["total"]
            totals["tp"] += day_stats["tp"]
            totals["fp"] += day_stats["fp"]
            totals["partial"] += day_stats["partial"]
            totals["pending"] += day_stats["pending"]
            totals["pnl_list"].extend(day_stats.get("pnl_list", []))

    totals["accuracy"] = _accuracy_pct(totals["tp"], totals["fp"], totals["partial"])
    return totals


if __name__ == "__main__":
    print("Generando informe del día con análisis de 5 capas...")
    report = generate_daily_report(send_telegram=False)
    print("\n" + report)
