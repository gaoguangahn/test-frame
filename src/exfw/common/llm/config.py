from dataclasses import dataclass


@dataclass
class LLMConfig:
    base_url: str = "http://10.163.5.71:8081/v1/chat/completions"
    model: str = "qwen3.5-27b-q5_k_m.gguf"
    temperature: float = 0.2
    top_p: float = 0.9
    max_tokens: int = 1024
    timeout: int = 300
