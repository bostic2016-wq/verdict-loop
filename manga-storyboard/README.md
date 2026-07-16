# Manga Storyboard

Local web app that turns a manga **transcript PDF** into storyboard panels.

**Flow:** Upload PDF → analyze → editable brief + gap questions → **5-panel pilot** → lock & continue.  
**Quality:** Creative bible → panel grammar → per-panel vision QA → sequence editorial read.  
**Style:** Built-in **JJK-inspired** / **HxH-inspired** aesthetic presets (legal prompt packs — not copyrighted training data) + your own drawings as references.

## Public demo (Streamlit Community Cloud) — separate app / URL

This app is deployed **separately** from Verdict Loop so it gets its own `*.streamlit.app` link.

### Deploy (one-time)

1. Push this folder to GitHub as its own repo (recommended), e.g. `bostic2016-wq/manga-storyboard`
2. Go to [share.streamlit.io](https://share.streamlit.io/) → **Create app**
3. Settings:
   - Repository: `bostic2016-wq/manga-storyboard`
   - Branch: `main`
   - Main file: `app.py`
   - **Custom subdomain:** `manga-storyboard` (or any free name) → URL like `https://manga-storyboard.streamlit.app`
4. **Advanced → Secrets** paste:

```toml
OPENROUTER_API_KEY = "sk-or-your-key"

# Optional image gen
# FAL_KEY = "your-fal-key"

# Optional: lock the public page
# APP_PASSWORD = "pick-a-password"
```

5. Deploy

**Do not** point this deploy at Verdict Loop’s `streamlit_app.py` — that would reuse/replace the other app’s link.

### Alternate: same monorepo, different entrypoint

If the code lives under `verdict-loop/manga-storyboard/`:

- Main file path: `manga-storyboard/app.py`
- Custom subdomain: still set to something like `manga-storyboard` so the URL stays separate from Verdict Loop

## Quick start (local)

```bash
cd manga-storyboard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add OPENROUTER_API_KEY (required for analysis / QA)
# Optional: FAL_KEY for real images — or check "Mock images" in the sidebar
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`).

## API keys

| Key | Used for |
|-----|----------|
| `OPENROUTER_API_KEY` | Director LLM (Claude) + vision QA |
| `FAL_KEY` | Image generation (Fal). Optional if you use **Mock images** |
| `GROQ_API_KEY` / `GEMINI_API_KEY` | Optional fallbacks |

Without image keys, enable **Mock images** in the sidebar to test the full workflow with placeholder panels.

## Config

See [`config.yaml`](config.yaml):

- `models.director` / `models.vision_critic`
- `models.image_backend`: `fal_illustrious` | `openrouter_gpt_image` | `mock`
- `vision_qa.pass_score` / `max_retries`
- `pilot.panel_count` (default 5)

Style presets live in [`styles/`](styles/) (`jjk_inspired.yaml`, `hxh_inspired.yaml`).

## Project layout

```
manga-storyboard/
  app.py                 # Streamlit UI
  config.yaml
  pipeline/              # ingest, analyze, bible, grammar, generate, QA, export
  styles/                # aesthetic presets
  library/               # your uploaded drawings
  outputs/runs/          # each run's panels + JSON
```

## Notes

- We do **not** ship models trained on official JJK / Hunter × Hunter pages (copyright). Presets approximate those aesthetics via prompt/settings language.
- Dialogue appears as **captions under panels** (not in-image speech bubbles) in V1.
- Exports are clean PNGs — no score overlays baked into the art.
