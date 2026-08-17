"""LLM integration for the Mentor backend (currently Groq)."""

from backend.llm.client import DEFAULT_MODEL, generate_reply

__all__ = ["DEFAULT_MODEL", "generate_reply"]
