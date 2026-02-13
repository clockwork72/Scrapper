"""Small OpenAI JSON client for extraction and verification backends."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests


class OpenAIClientError(RuntimeError):
    pass


@dataclass
class OpenAIJSONClient:
    model: str = "gpt-4.1"
    api_key: str | None = None
    timeout_s: int = 90
    base_url: str = "https://api.openai.com/v1"

    def _api_key(self) -> str:
        key = self.api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise OpenAIClientError("OPENAI_API_KEY is missing")
        return key

    def complete_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout_s,
        )
        if resp.status_code >= 400:
            raise OpenAIClientError(f"OpenAI API error {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception as e:  # pragma: no cover
            raise OpenAIClientError(f"Unexpected OpenAI response shape: {e}") from e

        if not isinstance(content, str):
            raise OpenAIClientError("OpenAI response content is not a string")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise OpenAIClientError(f"Model returned non-JSON content: {e}") from e

        if not isinstance(parsed, dict):
            raise OpenAIClientError("Model JSON root must be an object")
        return parsed
