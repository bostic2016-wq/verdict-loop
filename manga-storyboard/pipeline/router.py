"""LLM / vision router via LiteLLM → OpenRouter."""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import litellm

litellm.suppress_debug_info = True


class ProviderError(RuntimeError):
    pass


class DirectorRouter:
    def __init__(self, settings: dict[str, Any], run_dir: Path | None = None):
        self.settings = settings
        self.models = settings.get("models", {})
        self.fallbacks = settings.get("fallback_models", {})
        self.run_dir = run_dir

    def complete(
        self,
        role: str,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.4,
    ) -> str:
        model = self.models.get(role) or self.models.get("director")
        fallback = self.fallbacks.get(role) or self.fallbacks.get("director")
        candidates = [m for m in [model, fallback] if m]
        last_err: Exception | None = None
        for candidate in candidates:
            try:
                text = self._call(candidate, system, user, json_mode=json_mode, temperature=temperature)
                self._track(role, candidate, system + "\n" + user, text)
                return text
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                if not self._retryable(exc):
                    raise ProviderError(str(exc)) from exc
                time.sleep(2)
        raise ProviderError(f"All models failed for {role}: {last_err}")

    def complete_vision(
        self,
        role: str,
        system: str,
        user: str,
        image_paths: list[Path] | Path,
        *,
        json_mode: bool = True,
        temperature: float = 0.2,
    ) -> str:
        if isinstance(image_paths, Path):
            image_paths = [image_paths]
        model = self.models.get(role) or self.models.get("vision_critic") or self.models.get("director")
        content: list[dict[str, Any]] = [{"type": "text", "text": user}]
        for path in image_paths:
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                }
            )
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = litellm.completion(**kwargs)
            text = resp.choices[0].message.content or ""
            self._track(role, model, system + "\n" + user, text, images=len(image_paths))
            return text
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(str(exc)) from exc

    def _track(self, role: str, model: str, prompt: str, response: str, *, images: int = 0) -> None:
        if not self.run_dir:
            return
        try:
            from pipeline.tokens import record_llm_call

            # Vision calls: pad input estimate slightly for attached images
            extra = " " * (images * 800) if images else ""
            record_llm_call(
                self.run_dir,
                role=role,
                model=str(model),
                prompt_text=prompt + extra,
                response_text=response,
            )
        except Exception:  # noqa: BLE001 — usage must never break generation
            pass

    def _call(
        self,
        model: str,
        system: str,
        user: str,
        *,
        json_mode: bool,
        temperature: float,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = litellm.completion(**kwargs)
        return resp.choices[0].message.content or ""

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(x in msg for x in ("429", "503", "rate limit", "overloaded", "timeout", "unavailable"))
