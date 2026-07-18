import sympy as sp

def reconcile(contract_value: float, invoice_total: float, tolerance_pct: float = 1.0) -> dict:

    diff = sp.Abs(sp.Float(contract_value) - sp.Float(invoice_total))

    pct = float(diff / max(abs(contract_value), 1) * 100)

    return {

        "contract_value": contract_value,

        "invoice_total": invoice_total,

        "difference": float(diff),

        "pct_difference": round(pct, 2),

        "within_tolerance": pct <= tolerance_pct,

    }
