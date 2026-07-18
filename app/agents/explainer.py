def explain_conflict(a: dict, b: dict, doc_a_name: str, doc_b_name: str) -> str:

    prompt = f"""Write a 2-3 sentence explanation of this conflict for a human reviewer.

Be specific and cite both documents by name. Do not editorialize about which is correct.

{doc_a_name} states {a['subject']} {a['predicate']} = {a['value']} {a.get('unit') or ''} (dated {a['claim_date']}).

{doc_b_name} states {b['subject']} {b['predicate']} = {b['value']} {b.get('unit') or ''} (dated {b['claim_date']}).

"""

    resp = client.chat.completions.create(

        model="llama-3.1-8b-instant",

        messages=[{"role": "user", "content": prompt}],

        temperature=0.3,

    )

    return resp.choices[0].message.content.strip()
