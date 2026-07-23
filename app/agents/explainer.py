from openai import OpenAI
import json
import os

api_key = os.environ.get("GROQ_API_KEY")

if api_key:
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )
else:
    client = None

def explain_conflict(claim_a: dict, claim_b: dict, doc_a_info: dict, doc_b_info: dict,
                    chunk_a_text: str, chunk_b_text: str) -> dict:
    prompt = f"""You are analyzing a document conflict for a human reviewer.

Two documents contain claims that appear to conflict:

Document A: {doc_a_info.get('filename', 'Unknown')} (effective {doc_a_info.get('effective_date', 'unknown')})
Claim: {claim_a['subject']} - {claim_a['predicate']}: {claim_a['value']} {claim_a.get('unit', '')}
Context: {chunk_a_text[:800]}

Document B: {doc_b_info.get('filename', 'Unknown')} (effective {doc_b_info.get('effective_date', 'unknown')})
Claim: {claim_b['subject']} - {claim_b['predicate']}: {claim_b['value']} {claim_b.get('unit', '')}
Context: {chunk_b_text[:800]}

Write an explanation covering:
1. What each document states
2. Possible reasons for the difference (different time periods, currencies, scopes, line items, etc)
3. What should be verified

Do NOT claim which is correct - that is for the human to decide.

Return ONLY valid JSON with this structure:
{{
    "summary": "One sentence stating what differs",
    "explanation": "2-3 sentence explanation of the discrepancy and possible causes",
    "possible_reasons": ["reason 1", "reason 2", ...],
    "guidance": "What should be verified or checked"
}}
"""

    if not client:
        return {
            "summary": f"{claim_a.get('value', 'Value A')} vs {claim_b.get('value', 'Value B')}",
            "explanation": "API client not configured - manual review recommended",
            "possible_reasons": ["API key not configured"],
            "guidance": "Configure GROQ_API_KEY environment variable for automatic analysis"
        }

    resp = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    try:
        analysis = json.loads(resp.choices[0].message.content.strip())
    except json.JSONDecodeError:
        analysis = {
            "summary": f"{claim_a['value']} vs {claim_b['value']}",
            "explanation": "Failed to generate explanation",
            "possible_reasons": [],
            "guidance": "Manual review recommended"
        }
    return {
        "summary": analysis.get("summary", ""),
        "claim_a": {
            "document": doc_a_info.get("filename", "Unknown"),
            "effective_date": doc_a_info.get("effective_date", "unknown"),
            "entity": claim_a.get("entity"),
            "subject": claim_a.get("subject"),
            "predicate": claim_a.get("predicate"),
            "value": claim_a.get("value"),
            "unit": claim_a.get("unit"),
            "confidence": claim_a.get("confidence", 0),
            "source_context": chunk_a_text[:500]
        },
        "claim_b": {
            "document": doc_b_info.get("filename", "Unknown"),
            "effective_date": doc_b_info.get("effective_date", "unknown"),
            "entity": claim_b.get("entity"),
            "subject": claim_b.get("subject"),
            "predicate": claim_b.get("predicate"),
            "value": claim_b.get("value"),
            "unit": claim_b.get("unit"),
            "confidence": claim_b.get("confidence", 0),
            "source_context": chunk_b_text[:500]
        },
        "analysis": analysis,
        "traces": {
            "claim_a_chunk_id": claim_a.get("chunk_id"),
            "claim_b_chunk_id": claim_b.get("chunk_id"),
            "claim_a_doc_id": claim_a.get("doc_id"),
            "claim_b_doc_id": claim_b.get("doc_id")
        }
    }


def format_explanation_for_api(explanation: dict) -> dict:
    return {
        "summary": explanation["summary"],
        "claim_a": explanation["claim_a"],
        "claim_b": explanation["claim_b"],
        "analysis": explanation["analysis"],
        "traces": explanation["traces"]
    }


