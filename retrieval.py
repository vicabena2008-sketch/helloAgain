"""
retrieval.py
Builds the FAISS index from knowledge_base and exposes retrieve_context().
"""

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

RELEVANCE_THRESHOLD = 0.30

# ── Embedding model + FAISS index ─────────────────────────────────────────────
print("Loading embedding model...")
embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

documents: list[str] = []
doc_metadata: list[dict] = []
index = None


def rebuild_index():
    global documents, doc_metadata, index
    from db.customers import get_all_kb_items

    kb_items = get_all_kb_items()
    new_docs = []
    new_meta = []

    for item in kb_items:
        in_stock_bool = bool(item["in_stock"])
        stock_tag = "IN STOCK" if in_stock_bool else "OUT OF STOCK"
        count_tag = f" (qty: {item['stock_count']})" if item['stock_count'] is not None else ""
        image_str = f"IMAGE URL: {item['image_url']}\n" if item.get("image_url") else ""

        doc = (
            f"[CATEGORY: {item['category'].upper()}]\n"
            f"BRAND / TYPE: {item.get('brand', 'General')}\n"
            f"STOCK STATUS: {stock_tag}{count_tag}\n"
            f"{image_str}"
            f"DETAILS: {item['content']}"
        ).strip()

        new_docs.append(doc)
        new_meta.append({
            "in_stock": in_stock_bool,
            "category": item["category"],
            "brand":    item["brand"],
            "image_url": item.get("image_url", ""),
        })

    if new_docs:
        new_embs = embedding_model.encode(new_docs, show_progress_bar=False)
        faiss.normalize_L2(new_embs)
        
        new_index = faiss.IndexFlatIP(new_embs.shape[1])
        new_index.add(np.array(new_embs, dtype=np.float32))
        
        documents = new_docs
        doc_metadata = new_meta
        index = new_index
        print(f"FAISS index rebuilt dynamically — {index.ntotal} vectors.")
    else:
        documents = []
        doc_metadata = []
        index = faiss.IndexFlatIP(384)
        print("FAISS index is empty (no products in knowledge base).")


# Initial build on import
rebuild_index()


# ── Public API ────────────────────────────────────────────────────────────────
def retrieve_context(user_query: str, top_k: int = 5) -> list[tuple]:
    """Returns [(score, doc_text, metadata), ...] sorted by score DESC."""
    if not user_query.strip() or index is None or index.ntotal == 0:
        return []

    q_emb = embedding_model.encode([user_query], convert_to_numpy=True)
    faiss.normalize_L2(q_emb)
    scores, indices = index.search(q_emb.astype(np.float32), top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx != -1 and idx < len(documents) and score >= RELEVANCE_THRESHOLD:
            results.append((float(score), documents[idx], doc_metadata[idx]))

    results.sort(key=lambda x: x[0], reverse=True)
    return results


def split_by_stock(retrieved: list) -> tuple[list, list]:
    """Returns (in_stock_docs, out_of_stock_brands)."""
    in_stock   = [doc for _, doc, meta in retrieved if meta["in_stock"]]
    oos_brands = [meta["brand"] for _, _, meta in retrieved if not meta["in_stock"]]
    return in_stock, oos_brands
