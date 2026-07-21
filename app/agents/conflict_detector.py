from .extractor import client
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

def group_claims(claims: list[dict]) -> dict:

    groups = {}

    for c in claims:

        key = (c["entity"], c["subject"], c["predicate"])

        groups.setdefault(key, []).append(c)

    return groups

def values_conflict(a: dict, b: dict) -> bool:

    if a["value_type"] != b["value_type"]:

        return False

    if a["value_type"] == "number" or a["value_type"] == "currency":

        try:

            va, vb = float(a["value"].replace(",", "")), float(b["value"].replace(",", ""))

        except ValueError:

            return a["value"] != b["value"]
        return abs(va - vb) / max(abs(va), abs(vb), 1) > 0.01

    return a["value"].strip().lower() != b["value"].strip().lower()

def severity(a: dict, b: dict) -> float:

    base = 0.5

    if a["value_type"] in ("number", "currency"):

        try:

            va, vb = float(a["value"].replace(",", "")), float(b["value"].replace(",", ""))

            pct_diff = abs(va - vb) / max(abs(va), abs(vb), 1)

            base = min(1.0, pct_diff * 1.0)

        except ValueError:

            pass

    HIGH_STAKES = {"contract_value", "liability_cap", "termination_notice_days"}

    if a["predicate"] in HIGH_STAKES:

        base = min(1.0, base + 0.3)
    if "effective_date" in a and "effective_date" in b:
        try:
            date_a = datetime.fromisoformat(a["effective_date"])
            date_b = datetime.fromisoformat(b["effective_date"])
            time_diff = abs((date_b - date_a).days)
            if time_diff > 180:
                base = base * 0.7
        except (ValueError, TypeError):
            pass

    return round(base, 2)

def filter_superseded_pairs(conflicts: List[Dict], supersession_map: Dict[str, Optional[str]]) -> List[Dict]:
    filtered = []
    
    for conf in conflicts:
        claim_a = conf.get("claim_a")
        claim_b = conf.get("claim_b")
        
        if not claim_a or not claim_b:
            filtered.append(conf)
            continue
        
        doc_id_a = claim_a["doc_id"]
        doc_id_b = claim_b["doc_id"]
        if supersession_map.get(doc_id_a) == doc_id_b or supersession_map.get(doc_id_b) == doc_id_a:
            continue
        
        filtered.append(conf)
    
    return filtered

def detect_conflicts(claims: list[dict], supersession_map: Optional[Dict[str, Optional[str]]] = None) -> list[dict]:
    if supersession_map is None:
        supersession_map = {}

    conflicts = []

    for key, group in group_claims(claims).items():

        for i in range(len(group)):

            for j in range(i + 1, len(group)):

                a, b = group[i], group[j]

                if a["doc_id"] == b["doc_id"]:

                    continue

                if values_conflict(a, b):

                    conflicts.append({
                        "claim_id_a": a.get("claim_id"),
                        "claim_id_b": b.get("claim_id"),
                        "claim_a": a,
                        "claim_b": b,
                        "severity": severity(a, b),
                    })
    conflicts = filter_superseded_pairs(conflicts, supersession_map)
    
    return conflicts

def llm_judge_conflict(a: dict, b: dict, chunk_a_text: str, chunk_b_text: str) -> dict:

    prompt = f"""Two claims appear to conflict. Determine if this is a genuine contradiction
    or if it's explainable by different scope (different time period, region, currency, contract line item, etc).
    
    Claim A (from document dated {a.get('effective_date', 'unknown')}): 
    Subject: {a['subject']}
    Predicate: {a['predicate']}
    Value: {a['value']} {a.get('unit', '')}
    Context: {chunk_a_text[:500]}
    
    Claim B (from document dated {b.get('effective_date', 'unknown')}): 
    Subject: {b['subject']}
    Predicate: {b['predicate']}
    Value: {b['value']} {b.get('unit', '')}
    Context: {chunk_b_text[:500]}
    
    Respond with ONLY this JSON format, no other text:
    {{"is_genuine_conflict": true/false, "reasoning": "one sentence explaining why"}}
    """

    resp = client.chat.completions.create(

        model="llama-3.1-8b-instant",

        messages=[{"role": "user", "content": prompt}],

        temperature=0,

    )

    try:
        result = json.loads(resp.choices[0].message.content.strip())
    except json.JSONDecodeError:
        result = {"is_genuine_conflict": True, "reasoning": "Failed to parse LLM response"}
    
    return result

