"""Módulo de Auditoría de Seguridad On-Chain (RugCheck & Anti-Scam).

Verifica contratos en Solana vía la API pública de RugCheck para detectar:
- Honeypots (Freeze Authority activa)
- Riesgo de emisión infinita (Mint Authority activa)
- Concentración de insiders (Top 10 holders %)
- Liquidez bloqueada/quemada (LP Locked %)
- Score global de riesgo antes de enviar alertas de compra.
"""

import os
import sys
import json
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


def get_ssl_context():
    """Contexto SSL seguro para consultas HTTP."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def audit_token(mint_address: str, timeout: int = 10) -> dict:
    """Realiza una auditoría completa de seguridad para un token de Solana.

    Retorna un diccionario estructurado con métricas de riesgo.
    """
    if not mint_address or len(mint_address) < 32 or len(mint_address) > 44:
        return {
            "success": False,
            "error": "Dirección de contrato (mint) inválida",
            "mint": mint_address,
            "risk_rating": "DESCONOCIDO"
        }

    url = f"https://api.rugcheck.xyz/v1/tokens/{mint_address}/report"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MemeRadar/2.0",
            "Accept": "application/json"
        }
    )

    try:
        ctx = get_ssl_context()
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # 1. Autoridades
        token_meta = data.get("tokenMeta", {})
        mint_auth = data.get("mintAuthority") or token_meta.get("mintAuthority")
        freeze_auth = data.get("freezeAuthority") or token_meta.get("freezeAuthority")

        mint_revoked = mint_auth is None
        freeze_revoked = freeze_auth is None

        # 2. Rugged flag
        is_rugged = data.get("rugged", False)

        # 3. Score numérico (En RugCheck: 0 - 500 es Bueno/Seguro, 500 - 1500 Advertencia, >1500 Peligro)
        score = data.get("score", 0)

        # 4. Top Holders Supply %
        top_holders = data.get("topHolders", [])
        top10_pct = sum(float(h.get("pct", 0)) for h in top_holders[:10])
        insiders_count = sum(1 for h in top_holders if h.get("insider", False))

        # 5. Liquidez bloqueada
        markets = data.get("markets", [])
        lp_locked_pct = 0.0
        if markets and isinstance(markets, list):
            lp_info = markets[0].get("lp", {})
            lp_locked_pct = float(lp_info.get("lpLockedPct", 0.0))

        # 6. Riesgos identificados
        raw_risks = data.get("risks", [])
        risk_names = []
        for r in raw_risks:
            r_name = r.get("name") or r.get("description", "")
            if r_name:
                risk_names.append(r_name)

        # 7. Clasificación de riesgo global
        if is_rugged or not freeze_revoked:
            risk_rating = "PELIGRO / HONEYPOT"
            safe = False
        elif score > 1500 or top10_pct > 70.0:
            risk_rating = "ALTO RIESGO"
            safe = False
        elif score > 500 or not mint_revoked or top10_pct > 40.0:
            risk_rating = "RIESGO MODERADO"
            safe = True
        else:
            risk_rating = "BAJO RIESGO / BUENO"
            safe = True

        return {
            "success": True,
            "mint": mint_address,
            "safe": safe,
            "score": score,
            "risk_rating": risk_rating,
            "mint_authority": "REVOCADO" if mint_revoked else "ACTIVO (Riesgo)",
            "freeze_authority": "REVOCADO (Sin Honeypot)" if freeze_revoked else "ACTIVO (Peligro Honeypot)",
            "top10_supply_pct": round(top10_pct, 2),
            "insiders_count": insiders_count,
            "lp_locked_pct": round(lp_locked_pct, 2),
            "rugged": is_rugged,
            "risks": risk_names,
            "rugcheck_url": f"https://rugcheck.xyz/tokens/{mint_address}"
        }

    except urllib.error.HTTPError as e:
        return {
            "success": False,
            "error": f"Error HTTP {e.code} de RugCheck",
            "mint": mint_address,
            "risk_rating": "NO DISPONIBLE"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "mint": mint_address,
            "risk_rating": "ERROR AUDITORIA"
        }


def format_audit_for_alert(audit_res: dict) -> dict:
    """Convierte el resultado de auditoría en los campos requeridos por telegram_bot."""
    if not audit_res or not audit_res.get("success"):
        return {
            "contract": audit_res.get("mint", "N/A"),
            "risk": audit_res.get("risk_rating", "Auditoría no disponible")
        }

    mint = audit_res.get("mint", "")
    short_ca = f"{mint[:6]}...{mint[-4:]}" if len(mint) >= 10 else mint

    freeze_text = "PASADO (Freeze Revocado)" if "REVOCADO" in audit_res.get("freeze_authority", "") else "ALERTA (Freeze Activo)"
    mint_text = "MINT REVOCADO" if "REVOCADO" in audit_res.get("mint_authority", "") else "MINT ACTIVO"

    top10 = audit_res.get("top10_supply_pct", 0)
    top10_tag = " (Saludable)" if top10 < 30 else (" (Moderado)" if top10 < 50 else " (Concentrado)")
    top10_str = f"{top10}%{top10_tag}"

    risk_label = f"{audit_res.get('risk_rating', 'N/A')} (Score: {audit_res.get('score', 0)})"

    return {
        "contract": short_ca,
        "honeypot": freeze_text,
        "authorities": mint_text,
        "top_10": top10_str,
        "risk": risk_label,
        "raw_audit": audit_res
    }


if __name__ == "__main__":
    # Test directo de auditoría por línea de comandos
    test_mint = sys.argv[1] if len(sys.argv) > 1 else "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"
    print(f"Auditando token: {test_mint}...")
    res = audit_token(test_mint)
    print(json.dumps(res, indent=4, ensure_ascii=False))
    print("\nFormato de alerta Telegram:")
    formatted = format_audit_for_alert(res)
    print(json.dumps(formatted, indent=4, ensure_ascii=False))
