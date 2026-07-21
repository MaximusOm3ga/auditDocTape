import sqlite3
import os
from datetime import datetime
from typing import Optional, Dict, List, Any

DB_PATH = "./data/audit.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs("./data", exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            entity TEXT NOT NULL,
            effective_date TEXT NOT NULL,
            supersedes_id TEXT REFERENCES documents(doc_id),
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL REFERENCES documents(doc_id),
            chunk_index INTEGER NOT NULL,
            raw_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            claim_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL REFERENCES documents(doc_id),
            chunk_id TEXT NOT NULL REFERENCES chunks(chunk_id),
            entity TEXT NOT NULL,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            value TEXT NOT NULL,
            value_type TEXT NOT NULL,
            unit TEXT,
            confidence REAL DEFAULT 0.8,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_claims_entity_subject_predicate 
        ON claims(entity, subject, predicate)
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conflicts (
            conflict_id TEXT PRIMARY KEY,
            claim_id_a TEXT NOT NULL REFERENCES claims(claim_id),
            claim_id_b TEXT NOT NULL REFERENCES claims(claim_id),
            severity REAL NOT NULL,
            status TEXT DEFAULT 'open',
            explanation TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conflicts_status_severity 
        ON conflicts(status, severity DESC)
    """)
    
    conn.commit()
    conn.close()
def insert_document(doc_id: str, filename: str, doc_type: str, entity: str, 
                   effective_date: str, supersedes_id: Optional[str] = None) -> str:
    """Insert a document with metadata."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO documents (doc_id, filename, doc_type, entity, effective_date, supersedes_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (doc_id, filename, doc_type, entity, effective_date, supersedes_id))
    conn.commit()
    conn.close()
    return doc_id

def get_document(doc_id: str) -> Optional[Dict]:
    """Retrieve document metadata."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_supersedes(doc_id: str) -> Optional[str]:
    """Get the doc_id that this document supersedes."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT supersedes_id FROM documents WHERE doc_id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] else None
def insert_chunk(chunk_id: str, doc_id: str, chunk_index: int, raw_text: str) -> str:
    """Insert a document chunk."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO chunks (chunk_id, doc_id, chunk_index, raw_text)
        VALUES (?, ?, ?, ?)
    """, (chunk_id, doc_id, chunk_index, raw_text))
    conn.commit()
    conn.close()
    return chunk_id

def get_chunk_text(chunk_id: str) -> str:
    """Retrieve chunk raw text."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT raw_text FROM chunks WHERE chunk_id = ?", (chunk_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ""
def insert_claim(claim: Dict) -> str:
    """Insert an extracted claim into the structured store."""
    conn = get_connection()
    cursor = conn.cursor()
    claim_id = claim.get("claim_id", f"{claim['doc_id']}_{claim['chunk_id']}")
    
    cursor.execute("""
        INSERT INTO claims 
        (claim_id, doc_id, chunk_id, entity, subject, predicate, value, value_type, unit, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        claim_id,
        claim["doc_id"],
        claim["chunk_id"],
        claim["entity"],
        claim["subject"],
        claim["predicate"],
        claim["value"],
        claim["value_type"],
        claim.get("unit"),
        claim.get("confidence", 0.8)
    ))
    conn.commit()
    conn.close()
    return claim_id

def get_claim(claim_id: str) -> Optional[Dict]:
    """Retrieve a specific claim."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_claims_for_entity(entity: str) -> List[Dict]:
    """Get all claims for a specific entity (for conflict detection)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, d.effective_date 
        FROM claims c
        JOIN documents d ON c.doc_id = d.doc_id
        WHERE c.entity = ?
        ORDER BY c.created_at
    """, (entity,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
def insert_conflict(claim_id_a: str, claim_id_b: str, severity: float, explanation: str) -> str:
    """Insert a detected conflict."""
    conn = get_connection()
    cursor = conn.cursor()
    conflict_id = f"conf_{claim_id_a}_{claim_id_b}"
    
    cursor.execute("""
        INSERT INTO conflicts (conflict_id, claim_id_a, claim_id_b, severity, explanation, status)
        VALUES (?, ?, ?, ?, ?, 'open')
    """, (conflict_id, claim_id_a, claim_id_b, severity, explanation))
    conn.commit()
    conn.close()
    return conflict_id

def get_conflicts(min_severity: float = 0.0, status: str = "open") -> List[Dict]:
    """Retrieve conflicts, optionally filtered by severity and status."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM conflicts 
        WHERE severity >= ? AND status = ?
        ORDER BY severity DESC, created_at DESC
    """, (min_severity, status))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_conflict_status(conflict_id: str, status: str, resolved_at: Optional[str] = None):
    """Update conflict status (open, resolved, false_positive)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE conflicts 
        SET status = ?, resolved_at = ?
        WHERE conflict_id = ?
    """, (status, resolved_at or datetime.now().isoformat(), conflict_id))
    conn.commit()
    conn.close()
def get_document_supersession_chain(doc_id: str) -> List[str]:
    """Get the full chain of supersessions for a document."""
    chain = [doc_id]
    current = doc_id
    
    while True:
        superseded = get_supersedes(current)
        if not superseded:
            break
        chain.append(superseded)
        current = superseded
    
    return chain

def are_in_supersession_relationship(doc_id_a: str, doc_id_b: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        WITH RECURSIVE chain AS (
            SELECT doc_id, supersedes_id FROM documents WHERE doc_id = ?
            UNION ALL
            SELECT d.doc_id, d.supersedes_id FROM documents d
            JOIN chain c ON d.doc_id = c.supersedes_id
        )
        SELECT 1 FROM chain WHERE supersedes_id = ? LIMIT 1
    """, (doc_id_a, doc_id_b))
    
    result = cursor.fetchone()
    conn.close()
    return result is not None

