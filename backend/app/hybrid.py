import json
import math
import re
import time
from collections import Counter
from pathlib import Path

import requests

from . import config, embeddings, milvus_store

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
WORD_RE = re.compile(r"[a-zA-Z0-9]+")

_docs_cache: dict = {"ts": 0, "docs": [], "bm25": None}


def tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    tokens: list[str] = []
    for cjk in CJK_RE.findall(text):
        if len(cjk) == 1:
            tokens.append(cjk)
        for index in range(len(cjk) - 1):
            tokens.append(cjk[index : index + 2])
    for word in WORD_RE.findall(text):
        tokens.append(word)
    return tokens


class BM25Index:
    def __init__(self, token_docs: list[list[str]]):
        self.token_docs = token_docs
        self.doc_count = len(token_docs)
        self.avgdl = sum(len(doc) for doc in token_docs) / max(len(token_docs), 1)
        self.df: Counter = Counter()
        for doc in token_docs:
            self.df.update(set(doc))
        self.idf = {
            term: math.log(1 + (self.doc_count - df + 0.5) / (df + 0.5))
            for term, df in self.df.items()
        }

    def scores(self, query_tokens: list[str]) -> list[float]:
        k1, b = 1.5, 0.75
        result = []
        query_set = set(query_tokens)
        for doc in self.token_docs:
            doc_length = len(doc)
            tf = Counter(doc)
            score = 0.0
            for term in query_set:
                if term in self.idf:
                    freq = tf.get(term, 0)
                    score += (
                        self.idf[term]
                        * freq
                        * (k1 + 1)
                        / (freq + k1 * (1 - b + b * doc_length / self.avgdl))
                    )
            result.append(score)
        return result


def _split_chunks(text: str, title: str, category: str, size: int = 400) -> list[dict]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks = []
    buffer = ""
    for paragraph in paragraphs:
        if len(buffer) + len(paragraph) + 1 <= size:
            buffer = f"{buffer}\n{paragraph}" if buffer else paragraph
            continue
        if buffer:
            chunks.append({"text": buffer, "title": title, "category": category})
            buffer = paragraph
        else:
            while len(paragraph) > size:
                chunks.append({"text": paragraph[:size], "title": title, "category": category})
                paragraph = paragraph[size - 60 :]
            buffer = paragraph
    if buffer:
        chunks.append({"text": buffer, "title": title, "category": category})
    return chunks


def _scenic_of(item: dict, default: str = "hangzhou") -> str:
    return str(item.get("scenic_area") or item.get("metadata", {}).get("scenic_area") or default)


def _load_docs() -> tuple[list[dict], BM25Index]:
    cache = _docs_cache
    if cache["bm25"] is not None and time.time() - cache["ts"] < 600:
        return cache["docs"], cache["bm25"]

    docs: list[dict] = []
    md_path = DATA_DIR / "hangzhou_knowledge.md"
    if md_path.exists():
        content = md_path.read_text(encoding="utf-8")
        sections = re.split(r"\n(?=## )", content)
        for section in sections:
            lines = section.strip().splitlines()
            title = "杭州知识库"
            scenic_area = "hangzhou"
            if lines and lines[0].startswith("## "):
                header = lines[0][3:].strip()
                title = header
                for part in re.split(r"[【\]]", header):
                    if part.strip():
                        scenic_area = part.strip()
                        break
                lines = lines[1:]
            body = "\n".join(line for line in lines if not line.startswith("### ")).strip()
            if body:
                for chunk in _split_chunks(body, title, "景区知识"):
                    chunk["scenic_area"] = scenic_area
                    chunk["metadata"] = {"type": "knowledge", "scenic_area": scenic_area}
                    docs.append(chunk)

    for filename, category, label in (
        ("tickets.json", "票务数据", "【票务信息】"),
        ("attractions.json", "景点信息", "【景点】"),
        ("routes.json", "路线推荐", "【路线推荐】"),
    ):
        path = DATA_DIR / filename
        if not path.exists():
            continue
        for item in json.loads(path.read_text(encoding="utf-8")):
            scenic_area = _scenic_of(item)
            if category == "票务数据":
                text = (
                    f"{label}{item['name']}：价格 {item['price']}。"
                    f"价格说明：{item['price_note']}。开放时间：{item['opening_hours']}。"
                    f"地址：{item['address']}。提示：{item['tips']}。"
                )
                title = item["name"]
            elif category == "景点信息":
                text = (
                    f"{label}{item['name']}：{item['intro']} 地址：{item['address']}。"
                    f"最佳游览时间：{item['best_time']}。提示：{item['tips']}。"
                )
                title = item["name"]
            else:
                stop_lines = [
                    f"{stop['name']}（到达第 {stop['offset_minutes']} 分钟，停留 {stop['duration_minutes']} 分钟）：{stop['description']}"
                    for stop in item["stops"]
                ]
                text = f"{label}{item['title']}：{item['summary']}\n" + "\n".join(stop_lines)
                title = item["title"]
            for chunk in _split_chunks(text, title, category):
                chunk["scenic_area"] = scenic_area
                chunk["metadata"] = {"type": category, "scenic_area": scenic_area}
                docs.append(chunk)

    bm25 = BM25Index([tokenize(doc["text"]) for doc in docs])
    cache.update({"ts": time.time(), "docs": docs, "bm25": bm25})
    return docs, bm25


def _rrf(ranked_items: list[list[dict]], k: int = 60) -> list[dict]:
    scores: dict[str, float] = {}
    merged: dict[str, dict] = {}
    for ranked in ranked_items:
        for index, item in enumerate(ranked):
            key = item.get("_key", item.get("text", ""))
            merged.setdefault(key, item)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + index + 1)
    ordered = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    return [{**merged[key], "score": round(score, 4)} for key, score in ordered]


def _rerank(query: str, hits: list[dict], top_k: int) -> list[dict]:
    if not hits:
        return hits
    try:
        response = requests.post(
            f"{config.SILICONFLOW_BASE_URL}/rerank",
            headers={"Authorization": f"Bearer {config.SILICONFLOW_API_KEY}"},
            json={
                "model": "BAAI/bge-reranker-v2-m3",
                "query": query,
                "documents": [item["text"] for item in hits],
                "top_n": top_k,
            },
            timeout=20,
        )
        if response.status_code != 200:
            return hits[:top_k]
        results = sorted(
            response.json().get("results", []),
            key=lambda item: item.get("relevance_score", 0),
            reverse=True,
        )
        ordered = []
        for item in results:
            index = item.get("index")
            if index is None or index >= len(hits):
                continue
            ordered.append({**hits[index], "score": round(float(item.get("relevance_score", 0)), 4)})
        return ordered[:top_k] if ordered else hits[:top_k]
    except Exception:
        return hits[:top_k]


def search_hybrid(
    query: str,
    top_k: int = 6,
    scenic_areas: list[str] | None = None,
) -> list[dict]:
    docs, bm25 = _load_docs()
    ranked_bm25 = []
    bm25_scores = bm25.scores(tokenize(query))
    filtered_docs = docs
    if scenic_areas:
        filtered_docs = [doc for doc in docs if _scenic_of(doc) in scenic_areas]
        filtered_scores = [bm25_scores[index] for index, doc in enumerate(docs) if _scenic_of(doc) in scenic_areas]
    else:
        filtered_scores = bm25_scores
    for score, doc in sorted(zip(filtered_scores, filtered_docs), key=lambda pair: pair[0], reverse=True)[:10]:
        if score <= 0:
            continue
        ranked_bm25.append({**doc, "_key": doc["text"], "score": round(float(score), 4)})

    vector_hits = []
    try:
        vector_hits = milvus_store.search(
            embeddings.embed_query(query),
            top_k=10,
            score_threshold=0.15,
            scenic_areas=scenic_areas,
        )
    except Exception:
        vector_hits = []

    fused = _rrf([vector_hits, ranked_bm25]) if vector_hits else ranked_bm25
    return _rerank(query, fused, top_k)
