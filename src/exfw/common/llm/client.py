import json
from collections.abc import Callable, Iterator
from typing import Any

import requests

from .config import LLMConfig
from .response import LLMResponse


class LLMClient:
    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()

    def chat(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        stream: bool = False,
        on_chunk: Callable[[str], None] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any | None = None,
    ) -> LLMResponse:
        """调用 LLM 对话。"""
        data = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_tokens": max_tokens or self.config.max_tokens,
            "stream": stream,
        }

        if tools is not None:
            data["tools"] = tools
        if tool_choice is not None:
            data["tool_choice"] = tool_choice

        try:
            resp = requests.post(
                self.config.base_url,
                json=data,
                stream=stream,
                timeout=self.config.timeout,
            )
            resp.raise_for_status()

            if not stream:
                obj = resp.json()
                text = obj["choices"][0]["message"].get("content", "")
                return LLMResponse(text=text, raw=obj)

            full_text = ""
            for chunk in self._iter_sse(resp):
                full_text += chunk
                if on_chunk:
                    on_chunk(chunk)

            return LLMResponse(text=full_text)

        except Exception as e:
            return LLMResponse(text="", error=str(e))

    def _iter_sse(self, response) -> Iterator[str]:
        buffer = b""
        for chunk in response.iter_content(chunk_size=1024):
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue

                text = line.decode("utf-8", errors="ignore")
                if not text.startswith("data: "):
                    continue

                payload = text[6:]
                if payload == "[DONE]":
                    return

                try:
                    obj = json.loads(payload)
                    delta = obj["choices"][0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue


if __name__ == "__main__":
    config = LLMConfig(
        base_url="http://10.163.5.71:8080/v1/chat/completions",
        model="qwen3.5-27b-q5_k_m.gguf",
        temperature=0.2,
        top_p=0.9,
        max_tokens=1024,
        timeout=300,
    )
    client = LLMClient(config)
    messages = [
        {"role": "system", "content": "你是一个简洁的助手。"},
        {"role": "user", "content": "你好"},
    ]

    resp = client.chat(
        messages=messages,
        stream=False,
        on_chunk=lambda chunk: print(chunk, end="", flush=True),
    )

    print("非流式结果：")
    print(resp)
