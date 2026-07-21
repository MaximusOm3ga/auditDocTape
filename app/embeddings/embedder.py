from sentence_transformers import SentenceTransformer

_model = SentenceTransformer("all-MiniLM-L6-v2")

def embed(texts: list[str]):

    return _model.encode(texts, normalize_embeddings=True).tolist()



