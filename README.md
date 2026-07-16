# Verdict Loop

A free multi-model harness: **research → debate → verdict**, then optional **promo copy → image generation → vision QA**.

No paid OpenRouter required. Text uses free Groq + Gemini keys. Images use Pollinations Flux.

## Public demo (like a hosted tool)

Your site-builder demos are static pages on GitHub Pages. Verdict Loop needs a live server, so we host the **usable app** with [Streamlit Community Cloud](https://share.streamlit.io/) (free, connects to this GitHub repo).

1. Go to [share.streamlit.io](https://share.streamlit.io/) and sign in with GitHub (`bostic2016-wq`)
2. **New app** → repo `bostic2016-wq/verdict-loop` → branch `main` → Main file `streamlit_app.py`
3. Under **Advanced settings → Secrets**, paste:

```toml
GROQ_API_KEY = "your-groq-key"
GEMINI_API_KEY = "your-gemini-key"
# Optional: lock the public page
# APP_PASSWORD = "pick-a-password"
```

4. Deploy — you’ll get a public URL like `https://verdict-loop-….streamlit.app`

**Important:** anyone with that URL can burn your free API quota. Use `APP_PASSWORD` if you share the link widely.

## What it does

1. **Scout** gathers structured research notes  
2. **Advocate** vs **Skeptic** argue  
3. **Judge** scores and may request another loop  
4. **Promoter** writes headline / blurb / image prompts  
5. **Image Gen** (Pollinations) creates images  
6. **Image Critic** (Gemini vision) scores quality and can force a regenerate  

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

- [Groq](https://console.groq.com/) → `GROQ_API_KEY`
- [Google AI Studio](https://aistudio.google.com/apikey) → `GEMINI_API_KEY`
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

When you later want OpenRouter, set `OPENROUTER_API_KEY` and change a role’s model string to something like `openrouter/anthropic/claude-sonnet-4` — same router, no rewrite.

## Roles → models (defaults)

| Role | Model |
|------|--------|
| Scout | Groq Llama 3.3 70B |
| Advocate | Gemini Flash (latest) |
| Skeptic | Groq Llama 3.1 8B |
| Judge | Groq Llama 3.3 70B |
| Promoter | Gemini Flash (latest) |
| Image Gen | Pollinations Flux |
| Image Critic | Gemini Flash (vision) |
