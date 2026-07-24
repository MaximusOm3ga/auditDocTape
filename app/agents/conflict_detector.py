from .extractor import client
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from ..agents.verifier import numeric_conflict_analysis, NumericVerificationError



def normalize_predicate(pred: str) -> str:
    mapping = {
        "payment_terms": "payment_terms_days",
        "payment_terms_days": "payment_terms_days",
        "invoice_due_period": "payment_terms_days",
        "invoice_due_days": "payment_terms_days",
        "term": "initial_term_months",
        "initial_term": "initial_term_months",
        "contract_term": "initial_term_months",
        "liability": "liability_cap",
        "liability_cap": "liability_cap",
        "liability_limit": "liability_cap",
        "governing_law": "governing_law",
        "jurisdiction": "governing_law",
        "applicable_law": "governing_law",
    }
    return mapping.get(pred.strip().lower(), pred.strip().lower())

def group_claims(claims: list[dict]) -> dict:
    groups = {}
    seen = set()
    for c in claims:
        entity = (c.get("entity") or "").strip().lower()
        subject = (c.get("subject") or "").strip().lower().replace(" ", "_")
        predicate = normalize_predicate(c.get("predicate") or "")
        dedup_key = (c.get("doc_id"), entity, subject, predicate, str(c.get("value")).strip().lower())
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        key = (entity, subject, predicate)
        groups.setdefault(key, []).append(c)
    return groups

def values_conflict(a: dict, b: dict) -> bool:
    if a["value_type"] != b["value_type"]:
        return False
    if a["value_type"] in ("number", "currency"):
        try:
            result = numeric_conflict_analysis(a, b, tolerance_percent=1.0)
        except NumericVerificationError:
            return a["value"] != b["value"]
        return result.get("is_significant", False)
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

# def detect_conflicts(claims: list[dict], supersession_map: Optional[Dict[str, Optional[str]]] = None) -> list[dict]:
#     if supersession_map is None:
#         supersession_map = {}
# 
#     conflicts = []
# 
#     for key, group in group_claims(claims).items():
# 
#         for i in range(len(group)):
# 
#             for j in range(i + 1, len(group)):
# 
#                 a, b = group[i], group[j]
# 
#                 if a["doc_id"] == b["doc_id"]:
# 
#                     continue
# 
#                 if values_conflict(a, b):
# 
#                     conflicts.append({
#                         "claim_id_a": a.get("claim_id"),
#                         "claim_id_b": b.get("claim_id"),
#                         "claim_a": a,
#                         "claim_b": b,
#                         "severity": severity(a, b),
#                     })
#     conflicts = filter_superseded_pairs(conflicts, supersession_map)
#     
#     return conflicts

#DEBUGGER

def detect_conflicts(
    claims: list[dict], supersession_map: Optional[Dict[str, Optional[str]]] = None
) -> list[dict]:
    if supersession_map is None:
        supersession_map = {}

    print(f"\n[DEBUG] detect_conflicts called with {len(claims)} total claims")
    groups = group_claims(claims)
    print(f"[DEBUG] Grouped into {len(groups)} groups")
    for key, group in groups.items():
        print(
            f"[DEBUG]  Group {key}: {len(group)} claims from docs: {[c['doc_id'][:8] for c in group]}"
        )

    conflicts = []
    for key, group in groups.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a["doc_id"] == b["doc_id"]:
                    continue
                print(
                    f"[DEBUG]  CROSS-DOC COMPARE: {a['predicate']} | A='{a['value']}' vs B='{b['value']}' (types: {a['value_type']}/{b['value_type']})"
                )
                vc = values_conflict(a, b)
                print(f"[DEBUG]   values_conflict={vc}, severity={severity(a, b)}")
                if vc:
                    conflicts.append(
                        {
                            "claim_id_a": a.get("claim_id"),
                            "claim_id_b": b.get("claim_id"),
                            "claim_a": a,
                            "claim_b": b,
                            "severity": severity(a, b),
                        }
                    )

    print(f"[DEBUG] Raw conflicts before filter: {len(conflicts)}")
    conflicts = filter_superseded_pairs(conflicts, supersession_map)
    print(f"[DEBUG] After supersession filter: {len(conflicts)}")
    return conflicts

def llm_judge_conflict(a: dict, b: dict, chunk_a_text: str, chunk_b_text: str) -> dict:

    prompt = f"""You are a contract compliance auditor reviewing documents for the same business entity.
            
            Two documents for the same entity contain different values for the same contractual term.
            Your job is to determine whether this difference is MATERIAL and should be flagged for human review.
            
            A difference is MATERIAL if:
            - The same entity is bound by contradictory obligations (e.g., different payment amounts, different termination periods, different governing laws)
            - One document imposes stricter or different terms than the other without clear justification
            - A reasonable person would need to know about this discrepancy to manage legal or business risk
            
            A difference is NOT material ONLY if:
            - The claims are about completely unrelated topics or different subsidiaries
            - One document explicitly states it supersedes or amends the other
            
            Document A ({a.get("doc_type", "unknown")} dated {a.get("effective_date", "unknown")}):
            Subject: {a["subject"]}
            Term: {a["predicate"]}
            Value: {a["value"]} {a.get("unit", "")}
            Context: {chunk_a_text[:500]}
            
            Document B ({b.get("doc_type", "unknown")} dated {b.get("effective_date", "unknown")}):
            Subject: {b["subject"]}
            Term: {b["predicate"]}
            Value: {b["value"]} {b.get("unit", "")}
            Context: {chunk_b_text[:500]}
            
            Respond with ONLY this JSON format, no other text:
            {{"is_material_discrepancy": true/false, "reasoning": "one sentence explaining why"}}
            """

    resp = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens = 2048,
        reasoning_effort = "low",
    )

    try:
        result = json.loads(resp.choices[0].message.content.strip())
    except json.JSONDecodeError:
        result = {
            "is_material_discrepancy": True,
            "reasoning": "Failed to parse LLM response",
        }

    return result
