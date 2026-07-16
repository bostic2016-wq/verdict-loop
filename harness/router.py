from __future__ import annotations

import base64
import json
import re
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import litellm

# Hide litellm's red "Provider List" banners on soft-retried calls
litellm.suppress_debug_info = True


class ProviderError(RuntimeError):
    """User-facing provider failure (rate limits, auth, network)."""


def _friendly_provider_error(exc: Exception, role: str, model: str) -> ProviderError:
    msg = str(exc).lower()
    detail = str(exc)
    if any(x in msg for x in ("rate limit", "rate_limit", "429", "too many requests", "quota")):
        return ProviderError(
            f"Rate limited while running role '{role}' ({model}). "
            "Free tiers throttle bursts — wait a minute and try again. "
            "Partial results (if any) were saved under outputs/runs/."
        )
    if any(
        x in msg
        for x in ("503", "unavailable", "high demand", "overloaded", "capacity")
    ):
        return ProviderError(
            f"Model busy for role '{role}' ({model}). "
            "Free Gemini is under high demand — retry in a minute."
        )
    if any(x in msg for x in ("401", "403", "invalid api key", "authentication", "unauthorized")):
        return ProviderError(
            f"Auth failed for role '{role}' ({model}). "
            "Check OPENROUTER_API_KEY (or GROQ_API_KEY / GEMINI_API_KEY fallbacks) in .env."
        )
    return ProviderError(f"Provider error for role '{role}' ({model}): {detail}")


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        x in msg
        for x in (
            "429",
            "503",
            "rate limit",
            "unavailable",
            "high demand",
            "overloaded",
            "timeout",
            "temporarily",
            "402",
            "insufficient credits",
            "payment required",
        )
    )


def _retry_sleep_seconds(exc: Exception, attempt: int) -> float:
    """Short backoff, then fall over to the other free provider."""
    msg = str(exc)
    match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)\s*s", msg, re.IGNORECASE)
    if match:
        # Cap so the UI doesn't look frozen for minutes
        return min(max(float(match.group(1)) + 0.5, 2.0), 8.0)
    return float(3 * (attempt + 1))  # 3s, 6s, 9s max path before fallback


class ModelRouter:
    """Thin multi-model router: OpenRouter primary, free Groq/Gemini fallbacks."""

    def __init__(self, settings: dict[str, Any]):
        self.settings = settings
        self.models: dict[str, str] = settings.get("models", {})
        self.fallbacks: dict[str, str] = settings.get("fallback_models", {})
        self._last_call_at = 0.0
        self._pace_lock = threading.Lock()
        # LiteLLM reads GROQ_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY from environment.

    def model_for(self, role: str) -> str:
        if role not in self.models:
            raise KeyError(f"No model configured for role: {role}")
        return self.models[role]

    def _models_for_role(self, role: str) -> list[str]:
        models_to_try = [self.model_for(role)]
        fallback = self.fallbacks.get(role)
        if fallback and fallback not in models_to_try:
            models_to_try.append(fallback)
        return models_to_try

    def _pace(self) -> None:
        """Small gap between calls so free tiers don't see a burst."""
        with self._pace_lock:
            gap = 0.8
            now = time.time()
            wait = gap - (now - self._last_call_at)
            if wait > 0:
                time.sleep(wait)
            self._last_call_at = time.time()

    def _call(self, kwargs: dict[str, Any], *, json_mode: bool) -> str:
        self._pace()
        local = dict(kwargs)
        try:
            if json_mode:
                local["response_format"] = {"type": "json_object"}
            resp = litellm.completion(**local)
        except Exception:
            if json_mode:
                local.pop("response_format", None)
                resp = litellm.completion(**local)
            else:
                raise
        content = resp.choices[0].message.content or ""
        content = content.strip()
        if not content:
            raise RuntimeError("Empty model response")
        return content

    def _stream_call(self, kwargs: dict[str, Any]) -> Iterator[str]:
        self._pace()
        local = dict(kwargs)
        local["stream"] = True
        stream = litellm.completion(**local)
        yielded = False
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta
                text = getattr(delta, "content", None) or ""
            except Exception:
                text = ""
            if text:
                yielded = True
                yield text
        if not yielded:
            raise RuntimeError("Empty model stream")

    def _try_models(
        self,
        models_to_try: list[str],
        *,
        role: str,
        messages: list[dict[str, Any]],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str:
        last_exc: Exception | None = None
        for model in models_to_try:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            for attempt in range(2):
                try:
                    return self._call(kwargs, json_mode=json_mode)
                except Exception as exc:
                    last_exc = exc
                    msg = str(exc).lower()
                    if any(x in msg for x in ("402", "insufficient credits", "payment required")):
                        break
                    if _is_retryable(exc) and attempt < 1:
                        time.sleep(_retry_sleep_seconds(exc, attempt))
                        continue
                    break
        assert last_exc is not None
        raise _friendly_provider_error(last_exc, role, models_to_try[-1]) from last_exc

    def _try_models_stream(
        self,
        models_to_try: list[str],
        *,
        role: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> Iterator[str]:
        last_exc: Exception | None = None
        for model in models_to_try:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            for attempt in range(2):
                try:
                    yield from self._stream_call(kwargs)
                    return
                except Exception as exc:
                    last_exc = exc
                    msg = str(exc).lower()
                    if any(x in msg for x in ("402", "insufficient credits", "payment required")):
                        break
                    if _is_retryable(exc) and attempt < 1:
                        time.sleep(_retry_sleep_seconds(exc, attempt))
                        continue
                    break
        assert last_exc is not None
        raise _friendly_provider_error(last_exc, role, models_to_try[-1]) from last_exc

    def complete(
        self,
        role: str,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return self._try_models(
            self._models_for_role(role),
            role=role,
            messages=messages,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens or (2048 if json_mode else 1024),
        )

    def complete_messages(
        self,
        role: str,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> str:
        return self._try_models(
            self._models_for_role(role),
            role=role,
            messages=messages,
            json_mode=False,
            temperature=temperature,
            max_tokens=max_tokens or 1024,
        )

    def complete_model_messages(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        label: str | None = None,
        fallback: str | None = None,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> str:
        models_to_try = [model]
        if fallback and fallback not in models_to_try:
            models_to_try.append(fallback)
        return self._try_models(
            models_to_try,
            role=label or model,
            messages=messages,
            json_mode=False,
            temperature=temperature,
            max_tokens=max_tokens or 1024,
        )

    def complete_stream(
        self,
        role: str,
        system: str,
        user: str,
        *,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        yield from self._try_models_stream(
            self._models_for_role(role),
            role=role,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens or 1024,
        )

    def complete_messages_stream(
        self,
        role: str,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        yield from self._try_models_stream(
            self._models_for_role(role),
            role=role,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens or 1024,
        )

    def complete_model_messages_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        label: str | None = None,
        fallback: str | None = None,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        models_to_try = [model]
        if fallback and fallback not in models_to_try:
            models_to_try.append(fallback)
        yield from self._try_models_stream(
            models_to_try,
            role=label or model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens or 1024,
        )

    def complete_vision(
        self,
        role: str,
        system: str,
        user: str,
        image_path: Path,
        *,
        json_mode: bool = True,
        temperature: float = 0.2,
    ) -> str:
        mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]

        models_to_try = [self.model_for(role)]
        fallback = self.fallbacks.get(role)
        if fallback and fallback not in models_to_try:
            models_to_try.append(fallback)

        last_exc: Exception | None = None
        for model in models_to_try:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 1024,
            }
            for attempt in range(2):
                try:
                    return self._call(kwargs, json_mode=json_mode)
                except Exception as exc:
                    last_exc = exc
                    msg = str(exc).lower()
                    # Zero-credit OpenRouter: skip retries, jump to fallback model
                    if any(x in msg for x in ("402", "insufficient credits", "payment required")):
                        break
                    if _is_retryable(exc) and attempt < 1:
                        time.sleep(2 * (attempt + 1))
                        continue
                    break
        assert last_exc is not None
        raise _friendly_provider_error(last_exc, role, models_to_try[-1]) from last_exc


_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def parse_json(text: str) -> Any:
    text = (text or "").strip()
    if not text:
        raise ValueError("Could not parse JSON from empty model output")

    candidates: list[str] = [text]
    match = _JSON_FENCE.search(text)
    if match:
        candidates.append(match.group(1).strip())

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])

    # Always attempt a truncation repair from the first brace.
    if start >= 0:
        stub = text[start:].rstrip().rstrip(",")
        opens = stub.count("{") - stub.count("}")
        opens_b = stub.count("[") - stub.count("]")
        repaired = stub
        if repaired.count('"') % 2 == 1:
            repaired += '"'
        if opens_b > 0:
            repaired += "]" * opens_b
        if opens > 0:
            repaired += "}" * opens
        if repaired not in candidates:
            candidates.append(repaired)

    last_err: Exception | None = None
    for cand in candidates:
        try:
            return json.loads(cand)
        except Exception as exc:  # noqa: BLE001 — try next candidate
            last_err = exc
            continue
    raise ValueError(
        f"Could not parse JSON from model output ({len(text)} chars):\n{text[:800]}"
    ) from last_err
