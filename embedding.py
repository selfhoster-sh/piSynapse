"""Text embeddings via FastEmbed (ONNX). Used by intent classifier and memory search."""
import asyncio
import logging
import os
import threading
import warnings

import numpy as np
from fastembed import TextEmbedding

logger = logging.getLogger("piSynapse")

MODEL_NAME = os.getenv(
    "EMBED_MODEL",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
)

_model: TextEmbedding | None = None
_model_lock = threading.Lock()


def get_model() -> TextEmbedding:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                warnings.filterwarnings("ignore", message=".*now uses mean pooling.*")
                logger.info(f"⚡ Loading FastEmbed model '{MODEL_NAME}' on ONNX Runtime...")
                _model = TextEmbedding(model_name=MODEL_NAME)
                logger.info("✅ FastEmbed model loaded.")
    return _model


def embed(text: str) -> bytes:
    """Converts text to a float32 embedding vector, serialized as raw bytes for SQLite."""
    model = get_model()
    vec = list(model.embed([text]))[0]
    return vec.astype("float32").tobytes()


async def embed_async(text: str) -> bytes:
    """Async wrapper around embed() — offloads the blocking ONNX inference to a thread
    so it doesn't stall the FastAPI event loop.
    """
    return await asyncio.to_thread(embed, text)


async def embed_batch_async(texts: list[str]) -> list[bytes]:
    """Embed a batch of texts off the event loop (used by the intent classifier)."""
    def _run():
        model = get_model()
        return [vec.astype("float32").tobytes() for vec in model.embed(texts)]
    return await asyncio.to_thread(_run)


def model_dim() -> int:
    """Embedding dimension of the currently configured model (lazy-loads it).

    Used by migration/re-embed tooling to detect stale rows written by a
    different-dimension model after an upgrade.
    """
    vec = np.frombuffer(embed(""), dtype="float32")
    return int(vec.size)


def cosine_similarity(blob_a: bytes, blob_b: bytes) -> float:
    """Computes cosine similarity between two embedding vectors (raw bytes or legacy pickle)."""
    if not blob_a or not blob_b:
        return 0.0
    try:
        a = _deserialize(blob_a)
        b = _deserialize(blob_b)
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)
    except Exception as e:
        logger.error(f"cosine_similarity error: {e}")
        return 0.0


def _deserialize(blob: bytes) -> np.ndarray:
    """Deserialize an embedding vector stored in SQLite.

    Rows written today hold raw float32 bytes (see ``embed()``). Very old rows
    may hold a legacy numpy pickle — these are rejected for security (arbitrary
    code execution risk). Raw buffers can start with any byte (e.g. 0x80 from
    a negative float), so detect by length/finiteness rather than a magic byte.
    """
    if blob.startswith(b"\x93NUMPY"):  # numpy .npy container
        import io
        return np.load(io.BytesIO(blob), allow_pickle=False)
    if len(blob) % 4 == 0:
        arr = np.frombuffer(blob, dtype="float32")
        if arr.size > 0 and np.all(np.isfinite(arr)) and np.max(np.abs(arr)) < 1000:
            return arr
    # Reject unrecognized formats (including legacy pickle) — unpickling
    # untrusted data is arbitrary code execution.
    raise ValueError("Unrecognized embedding format — re-embed this memory")
