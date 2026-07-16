from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


class ImageClient:
    def __init__(self, settings: dict[str, Any], *, dry_run: bool = False):
        self.dry_run = dry_run
        self.settings = settings
        creative = settings.get("creative", {})
        self.provider = (creative.get("image_provider") or "pollinations").lower()
        self.openrouter_key = settings["_env"].get("OPENROUTER_API_KEY", "")
        if self.provider == "openrouter" and not self.openrouter_key:
            self.provider = "pollinations"
        self.base_url = settings.get("pollinations", {}).get(
            "base_url", "https://image.pollinations.ai/prompt"
        )
        self.openrouter_url = settings.get("openrouter", {}).get(
            "image_url", "https://openrouter.ai/api/v1/images"
        )
        self.model = settings.get("models", {}).get("image_model", "flux")
        self.pollinations_key = settings["_env"].get("POLLINATIONS_API_KEY", "")
        self.width = int(creative.get("width", 1024))
        self.height = int(creative.get("height", 1024))

    def generate(
        self,
        prompt: str,
        dest: Path,
        *,
        width: int | None = None,
        height: int | None = None,
        seed: int | None = None,
    ) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self.dry_run:
            dest.write_bytes(
                bytes.fromhex(
                    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707"
                    "070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c"
                    "1c2837292c30313434341f27393d38323c2e333432ffdb0043010909090c0b0c180d"
                    "0d1832211c2132323232323232323232323232323232323232323232323232323232"
                    "323232323232323232323232323232323232323232ffc00011080001000103011100"
                    "021101031101ffc40014000100000000000000000000000000000000ffc400141001"
                    "00000000000000000000000000000000ffda000c0301000210031000003f00bf8000"
                    "00ffd9"
                )
            )
            return dest

        if self.provider == "openrouter":
            try:
                return self._generate_openrouter(prompt, dest, seed=seed)
            except Exception:
                # Fall back to free Pollinations if OpenRouter image fails
                return self._generate_pollinations(
                    prompt, dest, width=width, height=height, seed=seed
                )
        return self._generate_pollinations(
            prompt, dest, width=width, height=height, seed=seed
        )

    def _generate_openrouter(
        self,
        prompt: str,
        dest: Path,
        *,
        seed: int | None = None,
    ) -> Path:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt.strip(),
            "aspect_ratio": "1:1",
            "output_format": "jpeg",
        }
        if seed is not None:
            payload["seed"] = seed
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/bostic2016-wq/verdict-loop",
            "X-Title": "Verdict Loop",
        }
        with httpx.Client(timeout=180.0) as client:
            resp = client.post(self.openrouter_url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        images = data.get("data") or []
        if not images or not images[0].get("b64_json"):
            raise RuntimeError(f"OpenRouter image response missing data: {data}")
        dest.write_bytes(base64.b64decode(images[0]["b64_json"]))
        return dest

    def _generate_pollinations(
        self,
        prompt: str,
        dest: Path,
        *,
        width: int | None = None,
        height: int | None = None,
        seed: int | None = None,
    ) -> Path:
        w = width or self.width
        h = height or self.height
        # Pollinations model names are short (flux); OpenRouter ids are not.
        model = self.model if "/" not in self.model else "flux"
        encoded = quote(prompt.strip(), safe="")
        url = (
            f"{self.base_url}/{encoded}"
            f"?width={w}&height={h}&model={model}&nologo=true&private=true"
        )
        if seed is not None:
            url += f"&seed={seed}"
        headers = {}
        if self.pollinations_key:
            headers["Authorization"] = f"Bearer {self.pollinations_key}"
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        return dest
