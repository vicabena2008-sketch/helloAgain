"""
retrieval.py
Builds the FAISS index from knowledge_base and exposes retrieve_context().
"""

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# At the top, add:
import threading
_index_lock = threading.Lock()

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
        print(f"FAISS index rebuilt dynamically - {index.ntotal} vectors.")
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
    q_lower = user_query.lower()
    q_words = [w for w in q_lower.split() if len(w) > 3]
    
    for score, idx in zip(scores[0], indices[0]):
        if idx != -1 and idx < len(documents) and score >= RELEVANCE_THRESHOLD:
            doc_meta = doc_metadata[idx]
            final_score = float(score)
            
            # BM25-like exact match boost for query keywords against the document and brand
            # This helps counteract FAISS over-indexing on currency or numbers.
            doc_text = documents[idx].lower()
            brand_text = doc_meta.get("brand", "").lower()
            for w in q_words:
                if w in brand_text:
                    final_score += 0.10
                elif w in doc_text:
                    final_score += 0.05
                    
            results.append((final_score, documents[idx], doc_meta))

    results.sort(key=lambda x: x[0], reverse=True)
    return results


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
