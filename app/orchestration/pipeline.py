def process_document(doc_id: str, doc_type: str, entity: str, text: str, db):

    chunks = chunk_text(text)

    chunk_records = []

    for i, ch in enumerate(chunks):

        chunk_id = f"{doc_id}_c{i}"

        db.insert_chunk(chunk_id, doc_id, i, ch)

        chunk_records.append((chunk_id, ch))

    vectors = embed([c[1] for c in chunk_records])

    metadatas = [{"doc_id": doc_id, "entity": entity, "doc_type": doc_type,

                  "superseded": False} for _ in chunk_records]

    chroma_store.add(vectors, [c[0] for c in chunk_records], [c[1] for c in chunk_records], metadatas)

    supersedes_id = db.get_supersedes(doc_id)

    if supersedes_id:

        chroma_store.mark_superseded(supersedes_id)

    all_claims = []

    for chunk_id, ch in chunk_records:

        extracted = extract_claims(ch, doc_type)

        for c in extracted:

            c.update({"doc_id": doc_id, "chunk_id": chunk_id, "entity": entity})

            claim_id = db.insert_claim(c)

            c["claim_id"] = claim_id

            all_claims.append(c)

    existing_claims = db.get_claims_for_entity(entity)

    conflicts = detect_conflicts(existing_claims + all_claims)

    for conf in conflicts:

        if conf["severity"] > 0.4:

            a, b = db.get_claim(conf["claim_id_a"]), db.get_claim(conf["claim_id_b"])

            judged = llm_judge_conflict(a, b, db.get_chunk_text(a["chunk_id"]), db.get_chunk_text(b["chunk_id"]))

            if not judged["is_genuine_conflict"]:

                continue

        explanation = explain_conflict(a, b, db.get_doc_name(a["doc_id"]), db.get_doc_name(b["doc_id"]))

        db.insert_conflict(conf["claim_id_a"], conf["claim_id_b"], conf["severity"], explanation)

    return {"chunks": len(chunks), "claims": len(all_claims), "conflicts": len(conflicts)}
