from fastapi import FastAPI, UploadFile, File, Form

import shutil, uuid

app = FastAPI()

@app.post("/documents/upload")

async def upload_document(file: UploadFile = File(...), doc_type: str = Form(...),

                           entity: str = Form(...), effective_date: str = Form(...),

                           supersedes: str = Form(None)):

    doc_id = str(uuid.uuid4())

    ext = file.filename.split(".")[-1].lower()

    path = f"./data/uploads/{doc_id}.{ext}"

    with open(path, "wb") as f:

        shutil.copyfileobj(file.file, f)

    text = parse_document(path, ext)

    db.insert_document(doc_id, file.filename, doc_type, entity, effective_date, supersedes)

    result = process_document(doc_id, doc_type, entity, text, db)

    return {"doc_id": doc_id, **result}

@app.get("/conflicts")

async def list_conflicts(min_severity: float = 0.0, status: str = "open"):

    return db.get_conflicts(min_severity, status)

@app.get("/entities/{entity}/claims")

async def entity_claims(entity: str):

    return db.get_claims_for_entity(entity)

@app.post("/query")

async def query(question: str):

    q_vec = embed([question])[0]

    hits = chroma_store.search(q_vec, k=5)  # pass entity=... / doc_type=... here to scope the query further

    context = "\n\n".join(db.get_chunk_text(cid) for cid, _ in hits)

    resp = client.chat.completions.create(

        model="llama-3.1-8b-instant",

        messages=[{"role": "user", "content": f"Answer using only this context, and cite the source:\n{context}\n\nQuestion: {question}"}],

    )

    return {"answer": resp.choices[0].message.content, "sources": [cid for cid, _ in hits]}
