import time

from pymilvus import DataType, MilvusClient

from . import config

_client: MilvusClient | None = None
_tested = False
_healthy_until = 0.0


def is_healthy() -> bool:
    if not _tested:
        return True
    return time.time() < _healthy_until


def _mark_unhealthy() -> None:
    global _tested, _healthy_until
    _tested = True
    _healthy_until = time.time()


def get_client() -> MilvusClient:
    global _client
    if _client is None:
        _client = MilvusClient(uri=config.MILVUS_URI)
    return _client


def ensure_collection() -> MilvusClient:
    client = get_client()
    if not client.has_collection(config.COLLECTION_NAME):
        schema = client.create_schema(auto_id=True, enable_dynamic_field=True)
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("text", DataType.VARCHAR, max_length=4096)
        schema.add_field("title", DataType.VARCHAR, max_length=512)
        schema.add_field("category", DataType.VARCHAR, max_length=128)
        schema.add_field("scenic_area", DataType.VARCHAR, max_length=128)
        schema.add_field("metadata", DataType.JSON)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=config.VECTOR_DIM)

        index_params = client.prepare_index_params()
        index_params.add_index(field_name="embedding", index_type="AUTOINDEX", metric_type="COSINE")
        client.create_collection(
            collection_name=config.COLLECTION_NAME,
            schema=schema,
            index_params=index_params,
        )
    return client


def insert_chunks(chunks: list[dict]) -> int:
    client = ensure_collection()
    rows = [
        {
            "text": chunk["text"],
            "title": chunk["title"],
            "category": chunk["category"],
            "scenic_area": chunk.get("metadata", {}).get("scenic_area", "hangzhou"),
            "metadata": chunk.get("metadata", {}),
            "embedding": chunk["embedding"],
        }
        for chunk in chunks
    ]
    client.insert(config.COLLECTION_NAME, rows)
    return len(rows)


def search(
    query_vector: list[float],
    top_k: int = 6,
    score_threshold: float = 0.28,
    scenic_areas: list[str] | None = None,
) -> list[dict]:
    if not is_healthy():
        raise RuntimeError("Milvus 暂时不可用，已切换到关键词检索")
    try:
        client = get_client()
        filter_expr = None
        if scenic_areas:
            safe = [area.replace("'", "") for area in scenic_areas]
            filter_expr = "scenic_area in " + str(safe).replace("'", '"')
        results = client.search(
            collection_name=config.COLLECTION_NAME,
            data=[query_vector],
            limit=top_k,
            output_fields=["text", "title", "category", "scenic_area", "metadata"],
            metric_type="COSINE",
            filter=filter_expr,
            timeout=8,
        )
        hits = []
        for item in results[0]:
            if float(item["distance"]) < score_threshold:
                continue
            entity = item.get("entity", {})
            hits.append(
                {
                    "id": item["id"],
                    "score": round(float(item["distance"]), 4),
                    "text": entity.get("text", ""),
                    "title": entity.get("title", ""),
                    "category": entity.get("category", ""),
                    "scenic_area": entity.get("scenic_area", ""),
                    "metadata": entity.get("metadata", {}),
                }
            )
        return hits
    except Exception:
        _mark_unhealthy()
        raise


def collection_count() -> int:
    if not is_healthy():
        return 0
    try:
        client = get_client()
        if not client.has_collection(config.COLLECTION_NAME):
            return 0
        return client.get_collection_stats(config.COLLECTION_NAME).get("row_count", 0)
    except Exception:
        _mark_unhealthy()
        return 0


def warmup() -> None:
    global _tested, _healthy_until
    try:
        collection_count()
        _tested = True
        _healthy_until = time.time() + 300
    except Exception:
        _mark_unhealthy()
