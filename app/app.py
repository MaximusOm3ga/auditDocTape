
from fastapi import FastAPI, UploadFile, File, Form
import shutil
import uuid
import json
import os

from app.database_pg import init_db, insert_document, get_document, get_conflicts as db_get_conflicts, get_claim, update_conflict_status
from app.ingestion.parsers import parse_document
from app.orchestration.pipeline import process_document
from app.embeddings.chroma_store import ChromaStore
from fastapi.responses import FileResponse, HTMLResponse
app = FastAPI(title="Audit Doc Tape", description="Document & Claims Intelligence System")
init_db()
chroma_store = ChromaStore()
os.makedirs("./data/uploads", exist_ok=True)


@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    entity: str = Form(...),
    effective_date: str = Form(...),
    supersedes: str = Form(None)
):

    try:
       doc_id = str(uuid.uuid4())
       ext = file.filename.split(".")[-1].lower()
       path = f"./data/uploads/{doc_id}.{ext}"
       with open(path, "wb") as f:
           shutil.copyfileobj(file.file, f)
       text = parse_document(path, ext)
       supersedes_id = None
       insert_document(file.filename, doc_type, entity, effective_date, supersedes_id)
       result = process_document(doc_id, doc_type, entity, text)
        
       return {
           "status": "success",
           "doc_id": doc_id,
           "processing": result
       }
    
    except Exception as e:
       return {
           "status": "error",
           "message": str(e)
       }


@app.get("/conflicts")
async def list_conflicts(min_severity: float = 0.0, status: str = "open"):

    try:
       conflicts = db_get_conflicts(min_severity, status)
        
       detailed_conflicts = []
       for conf in conflicts:
           claim_a = get_claim(conf["claim_id_a"])
           claim_b = get_claim(conf["claim_id_b"])
           doc_a = get_document(claim_a["doc_id"]) if claim_a else None
           doc_b = get_document(claim_b["doc_id"]) if claim_b else None
           try:
               explanation = json.loads(conf["explanation"]) if conf["explanation"] else {}
           except json.JSONDecodeError:
               explanation = {"error": "Could not parse explanation"}
            
           detailed_conflicts.append({
               "conflict_id": conf["conflict_id"],
               "severity": conf["severity"],
               "status": conf["status"],
               "created_at": conf["created_at"],
               "claim_a": {
                   "claim_id": claim_a["claim_id"] if claim_a else None,
                   "value": claim_a["value"] if claim_a else None,
                   "unit": claim_a.get("unit") if claim_a else None,
                   "predicate": claim_a["predicate"] if claim_a else None,
                   "confidence": claim_a.get("confidence") if claim_a else None,
                   "document": {
                       "doc_id": doc_a["doc_id"] if doc_a else None,
                       "filename": doc_a["filename"] if doc_a else None,
                       "effective_date": doc_a["effective_date"] if doc_a else None,
                       "doc_type": doc_a["doc_type"] if doc_a else None,
                   }
               },
               "claim_b": {
                   "claim_id": claim_b["claim_id"] if claim_b else None,
                   "value": claim_b["value"] if claim_b else None,
                   "unit": claim_b.get("unit") if claim_b else None,
                   "predicate": claim_b["predicate"] if claim_b else None,
                   "confidence": claim_b.get("confidence") if claim_b else None,
                   "document": {
                       "doc_id": doc_b["doc_id"] if doc_b else None,
                       "filename": doc_b["filename"] if doc_b else None,
                       "effective_date": doc_b["effective_date"] if doc_b else None,
                       "doc_type": doc_b["doc_type"] if doc_b else None,
                   }
               },
               "explanation": explanation
           })
        
       return {
           "status": "success",
           "count": len(detailed_conflicts),
           "conflicts": detailed_conflicts
       }
    
    except Exception as e:
       return {
           "status": "error",
           "message": str(e)
       }


@app.get("/entities/{entity}/claims")
async def entity_claims(entity: str):
    try:
       from app.database_pg import get_claims_for_entity
       claims = get_claims_for_entity(entity)
        
       return {
           "status": "success",
           "entity": entity,
           "claim_count": len(claims),
           "claims": claims
       }
    
    except Exception as e:
       return {
           "status": "error",
           "message": str(e)
       }


@app.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict(conflict_id: str, resolution: str = "resolved"):

    try:
       update_conflict_status(conflict_id, resolution)
       return {
           "status": "success",
           "conflict_id": conflict_id,
           "resolution": resolution
       }
    except Exception as e:
       return {
           "status": "error",
           "message": str(e)
       }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    with open("./app/Ui.html",encoding="utf-8") as f:
        return f.read()