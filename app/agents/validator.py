
from typing import Dict, List, Optional
ALLOWED_PREDICATES = {
    "contract": [
        "payment_terms_days",
        "contract_value",
        "renewal_date",
        "termination_notice_days",
        "liability_cap",
        "governing_law"
    ],
    "financial_report": [
        "revenue",
        "expenses",
        "net_income",
        "reporting_period",
        "fiscal_year"
    ],
    "policy": [
        "effective_date",
        "applies_to",
        "requirement",
        "penalty",
        "review_frequency"
    ],
}

ALLOWED_VALUE_TYPES = ["number", "date", "string", "currency"]


class ValidationError(Exception):
    pass


def validate_claim(claim: Dict, doc_type: str) -> bool:
    
    if doc_type not in ALLOWED_PREDICATES:
        raise ValidationError(f"Unknown document type: {doc_type}")
    
    allowed_predicates = ALLOWED_PREDICATES[doc_type]
    required_fields = ["subject", "predicate", "value", "value_type"]
    for field in required_fields:
        if field not in claim or claim[field] is None:
            raise ValidationError(f"Missing required field: {field}")
    if claim["predicate"] not in allowed_predicates:
        raise ValidationError(
            f"Invalid predicate '{claim['predicate']}' for {doc_type}. "
            f"Allowed: {allowed_predicates}"
        )
    if claim["value_type"] not in ALLOWED_VALUE_TYPES:
        raise ValidationError(
            f"Invalid value_type '{claim['value_type']}'. "
            f"Allowed: {ALLOWED_VALUE_TYPES}"
        )
    confidence = claim.get("confidence", 0.8)
    if not (0.0 <= confidence <= 1.0):
        raise ValidationError(f"Confidence must be between 0 and 1, got {confidence}")
    if not claim["subject"].strip():
        raise ValidationError("Subject cannot be empty")
    if not str(claim["value"]).strip():
        raise ValidationError("Value cannot be empty")
    if claim["value_type"] == "number":
        try:
            float(str(claim["value"]).replace(",", ""))
        except ValueError:
            raise ValidationError(
                f"Value '{claim['value']}' cannot be parsed as a number"
            )
    
    elif claim["value_type"] == "currency":
        value_clean = str(claim["value"]).replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip()
        try:
            float(value_clean)
        except ValueError:
            raise ValidationError(
                f"Currency value '{claim['value']}' cannot be parsed as a number"
            )
    
    elif claim["value_type"] == "date":
        import re
        date_pattern = r"^\d{4}-\d{2}-\d{2}$|^\d{1,2}/\d{1,2}/\d{2,4}$"
        if not re.match(date_pattern, str(claim["value"])):
            raise ValidationError(
                f"Date value '{claim['value']}' is not in expected format (YYYY-MM-DD or MM/DD/YYYY)"
            )
    
    return True


def validate_and_repair_claims(claims: List[Dict], doc_type: str) -> List[Dict]:

    valid_claims = []
    
    for claim in claims:
        try:
            validate_claim(claim, doc_type)
            valid_claims.append(claim)
        except ValidationError as e:
            print(f"Dropped invalid claim: {e}")
            continue
    
    return valid_claims


def get_allowed_predicates(doc_type: str) -> List[str]:
    return ALLOWED_PREDICATES.get(doc_type, [])


def is_valid_predicate(predicate: str, doc_type: str) -> bool:
    return predicate in ALLOWED_PREDICATES.get(doc_type, [])

