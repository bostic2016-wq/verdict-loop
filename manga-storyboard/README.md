# Manga Storyboard (v5)

Local web app that turns a manga **transcript PDF** into storyboard panels — with optional **5-panel video** and a **token/cost usage** view.

**Flow:** Upload PDF → analyze → editable brief + gap questions → **5-panel pilot** → optional video clip → lock & continue.  
**Quality:** Creative bible → panel grammar → per-panel vision QA.  
**Style:** Built-in **JJK-inspired** / **HxH-inspired** aesthetic presets + your own character drawings as references.

## What's new in v5

- **Image model profiles** (sidebar):
  - `Nano Banana Pro → FLUX` (default, strong multi-reference fidelity)
  - `Seedream 4.5 → FLUX` (anime-focused OpenRouter model)
- **Optional 5-panel video**: toggle in the sidebar, then generate a short OpenRouter clip from the pilot panels
- **Run usage / token view**: estimated tokens, image counts, video counts, and rough USD cost per run
- Full-color panels by default; power auras only when the script calls for them; outfit consistency locked to character looks/refs

## Public demo (Streamlit Community Cloud)

Deploy as a **separate** app from Verdict Loop:

1. Repo: `bostic2016-wq/verdict-loop` (or your fork)
2. Main file: `manga-storyboard/app.py`
3. Custom subdomain: e.g. `manga-storyboard`
4. Secrets:

```toml
OPENROUTER_API_KEY = "sk-or-your-key"
# Optional: APP_PASSWORD = "pick-a-password"
```

Reboot the Streamlit app after each push so it picks up the new build stamp in the sidebar.

## Quick start (local)

```bash
cd manga-storyboard
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add OPENROUTER_API_KEY
streamlit run app.py
```

## API keys

| Key | Used for |
|-----|----------|
| `OPENROUTER_API_KEY` | Director LLM, vision QA, images, video |
| `GROQ_API_KEY` / `GEMINI_API_KEY` | Optional LLM fallbacks |

Use **Mock images** in the sidebar to test the workflow without image spend.

## Config highlights (`config.yaml`)

- `models.image_profile` / `models.image_profiles` — switch Nano Banana vs Seedream chains
- `video.enabled`, `video.model` (default `google/veo-3.1-lite`), duration / resolution
- `costs.*` — estimates used only for the usage display
- `vision_qa`, `pilot.panel_count`

## Project layout

```
manga-storyboard/
  app.py
  config.yaml
  pipeline/          # ingest, analyze, generate, video, tokens, QA, export
  styles/            # jjk_inspired, hxh_inspired
  library/           # uploaded drawings + remembered characters
  outputs/runs/      # panels, usage.json, optional video/
```

## Notes

- Style presets approximate battle-/adventure-shonen aesthetics via prompt language — they are **not** trained on copyrighted pages.
- Dialogue stays as captions under panels (not in-image bubbles).
- Video is **opt-in** and can take minutes; it costs OpenRouter video credits.
- Token counts are estimates unless the provider returns exact usage.
