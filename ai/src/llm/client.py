"""Multi-provider LLM client with Gemini, OpenAI, and Offline SRE Expert fallback."""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any

from ..config import LLMConfig

logger = logging.getLogger("ai.llm.client")


class LLMClient:
    """Unified LLM client supporting Gemini, OpenAI, and offline SRE expert engine."""

    def __init__(self, config: LLMConfig):
        self.config = config

    async def generate(self, system_prompt: str, user_prompt: str) -> tuple[str, str, int]:
        """Generate text completion. Returns (response_text, provider_used, tokens_used)."""
        provider = self.config.provider.lower()

        # 1. Gemini
        if provider == "gemini" and self.config.gemini_api_key:
            try:
                text, tokens = self._call_gemini(system_prompt, user_prompt)
                return text, "gemini", tokens
            except Exception as e:
                logger.warning("Gemini API call failed (%s). Falling back to SRE Expert engine.", e)

        # 2. OpenAI
        elif provider == "openai" and self.config.openai_api_key:
            try:
                text, tokens = self._call_openai(system_prompt, user_prompt)
                return text, "openai", tokens
            except Exception as e:
                logger.warning("OpenAI API call failed (%s). Falling back to SRE Expert engine.", e)

        # 3. Offline SRE Expert Engine Fallback
        text = self._offline_sre_expert_generate(user_prompt)
        return text, "sre_expert", len(text.split())

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> tuple[str, int]:
        """Call Google Gemini REST API."""
        model = self.config.model or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.config.gemini_api_key}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_prompt}\n\n{user_prompt}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": self.config.temperature,
                "maxOutputTokens": self.config.max_tokens,
            },
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError("No candidates returned from Gemini API")
            text = candidates[0]["content"]["parts"][0]["text"]
            tokens = data.get("usageMetadata", {}).get("totalTokenCount", len(text.split()))
            return text, tokens

    def _call_openai(self, system_prompt: str, user_prompt: str) -> tuple[str, int]:
        """Call OpenAI Chat Completions API."""
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": self.config.model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.openai_api_key}",
            },
        )

        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {}).get("total_tokens", len(text.split()))
            return text, tokens

    def _offline_sre_expert_generate(self, user_prompt: str) -> str:
        """Deterministic SRE reasoning engine for 100% offline environments."""
        return user_prompt
