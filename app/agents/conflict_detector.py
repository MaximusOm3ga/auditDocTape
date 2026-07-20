from extractor import client
import json

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

            base = min(1.0, pct_diff * 2)  # >50% diff saturates severity

        except ValueError:

            pass

    HIGH_STAKES = {"contract_value", "liability_cap", "termination_notice_days"}

    if a["predicate"] in HIGH_STAKES:

        base = min(1.0, base + 0.3)

    return round(base, 2)

def detect_conflicts(claims: list[dict]) -> list[dict]:

    conflicts = []

    for key, group in group_claims(claims).items():


        for i in range(len(group)):

            for j in range(i + 1, len(group)):

                a, b = group[i], group[j]

                if a["doc_id"] == b["doc_id"]:

                    continue

                if values_conflict(a, b):

                    conflicts.append({

                        "claim_id_a": a["claim_id"], "claim_id_b": b["claim_id"],

                        "severity": severity(a, b),

                    })

    return conflicts
def llm_judge_conflict(a: dict, b: dict, chunk_a_text: str, chunk_b_text: str) -> dict:

    prompt = f"""Two claims appear to conflict. Determine if this is a genuine contradiction
    or if it's explainable by different scope (different time period, region, currency, contract line item).
    Claim A (from document dated {a['claim_date']}): {a['subject']} {a['predicate']} = {a['value']}
    Context: {chunk_a_text}
    Claim B (from document dated {b['claim_date']}): {b['subject']} {b['predicate']} = {b['value']}
    Context: {chunk_b_text}
    Return JSON: {{"is_genuine_conflict": bool, "reasoning": "one sentence"}}
    """

    resp = client.chat.completions.create(

        model="llama-3.1-8b-instant",

        messages=[{"role": "user", "content": prompt}],

        temperature=0,

    )

    return json.loads(resp.choices[0].message.content.strip())
