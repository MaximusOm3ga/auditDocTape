from openai import OpenAI

import json, os

client = OpenAI(

    api_key=os.environ["GROQ_API_KEY"],

    base_url="https://api.groq.com/openai/v1",

)

ALLOWED_PREDICATES = {

    "contract": ["payment_terms_days", "contract_value", "renewal_date",

                 "termination_notice_days", "liability_cap", "governing_law"],

    "financial_report": ["revenue", "expenses", "net_income", "period"],

    "policy": ["effective_date", "applies_to", "requirement"],

}

EXTRACTION_PROMPT = """You extract structured factual claims from a document chunk.

Document type: {doc_type}

Allowed predicates for this document type: {predicates}

For each factual claim in the text, output an object with:

- subject: the specific entity/item the claim is about (e.g. "VendorX", "Q3_2026")

- predicate: MUST be one of the allowed predicates above

- value: the stated value, as plain text

- value_type: one of "number", "date", "string", "currency"

- unit: unit if applicable (e.g. "USD", "days"), else null

- confidence: your confidence 0.0-1.0 that this is stated explicitly (not inferred)

Only extract claims that use an allowed predicate. If nothing matches, return an empty list.

Return ONLY a JSON array, no prose, no markdown fences.

Text:

{chunk_text}

"""

def extract_claims(chunk_text: str, doc_type: str) -> list[dict]:

    predicates = ALLOWED_PREDICATES.get(doc_type, [])

    prompt = EXTRACTION_PROMPT.format(

        doc_type=doc_type, predicates=predicates, chunk_text=chunk_text

    )

    resp = client.chat.completions.create(

        model="llama-3.1-8b-instant",

        messages=[{"role": "user", "content": prompt}],

        temperature=0,

    )

    raw = resp.choices[0].message.content.strip()

    try:

        claims = json.loads(raw)

    except json.JSONDecodeError:

        repair_prompt = f"The following is not valid JSON. Fix it and return ONLY the corrected JSON array:\n{raw}"

        resp2 = client.chat.completions.create(

            model="llama-3.1-8b-instant",

            messages=[{"role": "user", "content": repair_prompt}],

            temperature=0,

        )

        claims = json.loads(resp2.choices[0].message.content.strip())

    return [c for c in claims if c.get("predicate") in predicates]
