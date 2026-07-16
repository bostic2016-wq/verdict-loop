from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


class ImageClient:
    def __init__(self, settings: dict[str, Any], *, dry_run: bool = False):
        self.dry_run = dry_run
        self.base_url = settings.get("pollinations", {}).get(
            "base_url", "https://image.pollinations.ai/prompt"
        )
        self.model = settings.get("models", {}).get("image_model", "flux")
        self.api_key = settings["_env"].get("POLLINATIONS_API_KEY", "")
        creative = settings.get("creative", {})
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
            # Minimal valid JPEG so vision critic / UI can load a file offline.
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
        w = width or self.width
        h = height or self.height
        encoded = quote(prompt.strip(), safe="")
        url = (
            f"{self.base_url}/{encoded}"
            f"?width={w}&height={h}&model={self.model}&nologo=true&private=true"
        )
        if seed is not None:
            url += f"&seed={seed}"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        return dest