"""
LLM 設定の一元管理。
OLLAMA_BASE_URL / OLLAMA_MODEL を .env で上書き可能。
"""
import os

from crewai import LLM

_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "ollama/qwen2.5:7b")


def get_llm() -> LLM:
    """Ollama LLM インスタンスを返す。"""
    return LLM(model=_OLLAMA_MODEL, base_url=_OLLAMA_BASE_URL)
