"""
retrieval.py
Builds the FAISS index from knowledge_base and exposes retrieve_context().
"""

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# At the top, add:
import threading
import logging
_index_lock = threading.Lock()
logger = logging.getLogger(__name__)

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

    try:
        if new_docs:
            new_embs = embedding_model.encode(new_docs, show_progress_bar=False, convert_to_numpy=True)
            if not isinstance(new_embs, np.ndarray):
                new_embs = np.array(new_embs, dtype=np.float32)
            faiss.normalize_L2(new_embs)

            new_index = faiss.IndexFlatIP(new_embs.shape[1])
            new_index.add(np.array(new_embs, dtype=np.float32))

            with _index_lock:
                documents = new_docs
                doc_metadata = new_meta
                index = new_index

            print(f"FAISS index rebuilt dynamically - {index.ntotal} vectors.")
        else:
            with _index_lock:
                documents = []
                doc_metadata = []
                index = faiss.IndexFlatIP(384)
            print("FAISS index is empty (no products in knowledge base).")
    except Exception:
        logger.exception("Failed to rebuild FAISS index")
        # leave previous index intact if possible; fall back to empty lists if not
        with _index_lock:
            documents = documents or []
            doc_metadata = doc_metadata or []
            if index is None:
                try:
                    index = faiss.IndexFlatIP(384)
                except Exception:
                    index = None


# Initial build on import
rebuild_index()


# ── Public API ────────────────────────────────────────────────────────────────
def retrieve_context(user_query: str, top_k: int = 5) -> list[tuple]:
    """Returns [(score, doc_text, metadata), ...] sorted by score DESC."""
    if not user_query or not user_query.strip():
        return []

    try:
        # copy references under lock to avoid races with rebuilds
        with _index_lock:
            local_index = index
            local_documents = list(documents)
            local_meta = list(doc_metadata)

        if local_index is None or (hasattr(local_index, "ntotal") and local_index.ntotal == 0):
            return []

        q_emb = embedding_model.encode([user_query], convert_to_numpy=True)
        if not isinstance(q_emb, np.ndarray):
            q_emb = np.array(q_emb, dtype=np.float32)
        faiss.normalize_L2(q_emb)

        scores, indices = local_index.search(q_emb.astype(np.float32), top_k)

        results = []
        q_lower = user_query.lower()
        q_words = [w for w in q_lower.split() if len(w) > 3]

        for score, idx in zip(scores[0], indices[0]):
            if idx != -1 and idx < len(local_documents) and score >= RELEVANCE_THRESHOLD:
                doc_meta = local_meta[idx]
                final_score = float(score)

                # BM25-like exact match boost for query keywords against the document and brand
                doc_text = local_documents[idx].lower()
                brand_text = doc_meta.get("brand", "").lower()
                for w in q_words:
                    if w in brand_text:
                        final_score += 0.10
                    elif w in doc_text:
                        final_score += 0.05

                results.append((final_score, local_documents[idx], doc_meta))

        results.sort(key=lambda x: x[0], reverse=True)
        return results
    except Exception:
        logger.exception("retrieve_context failed")
        return []


def is_brand_relevant(brand: str, category: str, query: str) -> bool:
    """Heuristic to decide if an out-of-stock brand is actually relevant to the user's query.
    Returns True if query contains the brand or brand-specific synonyms/keywords.
    """
    if not brand and not category:
        return False
    q = (query or "").lower()
    b = (brand or "").lower()
    c = (category or "").lower()

    # direct mention of brand
    if b and b in q:
        return True

    # Brand-specific keywords for known OOS brands
    BRAND_OOS_KEYWORDS = {
        "smart tv": ["tv", "television", "screen", "lg", "oled", "smart tv"],
        "jeans and trousers": ["jeans", "trouser", "trousers", "pants", "denim", "chinos", "jeans and trousers"],
    }

    # Find matches in specific brand keywords if the brand is one of our known ones
    for known_brand, keywords in BRAND_OOS_KEYWORDS.items():
        if known_brand in b or b in known_brand:
            for kw in keywords:
                if kw in q:
                    return True
            # If it's a known brand but no keywords match, do not consider it relevant
            return False

    # Check if any token from the brand appears in the query (split on non-alphanumeric)
    import re
    brand_tokens = [t for t in re.findall(r"[a-z0-9]+", b) if len(t) > 2 and t not in ("and", "the", "for", "with")]
    for t in brand_tokens:
        if t and t in q:
            return True

    # Fallback to category name itself being mentioned (e.g. "tech", "fashion")
    if c and c in q:
        return True

    return False


def split_by_stock(retrieved: list, user_query: str | None = None) -> tuple[list, list]:
    """Returns (in_stock_docs, out_of_stock_brands).

    Only include out-of-stock brands if they are relevant to the user query
    (contains brand/category keywords) or if they are the top retrieved result.
    """
    if not retrieved:
        return [], []

    in_stock = []
    oos_brands = []

    top_idx = 0
    for i, (score, doc, meta) in enumerate(retrieved):
        if meta.get("in_stock"):
            in_stock.append(doc)
        else:
            # check relevance
            keep = False
            if i == top_idx:
                keep = True
            else:
                try:
                    keep = is_brand_relevant(meta.get("brand", ""), meta.get("category", ""), user_query or "")
                except Exception:
                    keep = False
            if keep:
                oos_brands.append(meta.get("brand"))

    return in_stock, oos_brands
