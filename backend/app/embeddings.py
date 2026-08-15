from openai import OpenAI

from . import config

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.SILICONFLOW_API_KEY, base_url=config.SILICONFLOW_BASE_URL)
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    response = get_client().embeddings.create(model=config.EMBEDDING_MODEL, input=texts)
    ordered = sorted(response.data, key=lambda item: item.index)
    return [item.embedding for item in ordered]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
