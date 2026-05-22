"""
retrieval.py
Builds the FAISS index from knowledge_base and exposes retrieve_context().
"""

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from knowledge_base import business_data

RELEVANCE_THRESHOLD = 0.30

# ── Build documents + metadata ────────────────────────────────────────────────
documents: list[str] = []
doc_metadata: list[dict] = []

for item in business_data:
    stock_tag = "IN STOCK" if item["in_stock"] else "OUT OF STOCK"
    count_tag = f" (qty: {item['stock_count']})" if item["stock_count"] is not None else ""

    image_str = f"IMAGE URL: {item['image_url']}\n" if item.get("image_url") else ""

    doc = (
        f"[CATEGORY: {item['category'].upper()}]\n"
        f"BRAND / TYPE: {item.get('brand', 'General')}\n"
        f"STOCK STATUS: {stock_tag}{count_tag}\n"
        f"{image_str}"
        f"DETAILS: {item['content']}"
    ).strip()

    documents.append(doc)
    doc_metadata.append({
        "in_stock": item["in_stock"],
        "category": item["category"],
        "brand":    item["brand"],
        "image_url": item.get("image_url", ""),
    })

# ── Embedding model + FAISS index ─────────────────────────────────────────────
print("Loading embedding model...")
embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

print("Encoding documents...")
embeddings = embedding_model.encode(documents, show_progress_bar=True)
faiss.normalize_L2(embeddings)

index = faiss.IndexFlatIP(embeddings.shape[1])
index.add(np.array(embeddings, dtype=np.float32))
print(f"FAISS index ready — {index.ntotal} vectors.")


# ── Public API ────────────────────────────────────────────────────────────────
def retrieve_context(user_query: str, top_k: int = 5) -> list[tuple]:
    """Returns [(score, doc_text, metadata), ...] sorted by score DESC."""
    if not user_query.strip():
        return []

    q_emb = embedding_model.encode([user_query], convert_to_numpy=True)
    faiss.normalize_L2(q_emb)
    scores, indices = index.search(q_emb.astype(np.float32), top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx != -1 and score >= RELEVANCE_THRESHOLD:
            results.append((float(score), documents[idx], doc_metadata[idx]))

    results.sort(key=lambda x: x[0], reverse=True)
    return results


def split_by_stock(retrieved: list) -> tuple[list, list]:
    """Returns (in_stock_docs, out_of_stock_brands)."""
    in_stock   = [doc for _, doc, meta in retrieved if meta["in_stock"]]
    oos_brands = [meta["brand"] for _, _, meta in retrieved if not meta["in_stock"]]
    return in_stock, oos_brands
