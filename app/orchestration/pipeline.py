from ..database_pg import *
from ..ingestion.parsers import parse_document
from ..ingestion.chunker import chunk_text
from ..embeddings.embedder import embed
from ..embeddings.chroma_store import ChromaStore
from ..agents.extractor import extract_claims
from ..agents.conflict_detector import detect_conflicts, llm_judge_conflict, filter_superseded_pairs
from ..agents.explainer import explain_conflict
from typing import Optional, Dict, List
import json
from datetime import date,datetime

chroma_store = ChromaStore()
def _json_safe(obj):
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj

def process_document(doc_id: str, doc_type: str, entity: str, text: str) -> Dict:
    chunks = chunk_text(text)
    chunk_records = []
    for i, ch in enumerate(chunks):
        chunk_id = insert_chunk(doc_id, i, ch)
        chunk_records.append((chunk_id, ch))
    vectors = embed([c[1] for c in chunk_records])
    metadatas = [{
        "doc_id": doc_id,
        "entity": entity,
        "doc_type": doc_type,
        "superseded": False
    } for _ in chunk_records]
    
    chroma_store.add(vectors, [c[0] for c in chunk_records], [c[1] for c in chunk_records], metadatas)
    supersedes_id = get_supersedes(doc_id)
    if supersedes_id:
        chroma_store.mark_superseded(supersedes_id)
    all_claims = []
    for chunk_id, ch in chunk_records:
        extracted = extract_claims(ch, doc_type)
        for claim in extracted:
            claim.update({
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "entity": entity
            })
            claim_id = insert_claim(claim)
            claim["claim_id"] = claim_id
            all_claims.append(claim)
    existing_claims = get_claims_for_entity(entity)
    combined_claims = existing_claims + all_claims
    supersession_map = {}
    for claim in combined_claims:
        doc = get_document(claim["doc_id"])
        if doc and doc["supersedes_id"]:
            supersession_map[doc["doc_id"]] = doc["supersedes_id"]

    conflicts = detect_conflicts(combined_claims, supersession_map)
    judged_conflicts = []
    for conf in conflicts:
        print(
            f"[DEBUG] Judging conflict: {conf['claim_a']['predicate']} vs {conf['claim_b']['predicate']}, severity={conf['severity']}"
        )
        if conf["severity"] > 0.4:
            claim_a = conf["claim_a"]
            claim_b = conf["claim_b"]
            chunk_a_text = get_chunk_text(claim_a["chunk_id"])
            chunk_b_text = get_chunk_text(claim_b["chunk_id"])

            judgment = llm_judge_conflict(claim_a, claim_b, chunk_a_text, chunk_b_text)

            print(f"[DEBUG] LLM judgment: {judgment}")
            if not judgment.get("is_material_discrepancy", True):
                print(f"[DEBUG]  -> FILTERED OUT by LLM")
                continue
        judged_conflicts.append(conf)
        print(f"[DEBUG]  -> KEPT")


    stored_conflict_count = 0
    for conf in judged_conflicts:
        claim_a = conf["claim_a"]
        claim_b = conf["claim_b"]
        doc_a = get_document(claim_a["doc_id"])
        doc_b = get_document(claim_b["doc_id"])
        
        chunk_a_text = get_chunk_text(claim_a["chunk_id"])
        chunk_b_text = get_chunk_text(claim_b["chunk_id"])
        
        explanation = explain_conflict(claim_a, claim_b, doc_a, doc_b, chunk_a_text, chunk_b_text)
        explanation_json = json.dumps(_json_safe(explanation))
        
        conflict_id = insert_conflict(
            claim_a["claim_id"],
            claim_b["claim_id"],
            conf["severity"],
            explanation_json
        )
        stored_conflict_count += 1
    
    return {
        "doc_id": doc_id,
        "chunks_created": len(chunks),
        "claims_extracted": len(all_claims),
        "conflicts_detected": len(judged_conflicts),
        "conflicts_stored": stored_conflict_count
    }


