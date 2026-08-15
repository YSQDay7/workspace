import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import embeddings, milvus_store  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CHUNK_SIZE = 420
OVERLAP = 80


def split_text(text: str, title: str, category: str, metadata: dict | None = None) -> list[dict]:
    chunks = []
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    buffer = ""
    for paragraph in paragraphs:
        if len(buffer) + len(paragraph) + 1 <= CHUNK_SIZE:
            buffer = f"{buffer}\n{paragraph}" if buffer else paragraph
            continue
        if buffer:
            chunks.append(buffer)
            buffer = paragraph
        else:
            while len(paragraph) > CHUNK_SIZE:
                chunks.append(paragraph[:CHUNK_SIZE])
                paragraph = paragraph[CHUNK_SIZE - OVERLAP :]
            buffer = paragraph
    if buffer:
        chunks.append(buffer)
    return [
        {
            "text": chunk,
            "title": title,
            "category": category,
            "metadata": metadata or {},
        }
        for chunk in chunks
    ]


def _scenic_area(header: str, default: str = "hangzhou") -> str:
    for part in re.split(r"[【\]]", header):
        if part.strip():
            return part.strip()
    return default


def load_markdown_chunks() -> list[dict]:
    md_path = DATA_DIR / "hangzhou_knowledge.md"
    content = md_path.read_text(encoding="utf-8")
    chunks: list[dict] = []
    current_title = "杭州知识库"
    current_scenic = "hangzhou"
    current_body: list[str] = []

    for raw_line in content.splitlines():
        if raw_line.startswith("## "):
            if current_body:
                chunks.extend(split_text("\n".join(current_body), current_title, "景区知识", {"scenic_area": current_scenic}))
            header = raw_line[3:].strip()
            current_title = header
            current_scenic = _scenic_area(header)
            current_body = []
        else:
            current_body.append(raw_line)
    if current_body:
        chunks.extend(split_text("\n".join(current_body), current_title, "景区知识", {"scenic_area": current_scenic}))
    return chunks


def load_json_chunks() -> list[dict]:
    chunks: list[dict] = []
    tickets = json.loads((DATA_DIR / "tickets.json").read_text(encoding="utf-8"))
    for ticket in tickets:
        text = (
            f"【票务信息】{ticket['name']}：价格 {ticket['price']}。"
            f"价格说明：{ticket['price_note']}。开放时间：{ticket['opening_hours']}。"
            f"地址：{ticket['address']}。提示：{ticket['tips']}。"
        )
        chunks.extend(
            split_text(
                text,
                ticket["name"],
                "票务数据",
                {
                    "type": "ticket",
                    "scenic_area": ticket["scenic_area"],
                    "price": ticket["price"],
                    "opening_hours": ticket["opening_hours"],
                },
            )
        )

    attractions = json.loads((DATA_DIR / "attractions.json").read_text(encoding="utf-8"))
    for attraction in attractions:
        text = (
            f"【景点】{attraction['name']}：{attraction['intro']} "
            f"地址：{attraction['address']}。最佳游览时间：{attraction['best_time']}。"
            f"建议停留：{attraction['duration_minutes']} 分钟。提示：{attraction['tips']}。"
        )
        chunks.extend(
            split_text(
                text,
                attraction["name"],
                "景点信息",
                {
                    "type": "attraction",
                    "scenic_area": attraction["scenic_area"],
                    "latitude": attraction["latitude"],
                    "longitude": attraction["longitude"],
                },
            )
        )

    routes = json.loads((DATA_DIR / "routes.json").read_text(encoding="utf-8"))
    for route in routes:
        stop_lines = []
        for stop in route["stops"]:
            stop_lines.append(
                f"{stop['name']}（到达第 {stop['offset_minutes']} 分钟，停留 {stop['duration_minutes']} 分钟）：{stop['description']}"
            )
        text = (
            f"【路线推荐】{route['title']}：{route['summary']}\n"
            f"默认开始时间 {route['default_start']}。行程：\n" + "\n".join(stop_lines)
        )
        scenic_areas = sorted({stop["scenic_area"] for stop in route["stops"]})
        chunks.extend(
            split_text(
                text,
                route["title"],
                "路线推荐",
                {"type": "route", "route_id": route["id"], "scenic_area": "|".join(scenic_areas)},
            )
        )
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="杭州智游知识库向量入库")
    parser.add_argument("--force", action="store_true", help="删除并重建集合")
    parser.add_argument("--append", action="store_true", help="追加到已有集合")
    args = parser.parse_args()

    client = milvus_store.get_client()
    if client.has_collection(milvus_store.config.COLLECTION_NAME) and args.force:
        client.drop_collection(milvus_store.config.COLLECTION_NAME)

    existing = milvus_store.collection_count()
    if existing > 0 and not args.force and not args.append:
        print(f"集合已有 {existing} 条数据，跳过入库。如需重建请加 --force，如需追加请加 --append。")
        return

    chunks = load_markdown_chunks() + load_json_chunks()
    print(f"共生成 {len(chunks)} 个文本块，开始向量化...")

    for start in range(0, len(chunks), 16):
        batch = chunks[start : start + 16]
        vectors = embeddings.embed_texts([item["text"] for item in batch])
        for item, vector in zip(batch, vectors):
            item["embedding"] = vector
        milvus_store.insert_chunks(batch)
        print(f"已入库 {min(start + 16, len(chunks))}/{len(chunks)}")

    print(f"入库完成，集合 {milvus_store.config.COLLECTION_NAME} 现有 {milvus_store.collection_count()} 条。")


if __name__ == "__main__":
    main()
