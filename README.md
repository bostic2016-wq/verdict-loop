# Verdict Loop

A free multi-model harness: **research → debate → verdict**, then optional **promo copy → image generation → vision QA**.

No paid OpenRouter required. Text uses free Groq + Gemini keys. Images use Pollinations Flux.

## What it does

1. **Scout** gathers structured research notes  
2. **Advocate** vs **Skeptic** argue  
3. **Judge** scores and may request another loop  
4. **Promoter** writes headline / blurb / image prompts  
5. **Image Gen** (Pollinations) creates images  
6. **Image Critic** (Gemini vision) scores quality and can force a regenerate  

Not for sports-bot work (by design). Use it on plans, launches, purchases, life decisions, etc.

## Setup

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

## Web UI

```bash
python web_app.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Config

Edit `config.yaml` to change models, pass scores, max rounds, and image sizes.

When you later want OpenRouter, set `OPENROUTER_API_KEY` and change a role’s model string to something like `openrouter/anthropic/claude-sonnet-4` — same router, no rewrite.

## Roles → models (defaults)

| Role | Model |
|------|--------|
| Scout | Groq Llama 3.3 70B |
| Advocate | Gemini 2.0 Flash |
| Skeptic | Groq Llama 3.1 8B |
| Judge | Gemini 2.0 Flash |
| Promoter | Gemini 2.0 Flash |
| Image Gen | Pollinations Flux |
| Image Critic | Gemini 2.0 Flash (vision) |
