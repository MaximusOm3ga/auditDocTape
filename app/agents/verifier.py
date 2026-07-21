import re
from typing import Optional, Dict, Tuple
CONVERSION_RATES = {
    "USD": 1.0,
    "EUR": 1.10,
    "GBP": 1.27,
    "INR": 0.012,
    "JPY": 0.0067,
}


class NumericVerificationError(Exception):
    pass


def parse_number(value_str: str) -> Tuple[float, Optional[str]]:
    """
    Parse a number value, potentially with currency or unit.
    
    Returns: (number, currency_if_found)
    Examples:
        "$1,234.56" -> (1234.56, "USD")
        "1234.56 EUR" -> (1234.56, "EUR")
        "30 days" -> (30, None)
    """
    value_str = str(value_str).strip()
    currency = None
    if "$" in value_str:
        currency = "USD"
        value_str = value_str.replace("$", "")
    elif "€" in value_str:
        currency = "EUR"
        value_str = value_str.replace("€", "")
    elif "£" in value_str:
        currency = "GBP"
        value_str = value_str.replace("£", "")
    else:
        match = re.search(r"(USD|EUR|GBP|JPY|INR|CAD|AUD)", value_str, re.IGNORECASE)
        if match:
            currency = match.group(1).upper()
            value_str = value_str[:match.start()] + value_str[match.end():]
    value_str = value_str.replace(",", "").strip()
    
    try:
        number = float(value_str)
    except ValueError:
        raise NumericVerificationError(f"Cannot parse '{value_str}' as a number")
    
    return number, currency


def convert_currency(amount: float, from_currency: Optional[str], to_currency: Optional[str]) -> float:

    if not from_currency or not to_currency:
        return amount
    
    if from_currency == to_currency:
        return amount
    
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    
    if from_currency not in CONVERSION_RATES:
        raise NumericVerificationError(f"Unknown currency: {from_currency}")
    if to_currency not in CONVERSION_RATES:
        raise NumericVerificationError(f"Unknown currency: {to_currency}")
    in_usd = amount / CONVERSION_RATES[from_currency]
    converted = in_usd * CONVERSION_RATES[to_currency]
    
    return converted


def numeric_conflict_analysis(claim_a: Dict, claim_b: Dict, tolerance_percent: float = 5.0) -> Dict:

    try:
        num_a, curr_a = parse_number(claim_a["value"])
        num_b, curr_b = parse_number(claim_b["value"])
    except NumericVerificationError as e:
        return {
            "error": str(e),
            "is_significant": True
        }
    converted = False
    if curr_a != curr_b and curr_a is not None and curr_b is not None:
        try:
            num_b_converted = convert_currency(num_b, curr_b, curr_a)
            converted = True
            comparison_num_b = num_b_converted
            common_currency = curr_a
        except NumericVerificationError:
            comparison_num_b = num_b
            common_currency = None
    else:
        comparison_num_b = num_b
        common_currency = curr_a or curr_b
    max_val = max(abs(num_a), abs(comparison_num_b), 1)
    percent_diff = abs(num_a - comparison_num_b) / max_val * 100
    
    is_significant = percent_diff > tolerance_percent
    
    explanation = f"Value A: {num_a} {curr_a or ''}, Value B: {num_b} {curr_b or ''}"
    if converted:
        explanation += f" (converted to {common_currency}: {comparison_num_b})"
    explanation += f" — Difference: {percent_diff:.1f}%"
    
    return {
        "value_a": num_a,
        "value_b": num_b,
        "currency_a": curr_a,
        "currency_b": curr_b,
        "converted_to_common_currency": converted,
        "common_currency": common_currency,
        "comparison_value_b": comparison_num_b,
        "percent_difference": round(percent_diff, 2),
        "is_significant": is_significant,
        "explanation": explanation
    }


def verify_invoice_vs_contract(invoice_amount: float, invoice_currency: Optional[str],
                               contract_amount: float, contract_currency: Optional[str],
                               tolerance_percent: float = 2.0) -> Dict:

    try:
        invoice_num = invoice_amount
        contract_num = contract_amount
        if invoice_currency and contract_currency and invoice_currency != contract_currency:
            contract_num = convert_currency(contract_num, contract_currency, invoice_currency)
            common_currency = invoice_currency
        else:
            common_currency = invoice_currency or contract_currency
        max_val = max(abs(invoice_num), abs(contract_num), 1)
        variance_percent = abs(invoice_num - contract_num) / max_val * 100
        
        matches = variance_percent <= tolerance_percent
        
        return {
            "matches": matches,
            "invoice_amount_normalized": invoice_num,
            "contract_amount_normalized": contract_num,
            "common_currency": common_currency,
            "variance_percent": round(variance_percent, 2),
            "explanation": f"Invoice: {invoice_num} {invoice_currency or ''}, "
                          f"Contract: {contract_num} {contract_currency or ''}, "
                          f"Variance: {variance_percent:.2f}%"
        }
    except Exception as e:
        raise NumericVerificationError(f"Failed to verify: {e}")


def reconcile(contract_value: float, invoice_total: float, tolerance_pct: float = 1.0) -> dict:
    diff = abs(contract_value - invoice_total)
    pct = float(diff / max(abs(contract_value), 1) * 100)
    
    return {
        "contract_value": contract_value,
        "invoice_total": invoice_total,
        "difference": float(diff),
        "pct_difference": round(pct, 2),
        "within_tolerance": pct <= tolerance_pct,
    }


