from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

import requests
from deep_translator import GoogleTranslator


class BaseTranslationClient(ABC):
    """Abstract interface for translation clients."""

    @abstractmethod
    def translate_lines(self, lines: List[str], source_lang: Optional[str], target_lang: str) -> List[str]:
        """Translate a list of lines into target_lang.

        Implementations should preserve the order and return exactly len(lines) results.
        On irrecoverable API errors, raise an Exception with a clear message.
        """
        raise NotImplementedError

    @abstractmethod
    def get_source_name(self) -> str:
        """Return the name of the translation source/client."""
        raise NotImplementedError


class GoogleTranslateClient(BaseTranslationClient):
    """Google Translate implementation using deep_translator."""

    def translate_lines(self, lines: List[str], source_lang: Optional[str], target_lang: str) -> List[str]:
        translator = GoogleTranslator(source=source_lang or "auto", target=target_lang)
        results: List[str] = []
        for text in lines:
            try:
                results.append(translator.translate(text))
            except Exception:
                # Graceful fallback to original line on error per-line
                results.append(text)
        # Ensure 1:1 mapping size
        if len(results) != len(lines):
            # Pad or trim as a last resort (should not happen here)
            if len(results) < len(lines):
                results.extend(lines[len(results):])
            else:
                results = results[: len(lines)]
        return results

    def get_source_name(self) -> str:
        """Return the name of the translation source."""
        return "Google Translate"


class OpenRouterClient(BaseTranslationClient):
    """OpenRouter LLM-based translation client using a single-request strategy.

    It sends the full lyrics in one prompt and instructs the LLM to return
    exactly the same number of lines, in order, separated by newlines.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        prompt_template: str,
        model_body: Optional[Dict[str, Any]] = None,
        base_url: str = "https://openrouter.ai/api/v1/chat/completions",
        app_title: str = "Spotify Lyrics Translator",
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.prompt_template = prompt_template
        self.model_body = model_body or {}
        self.base_url = base_url
        self.app_title = app_title

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Optional headers encouraged by OpenRouter
            "X-Title": self.app_title,
        }

    def _build_body(self, prompt_text: str) -> Dict[str, Any]:
        # Do not let user config override model/messages
        merged: Dict[str, Any] = {k: v for k, v in self.model_body.items() if k not in {"model", "messages"}}
        merged.update({
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt_text,
                }
            ],
        })
        return merged

    @staticmethod
    def _normalize_lines(output: str, expected_count: int, original_lines: List[str]) -> List[str]:
        # Split on newlines and strip trailing spaces
        lines = [l.rstrip("\r") for l in output.split("\n")]
        # Remove possible numbering or leading hyphens for simple robustness
        cleaned = []
        for l in lines:
            s = l.strip()
            if s.startswith(("- ", "* ")):
                s = s[2:].strip()
            # Remove simple numeric prefixes like "1. ", "1) "
            if len(s) >= 3 and (s[1:3] in {". ", ") "} and s[0].isdigit()):
                s = s[3:].strip()
            cleaned.append(s)

        if len(cleaned) == expected_count:
            return cleaned

        # Best-effort normalization: pad/truncate
        if len(cleaned) < expected_count:
            cleaned.extend(original_lines[len(cleaned):])
        else:
            cleaned = cleaned[:expected_count]
        return cleaned

    def translate_lines(self, lines: List[str], source_lang: Optional[str], target_lang: str) -> List[str]:
        if not self.api_key:
            raise ValueError("OpenRouter API key is missing. Please provide it in settings.")

        lyrics_text = "\n".join(lines)
        prompt_text = self.prompt_template.replace("{lyrics}", lyrics_text)
        if "{target_language}" in prompt_text:
            prompt_text = prompt_text.replace("{target_language}", target_lang)

        body = self._build_body(prompt_text)

        try:
            response = requests.post(self.base_url, headers=self._build_headers(), json=body, timeout=60)
        except Exception as e:
            raise RuntimeError(f"Failed to reach OpenRouter: {e}")

        if response.status_code >= 400:
            try:
                data = response.json()
                message = data.get("error", {}).get("message") or data.get("message") or response.text
            except Exception:
                message = response.text
            raise RuntimeError(f"OpenRouter error {response.status_code}: {message}")

        try:
            data = response.json()
        except Exception:
            raise RuntimeError("Invalid JSON response from OpenRouter.")

        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            raise RuntimeError("Unexpected OpenRouter response format.")

        return self._normalize_lines(content or "", expected_count=len(lines), original_lines=lines)

    def get_source_name(self) -> str:
        """Return the model name from the model string."""
        # Extract model name from format like "openai/gpt-4" -> "gpt-4"
        if "/" in self.model:
            return self.model.split("/")[-1]
        return self.model


# ----------- Utility: OpenRouter models discovery and display formatting -----------
def fetch_openrouter_models(api_key: str) -> List[Dict[str, Any]]:
    """Fetch available models from OpenRouter API.

    Returns a list of items with keys: id, context, pricing:{prompt, completion}, vision.
    """
    api_key = (api_key or "").strip()
    if not api_key:
        return []

    url = "https://openrouter.ai/api/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=30)
    except Exception:
        return []

    if resp.status_code >= 400:
        return []

    try:
        data = resp.json()
    except Exception:
        return []

    items = []
    for item in (data.get("data") or []):
        model_id = item.get("id") or item.get("canonical_slug") or ""
        if not model_id:
            continue

        # Context length: prefer top_provider.context_length, fallback to context_length
        tp = item.get("top_provider") or {}
        context = tp.get("context_length") or item.get("context_length")

        # Pricing can vary in structure; try common keys
        # OpenRouter returns per-token costs, convert to per-million-tokens for display
        pricing = item.get("pricing") or {}
        prompt_cost_raw = pricing.get("prompt") or pricing.get("input") or pricing.get("per_1m_prompt_tokens")
        completion_cost_raw = pricing.get("completion") or pricing.get("output") or pricing.get("per_1m_completion_tokens")

        # Convert per-token costs to per-million-token costs
        prompt_cost = None
        completion_cost = None
        if prompt_cost_raw is not None:
            try:
                prompt_cost = float(prompt_cost_raw) * 1000000
            except (ValueError, TypeError):
                prompt_cost = prompt_cost_raw
        if completion_cost_raw is not None:
            try:
                completion_cost = float(completion_cost_raw) * 1000000
            except (ValueError, TypeError):
                completion_cost = completion_cost_raw

        # Vision support if image modality present
        arch = item.get("architecture") or {}
        input_modalities = arch.get("input_modalities") or []
        vision = any(str(m).lower() == "image" for m in input_modalities)

        items.append({
            "id": model_id,
            "context": context,
            "pricing": {
                "prompt": prompt_cost,
                "completion": completion_cost,
            },
            "vision": vision,
        })

    return items


def _fmt_cost(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        # Many APIs return cost per 1M as a number in USD
        v = float(value)
        return f"${v:.2f}"
    except Exception:
        # If it's already a string or unexpected, pass through
        return str(value)


def format_model_display(model_info: Dict[str, Any]) -> str:
    """Return a human-friendly label for a model entry per spec.

    Format:
    {id} | Context: {context} | Cost per 1M tokens: Prompt: ${p}. Completion: ${c} | Vision Available
    (omit the trailing pipe if Vision not available)
    """
    model_id = model_info.get("id", "")
    context = model_info.get("context") or "N/A"
    pricing = model_info.get("pricing") or {}
    prompt_cost = _fmt_cost(pricing.get("prompt"))
    completion_cost = _fmt_cost(pricing.get("completion"))
    vision = bool(model_info.get("vision"))

    base = f"{model_id} | Context: {context} | Cost per 1M tokens: Prompt: {prompt_cost}. Completion: {completion_cost}"
    if vision:
        return base + " | Vision Available"
    return base

