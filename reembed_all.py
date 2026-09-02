"""Re-embed all stored vectors against the currently configured EMBED_MODEL.

Use after an EMBED_MODEL change in .env / example.env (D-EMB-UPGRADE):
the stored embeddings (memories, conversations, corpus additions) were
written with the old model's dimension, and mixing two dimensions breaks
cosine similarity. Run this so every stored vector matches the new model.

Re-embeds:
  - memories.embedding and conversations.embedding (assistant.db)
  - corpus_data/additions_embeddings.npy (deleted; the corpus feeder rebuilds
    it index-aligned from additions.jsonl on next run)

Safe to re-run; dimensions are idempotent. Has no effect if none of the
source rows are present. The base tool corpus (_TOOL_EMBED_CORPUS) is
embedded fresh in-memory at runtime, so it needs no migration.
"""

import logging
import sqlite3

import numpy as np

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("reembed")


def main():
    import config
    from embedding import embed, model_dim

    dim = model_dim()
    log.info("Configured EMBED_MODEL dimension: %d", dim)

    db = config.DB_PATH
    conn = sqlite3.connect(db)
    cur = conn.cursor()

    # --- conversations ---
    convo_rows = cur.execute(
        "SELECT id, content FROM conversations WHERE embedding IS NOT NULL"
    ).fetchall()
    if convo_rows:
        log.info("Re-embedding %d conversation rows…", len(convo_rows))
        for cid, content in convo_rows:
            new_blob = embed(content or "")
            if len(np.frombuffer(new_blob, dtype="float32")) != dim:
                log.warning("dimension mismatch for conversation %s", cid)
                continue
            cur.execute("UPDATE conversations SET embedding = ? WHERE id = ?", (new_blob, cid))
        conn.commit()
    else:
        log.info("No conversation embeddings to re-embed.")

    # --- memories ---
    mem_rows = cur.execute(
        "SELECT id, content FROM memories WHERE embedding IS NOT NULL"
    ).fetchall()
    if mem_rows:
        log.info("Re-embedding %d memory rows…", len(mem_rows))
        for mid, content in mem_rows:
            new_blob = embed(content or "")
            cur.execute("UPDATE memories SET embedding = ? WHERE id = ?", (new_blob, mid))
        conn.commit()
    else:
        log.info("No memory embeddings to re-embed.")
    conn.close()

    # --- corpus additions ---
    # Import lazily so an unconfigured env does not fail before the DB step.
    from corpus_feeder import EMBEDDINGS_FILE
    if EMBEDDINGS_FILE.exists():
        EMBEDDINGS_FILE.unlink(missing_ok=True)
        log.info("Removed %s — corpus feeder will rebuild it from additions.jsonl", EMBEDDINGS_FILE.name)
    else:
        log.info("No corpus additions embeddings file to remove.")

    log.info("Done. Run the service so the corpus feeder regenerates the npy.")


if __name__ == "__main__":
    main()
