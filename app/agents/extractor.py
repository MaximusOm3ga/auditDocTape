from openai import OpenAI
import json
import os
from .validator import validate_and_repair_claims, get_allowed_predicates
from dotenv import load_dotenv

load_dotenv()

_api_key = os.environ.get("GROQ_API_KEY")
if _api_key:
    client = OpenAI(api_key=_api_key, base_url="https://api.groq.com/openai/v1")
else:
    class _DummyCompletions:
        @staticmethod
        def create(*args, **kwargs):
            raise RuntimeError("GROQ_API_KEY not set. LLM calls are disabled. Set GROQ_API_KEY to enable.")

    class _DummyChat:
        completions = _DummyCompletions()

    class _DummyClient:
        chat = _DummyChat()

    client = _DummyClient()

EXTRACTION_PROMPT = """You extract structured factual claims from a document chunk.

Document type: {doc_type}

Allowed predicates for this document type: {predicates}

For each factual claim in the text, output an object with:

- subject: the specific entity/item the claim is about (e.g. "VendorX", "Q3_2026")

- predicate: MUST be one of the allowed predicates above. Never invent new predicates.

- value: the stated value, as plain text

- value_type: one of "number", "date", "string", "currency"

- unit: unit if applicable (e.g. "USD", "days"), else null

- confidence: your confidence 0.0-1.0 that this is stated explicitly (not inferred)

**CRITICAL: Only extract claims that use an allowed predicate. If nothing matches the allowed predicates, return an empty list.**

**Prefer silence over invention: if uncertain whether a chunk contains a fact matching an allowed predicate, do not extract it.**

Return ONLY a JSON array, no prose, no markdown fences.

Text:

{chunk_text}

"""

def extract_claims(chunk_text: str, doc_type: str) -> list[dict]:
    predicates = get_allowed_predicates(doc_type)

    prompt = EXTRACTION_PROMPT.format(
        doc_type=doc_type, predicates=predicates, chunk_text=chunk_text
    )

    resp = client.chat.completions.create(

        model="openai/gpt-oss-20b",

        messages=[{"role": "user", "content": prompt}],

        temperature=0,

        #max_tokens=1024,

    )

    raw = resp.choices[0].message.content.strip()

    try:

        claims = json.loads(raw)

    except json.JSONDecodeError:
        repair_prompt = f"The following is not valid JSON. Fix it and return ONLY the corrected JSON array:\n{raw}"

        resp2 = client.chat.completions.create(

            model="openai/gpt-oss-20b",

            messages=[{"role": "user", "content": repair_prompt}],

            temperature=0,

            #max_tokens = 1024,

        )

        try:
            claims = json.loads(resp2.choices[0].message.content.strip())
        except json.JSONDecodeError:
            print(f"Failed to repair JSON for chunk. Original: {raw}")
            claims = []
    return validate_and_repair_claims(claims, doc_type)

