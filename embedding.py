import numpy as np
from fastembed import TextEmbedding
import pickle
import logging
import os

logger = logging.getLogger("piSynapse")

MODEL_NAME = os.getenv(
    "EMBED_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

_model: TextEmbedding | None = None


def get_model() -> TextEmbedding:
    global _model
    if _model is None:
        logger.info(f"⚡ Loading FastEmbed model '{MODEL_NAME}' on ONNX Runtime...")
        _model = TextEmbedding(model_name=MODEL_NAME)
        logger.info("✅ FastEmbed model loaded.")
    return _model


def embed(text: str) -> bytes:
    """Converts text to a float32 embedding vector, serialized as a pickle BLOB for SQLite."""
    model = get_model()
    vec = list(model.embed([text]))[0]
    return pickle.dumps(vec.astype("float32"))


def cosine_similarity(blob_a: bytes, blob_b: bytes) -> float:
    """Computes cosine similarity between two pickle-serialized embedding vectors."""
    if not blob_a or not blob_b:
        return 0.0
    try:
        a = np.asarray(pickle.loads(blob_a), dtype="float32")
        b = np.asarray(pickle.loads(blob_b), dtype="float32")
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)
    except Exception as e:
        logger.error(f"cosine_similarity error: {e}")
        return 0.0