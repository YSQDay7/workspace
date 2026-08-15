from openai import OpenAI

from . import config

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL)
    return _client


def chat(messages: list[dict], temperature: float = 0.3, max_tokens: int = 1400, json_mode: bool = False) -> str:
    kwargs: dict = {"temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = get_client().chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=messages,
        **kwargs,
    )
    return response.choices[0].message.content or ""


def chat_stream(messages: list[dict], temperature: float = 0.3, max_tokens: int = 1400):
    kwargs: dict = {"temperature": temperature, "max_tokens": max_tokens}
    response = get_client().chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=messages,
        stream=True,
        **kwargs,
    )
    for chunk in response:
        if chunk.choices:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content


def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    temperature: float = 0.1,
    max_tokens: int = 300,
) -> tuple[str, list[str]]:
    response = get_client().chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=messages,
        tools=tools,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    message = response.choices[0].message
    tool_calls = getattr(message, "tool_calls", None) or []
    names = [call.function.name for call in tool_calls]
    return message.content or "", names
