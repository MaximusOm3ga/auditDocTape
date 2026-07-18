import chromadb

import os

class ChromaStore:

    def __init__(self, persist_dir: str = "./data/chroma", collection_name: str = "chunks"):

        self.client = chromadb.PersistentClient(path=persist_dir)

        self.collection = self.client.get_or_create_collection(

            name=collection_name,

            metadata={"hnsw:space": "cosine"},

        )

    def add(self, vectors: list[list[float]], chunk_ids: list[str], texts: list[str],

            metadatas: list[dict]):

        """metadatas: one dict per chunk, e.g. {'doc_id': ..., 'entity': ..., 'doc_type': ...,

        'effective_date': ..., 'superseded': False}"""

        self.collection.add(

            ids=chunk_ids,

            embeddings=vectors,

            documents=texts,

            metadatas=metadatas,

        )

    def mark_superseded(self, doc_id: str):

        """Flip a metadata flag rather than deleting — keeps history intact but excludes

        the doc from default retrieval. Chroma supports metadata updates natively."""

        results = self.collection.get(where={"doc_id": doc_id})

        if results["ids"]:

            self.collection.update(

                ids=results["ids"],

                metadatas=[{**m, "superseded": True} for m in results["metadatas"]],

            )

    def search(self, query_vec: list[float], k: int = 5, entity: str | None = None,

               doc_type: str | None = None, include_superseded: bool = False):

        where = {}

        if entity:

            where["entity"] = entity

        if doc_type:

            where["doc_type"] = doc_type

        if not include_superseded:

            where["superseded"] = False

        results = self.collection.query(

            query_embeddings=[query_vec],

            n_results=k,

            where=where or None,

        )

        return list(zip(results["ids"][0], results["distances"][0]))
