# Verdict Loop

A multi-model harness: **research → debate → verdict**, then optional **promo / images**, plus **follow-up chat** with session memory.

**v3 defaults:** Brief answers, images off, expandable full debate, compare two plans, starter templates.

Runs on **OpenRouter** — one API key. Free Groq/Gemini keys act as fallback.

## Roles → models (current lineup)

| Role | Model | Provider |
|------|-------|----------|
| Scout | GPT-5 mini | OpenAI |
| Advocate | Grok 4.20 | xAI |
| Skeptic | GPT-5 mini | OpenAI |
| Judge | Claude Sonnet 5 | Anthropic |
| Promoter | Gemini 2.5 Flash | Google |
| Image Critic | Gemini 2.5 Flash (vision) | Google |
| Image Gen | FLUX.2 Pro | Black Forest Labs |

A full run (debate + 2 images) costs roughly **$0.05–0.15** in OpenRouter credits. Edit `config.yaml` to swap any role's model — no code changes needed.

## Public demo (Streamlit Community Cloud)

1. Go to [share.streamlit.io](https://share.streamlit.io/) and sign in with GitHub (`bostic2016-wq`)
2. **New app** → repo `bostic2016-wq/verdict-loop` → branch `main` → Main file `streamlit_app.py`
3. Under **Advanced settings → Secrets**, paste:

```toml
OPENROUTER_API_KEY = "sk-or-your-key"

# Optional free fallbacks
# GROQ_API_KEY = "your-groq-key"
# GEMINI_API_KEY = "your-gemini-key"

# Optional: lock the public page
# APP_PASSWORD = "pick-a-password"
```

4. Deploy — you'll get a public URL like `https://verdict-loop-….streamlit.app`

**Important:** anyone with that URL spends your OpenRouter credits. Set `APP_PASSWORD` if you share the link widely.

### Manga Storyboard (separate app / separate URL)

The manga tool lives in the same repo but must be deployed as a **second** Streamlit app so it does **not** reuse the Verdict Loop link:

1. [share.streamlit.io](https://share.streamlit.io/) → **Create app** (do not edit the Verdict Loop app)
2. Repository: `bostic2016-wq/verdict-loop`
3. Branch: `main`
4. Main file path: `manga-storyboard/app.py`
5. **Custom subdomain:** `manga-storyboard` → URL like `https://manga-storyboard.streamlit.app`
6. Secrets (same OpenRouter key; optional `FAL_KEY` / `APP_PASSWORD`)

```toml
OPENROUTER_API_KEY = "sk-or-your-key"
# FAL_KEY = "your-fal-key"
# APP_PASSWORD = "pick-a-password"
```

Mock image mode is the default in `manga-storyboard/config.yaml` until you set a real image backend.

## What it does

1. **Scout** gathers structured research notes
2. **Advocate** vs **Skeptic** argue (different model families so it isn't one model debating itself)
3. **Judge** scores and may request another loop
4. **Promoter** writes headline / blurb / image prompts
5. **Image Gen** (FLUX.2 Pro via OpenRouter, Pollinations fallback) creates images
6. **Image Critic** (vision) scores quality and can force a regenerate

Not for sports-bot work (by design). Use it on plans, launches, purchases, life decisions, etc.

## Local setup

```bash
cd "/Users/kevinbostic/Harness for opendoor "
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

- [OpenRouter](https://openrouter.ai/keys) → `OPENROUTER_API_KEY` (primary — powers text + images)
- Optional fallbacks: [Groq](https://console.groq.com/) → `GROQ_API_KEY`, [Google AI Studio](https://aistudio.google.com/apikey) → `GEMINI_API_KEY`
- Optional: Pollinations account key → `POLLINATIONS_API_KEY`

## CLI

```bash
python cli.py "Should I launch a weekend newsletter about city walks?"
python cli.py "Should I buy a used cargo bike for deliveries?" --no-images
python cli.py -f idea.txt --json
# Offline wiring check (no API keys):
python cli.py --dry-run "Should I launch a newsletter about neighborhood walks?"
```

Optional Scout material: `--context notes.txt` (links / pasted research).

Outputs land in `outputs/runs/<id>/` (`result.json`, `report.md`, `images/`).

## Local web UIs

```bash
# FastAPI UI
python web_app.py
# → http://127.0.0.1:8000

# Streamlit UI (same as public deploy)
streamlit run streamlit_app.py
```

## Config

Edit `config.yaml` to change models, pass scores, max rounds, and image sizes.

Model strings use LiteLLM format: `openrouter/<provider>/<model>` for OpenRouter (e.g. `openrouter/anthropic/claude-sonnet-5`), or `groq/...` / `gemini/...` for the free direct APIs. The image model uses OpenRouter's image API directly (e.g. `black-forest-labs/flux.2-pro`).
