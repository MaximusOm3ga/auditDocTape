from psycopg2 import pool
from contextlib import contextmanager
from typing import Optional, Dict, List
from datetime import datetime

from app.config import (
    DB_HOST, DB_PORT, DB_NAME,
    DB_USER, DB_PASSWORD, DB_POOL_MIN, DB_POOL_MAX
)
_connection_pool: Optional[pool.SimpleConnectionPool] = None


def init_connection_pool():
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = pool.SimpleConnectionPool(
            DB_POOL_MIN,
            DB_POOL_MAX,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD if DB_PASSWORD else None
        )
        print(f"Connection pool initialized ({DB_POOL_MIN}-{DB_POOL_MAX} connections)")


def close_connection_pool():
    global _connection_pool
    if _connection_pool is not None:
        _connection_pool.closeall()
        print("Connection pool closed")


@contextmanager
def get_db_connection():
    conn = _connection_pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        _connection_pool.putconn(conn)


def init_db():
    init_connection_pool()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS \"btree_gin\"")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                filename TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                entity TEXT NOT NULL,
                effective_date DATE NOT NULL,
                supersedes_id UUID REFERENCES documents(doc_id),
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active',
                
                CONSTRAINT valid_status CHECK (status IN ('active', 'archived', 'deleted')),
                CONSTRAINT valid_doc_type CHECK (doc_type IN ('contract', 'financial_report', 'policy'))
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                raw_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                claim_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
                chunk_id UUID NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
                entity TEXT NOT NULL,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                value TEXT NOT NULL,
                value_type TEXT NOT NULL,
                unit TEXT,
                confidence REAL DEFAULT 0.8,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                CONSTRAINT valid_value_type CHECK (value_type IN ('number', 'date', 'string', 'currency')),
                CONSTRAINT valid_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_claims_entity_subject_predicate 
            ON claims(entity, subject, predicate)
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conflicts (
                conflict_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                claim_id_a UUID NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
                claim_id_b UUID NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
                severity REAL NOT NULL,
                status TEXT DEFAULT 'open',
                explanation TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                
                CONSTRAINT valid_severity CHECK (severity >= 0.0 AND severity <= 1.0),
                CONSTRAINT valid_conflict_status CHECK (status IN ('open', 'resolved', 'false_positive'))
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conflicts_status_severity 
            ON conflicts(status, severity DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_claims_doc_id ON claims(doc_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_claims_chunk_id ON claims(chunk_id)
        """)
        
        print("Database schema initialized successfully")
def insert_document(filename: str, doc_type: str, entity: str, 
                   effective_date: str, supersedes_id: Optional[str] = None) -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO documents (filename, doc_type, entity, effective_date, supersedes_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING doc_id::text
        """, (filename, doc_type, entity, effective_date, supersedes_id))
        doc_id = cursor.fetchone()[0]
    return doc_id


def get_document(doc_id: str) -> Optional[Dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT doc_id::text, filename, doc_type, entity, effective_date, 
                   supersedes_id::text, uploaded_at, status
            FROM documents 
            WHERE doc_id = %s::uuid
        """, (doc_id,))
        row = cursor.fetchone()
        
        if row:
            columns = ['doc_id', 'filename', 'doc_type', 'entity', 'effective_date', 
                      'supersedes_id', 'uploaded_at', 'status']
            return dict(zip(columns, row))
    return None


def get_supersedes(doc_id: str) -> Optional[str]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT supersedes_id::text 
            FROM documents 
            WHERE doc_id = %s::uuid
        """, (doc_id,))
        row = cursor.fetchone()
        return row[0] if row and row[0] else None
def insert_chunk(doc_id: str, chunk_index: int, raw_text: str) -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chunks (doc_id, chunk_index, raw_text)
            VALUES (%s::uuid, %s, %s)
            RETURNING chunk_id::text
        """, (doc_id, chunk_index, raw_text))
        chunk_id = cursor.fetchone()[0]
    return chunk_id


def get_chunk_text(chunk_id: str) -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT raw_text 
            FROM chunks 
            WHERE chunk_id = %s::uuid
        """, (chunk_id,))
        row = cursor.fetchone()
        return row[0] if row else ""
def insert_claim(claim: Dict) -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO claims 
            (doc_id, chunk_id, entity, subject, predicate, value, value_type, unit, confidence)
            VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s)
            RETURNING claim_id::text
        """, (
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
        claim_id = cursor.fetchone()[0]
    return claim_id


def get_claim(claim_id: str) -> Optional[Dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT claim_id::text, doc_id::text, chunk_id::text, entity, subject, predicate, 
                   value, value_type, unit, confidence, created_at
            FROM claims 
            WHERE claim_id = %s::uuid
        """, (claim_id,))
        row = cursor.fetchone()
        
        if row:
            columns = ['claim_id', 'doc_id', 'chunk_id', 'entity', 'subject', 'predicate',
                      'value', 'value_type', 'unit', 'confidence', 'created_at']
            return dict(zip(columns, row))
    return None


def get_claims_for_entity(entity: str) -> List[Dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.claim_id::text, c.doc_id::text, c.chunk_id::text, c.entity, 
                   c.subject, c.predicate, c.value, c.value_type, c.unit, 
                   c.confidence, c.created_at, d.effective_date
            FROM claims c
            JOIN documents d ON c.doc_id = d.doc_id
            WHERE c.entity = %s
            ORDER BY c.created_at
        """, (entity,))
        rows = cursor.fetchall()
        
        claims = []
        for row in rows:
            columns = ['claim_id', 'doc_id', 'chunk_id', 'entity', 'subject', 'predicate',
                      'value', 'value_type', 'unit', 'confidence', 'created_at', 'effective_date']
            claims.append(dict(zip(columns, row)))
        return claims
def insert_conflict(claim_id_a: str, claim_id_b: str, severity: float, explanation: str) -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conflicts (claim_id_a, claim_id_b, severity, explanation, status)
            VALUES (%s::uuid, %s::uuid, %s, %s, 'open')
            RETURNING conflict_id::text
        """, (claim_id_a, claim_id_b, severity, explanation))
        conflict_id = cursor.fetchone()[0]
    return conflict_id


def get_conflicts(min_severity: float = 0.0, status: str = "open") -> List[Dict]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT conflict_id::text, claim_id_a::text, claim_id_b::text, 
                   severity, status, explanation, created_at, resolved_at
            FROM conflicts 
            WHERE severity >= %s AND status = %s
            ORDER BY severity DESC, created_at DESC
        """, (min_severity, status))
        rows = cursor.fetchall()
        
        conflicts = []
        for row in rows:
            columns = ['conflict_id', 'claim_id_a', 'claim_id_b', 'severity', 
                      'status', 'explanation', 'created_at', 'resolved_at']
            conflicts.append(dict(zip(columns, row)))
        return conflicts


def update_conflict_status(conflict_id: str, status: str, resolved_at: Optional[str] = None):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE conflicts 
            SET status = %s, resolved_at = %s
            WHERE conflict_id = %s::uuid
        """, (status, resolved_at or datetime.now().isoformat(), conflict_id))
def get_document_supersession_chain(doc_id: str) -> List[str]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            WITH RECURSIVE supersession_chain AS (
                SELECT doc_id::text, supersedes_id::text, 1 as depth
                FROM documents
                WHERE doc_id = %s::uuid
                
                UNION ALL
                
                SELECT d.doc_id::text, d.supersedes_id::text, sc.depth + 1
                FROM documents d
                JOIN supersession_chain sc ON d.doc_id = sc.supersedes_id::uuid
            )
            SELECT doc_id FROM supersession_chain
            ORDER BY depth
        """, (doc_id,))
        
        rows = cursor.fetchall()
        return [row[0] for row in rows]


def are_in_supersession_relationship(doc_id_a: str, doc_id_b: str) -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            WITH RECURSIVE chain AS (
                SELECT doc_id::text, supersedes_id::text FROM documents WHERE doc_id = %s::uuid
                UNION ALL
                SELECT d.doc_id::text, d.supersedes_id::text FROM documents d
                JOIN chain c ON d.doc_id = c.supersedes_id::uuid
            )
            SELECT 1 FROM chain WHERE supersedes_id::text = %s LIMIT 1
        """, (doc_id_a, doc_id_b))
        
        result = cursor.fetchone()
        return result is not None
def health_check() -> bool:
    try:
        if _connection_pool is None:
            init_connection_pool()

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            return True
    except Exception as e:
        print(f"Database health check failed: {e}")
        return False
