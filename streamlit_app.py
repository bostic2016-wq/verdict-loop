"""
Public Verdict Loop UI (Streamlit).
Deploy from GitHub via Streamlit Community Cloud for a shareable public URL.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Streamlit Cloud secrets → env (so harness.config / LiteLLM see them)
try:
    if hasattr(st, "secrets"):
        for key in (
            "GROQ_API_KEY",
            "GEMINI_API_KEY",
            "POLLINATIONS_API_KEY",
            "OPENROUTER_API_KEY",
            "APP_PASSWORD",
        ):
            try:
                val = st.secrets[key]
            except Exception:
                continue
            if val:
                os.environ[key] = str(val)
except Exception:
    pass

from harness.pipeline import run_pipeline  # noqa: E402

st.set_page_config(
    page_title="Verdict Loop v2",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
      :root {
        --ink: #0c1222;
        --muted: #5b6578;
        --paper: #e7ecf4;
        --panel: rgba(255,255,255,0.88);
        --accent: #1a6dff;
        --accent-deep: #0f4fcc;
        --warm: #f0a05a;
        --warn: #b42318;
        --line: rgba(12,18,34,0.10);
      }
      html, body, [class*="css"]  {
        font-family: "Manrope", sans-serif;
      }
      .stApp {
        background:
          radial-gradient(ellipse 55% 45% at 8% -5%, rgba(26,109,255,0.22) 0%, transparent 55%),
          radial-gradient(ellipse 50% 40% at 95% 5%, rgba(240,160,90,0.18) 0%, transparent 50%),
          radial-gradient(ellipse 40% 35% at 70% 90%, rgba(26,109,255,0.08) 0%, transparent 55%),
          linear-gradient(165deg, #e9eef7 0%, #f2f4f8 48%, #e6ebf3 100%);
        background-attachment: fixed;
      }
      .block-container {
        max-width: 940px;
        padding-top: 1.35rem;
        padding-bottom: 3rem;
      }
      #MainMenu, footer { visibility: hidden; }
      .vl-hero {
        animation: rise 0.7s ease-out both;
        margin-bottom: 1.1rem;
      }
      .vl-brand-row {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        flex-wrap: wrap;
        margin: 0 0 0.7rem;
      }
      .vl-brand {
        font-family: "Manrope", sans-serif;
        font-size: clamp(1.65rem, 3.2vw, 2.15rem);
        letter-spacing: -0.03em;
        color: var(--ink);
        font-weight: 800;
        margin: 0;
        line-height: 1;
      }
      .vl-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        font-size: 0.7rem;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        font-weight: 700;
        padding: 0.32rem 0.65rem;
        border-radius: 999px;
        background: linear-gradient(135deg, #1a6dff, #3b82f6);
        color: #fff;
        box-shadow: 0 6px 18px rgba(26,109,255,0.28);
        animation: pulse-soft 2.4s ease-in-out infinite;
      }
      .vl-title {
        font-family: "Instrument Serif", Georgia, serif;
        font-size: clamp(2.15rem, 5vw, 3.25rem);
        line-height: 1.05;
        color: var(--ink);
        margin: 0 0 0.7rem;
        font-weight: 400;
        letter-spacing: -0.02em;
      }
      .vl-title em {
        font-style: italic;
        color: var(--accent-deep);
      }
      .vl-lede {
        color: var(--muted);
        font-size: 1.05rem;
        line-height: 1.55;
        max-width: 38rem;
        margin: 0;
      }
      .vl-panel {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 20px;
        padding: 1.2rem 1.3rem 1.35rem;
        backdrop-filter: blur(12px);
        box-shadow: 0 22px 48px rgba(12,18,34,0.08);
        animation: rise 0.85s ease-out both;
      }
      .vl-verdict {
        border-radius: 18px;
        padding: 1.2rem 1.3rem;
        border: 1px solid var(--line);
        animation: rise 0.55s ease-out both;
        margin: 1rem 0;
      }
      .vl-verdict.do { background: linear-gradient(135deg, #d9f5e8, #eefaf4); }
      .vl-verdict.dont { background: linear-gradient(135deg, #fde8e4, #fff5f3); }
      .vl-verdict.only_if { background: linear-gradient(135deg, #e4ecfb, #f3f7fd); }
      .vl-badge {
        display: inline-block;
        font-size: 0.75rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        font-weight: 700;
        padding: 0.28rem 0.55rem;
        border-radius: 999px;
        background: var(--ink);
        color: #fff;
        margin-bottom: 0.55rem;
      }
      .vl-steps {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 0.55rem;
        margin: 1.15rem 0 0.35rem;
      }
      .vl-step {
        background: rgba(255,255,255,0.72);
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 0.7rem 0.75rem;
        font-size: 0.78rem;
        color: var(--muted);
        animation: rise 0.9s ease-out both;
        transition: transform 0.2s ease, border-color 0.2s ease;
      }
      .vl-step:hover {
        transform: translateY(-2px);
        border-color: rgba(26,109,255,0.35);
      }
      .vl-step strong {
        display: block;
        color: var(--ink);
        font-size: 0.84rem;
        margin-bottom: 0.15rem;
      }
      .vl-models {
        display: flex;
        flex-wrap: wrap;
        gap: 0.55rem;
        align-items: stretch;
        margin: 1rem 0 0.35rem;
        animation: rise 1s ease-out both;
      }
      .vl-models-label {
        font-size: 0.68rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: var(--muted);
        font-weight: 700;
        width: 100%;
        margin: 0 0 0.15rem;
      }
      .vl-model {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        color: var(--muted);
        background: rgba(255,255,255,0.78);
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 0.45rem 0.65rem;
        transition: transform 0.2s ease, border-color 0.2s ease;
      }
      .vl-model:hover {
        transform: translateY(-1px);
        border-color: rgba(26,109,255,0.4);
      }
      .vl-model svg {
        width: 18px;
        height: 18px;
        flex: none;
        opacity: 0.9;
      }
      .vl-model-name {
        font-size: 0.78rem;
        font-weight: 700;
        color: var(--ink);
        line-height: 1.15;
        display: block;
      }
      .vl-model-role {
        font-size: 0.68rem;
        color: var(--muted);
        line-height: 1.15;
        display: block;
      }
      @media (max-width: 720px) {
        .vl-steps { grid-template-columns: 1fr 1fr; }
      }
      @keyframes rise {
        from { opacity: 0; transform: translateY(12px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes pulse-soft {
        0%, 100% { box-shadow: 0 6px 18px rgba(26,109,255,0.28); }
        50% { box-shadow: 0 8px 26px rgba(26,109,255,0.42); }
      }
      div.stButton > button {
        background: linear-gradient(135deg, #1a6dff, #0f4fcc) !important;
        color: #fff !important;
        border: 0 !important;
        border-radius: 14px !important;
        font-weight: 700 !important;
        padding: 0.7rem 1.25rem !important;
        transition: transform 0.15s ease, filter 0.15s ease !important;
        box-shadow: 0 10px 24px rgba(26,109,255,0.28) !important;
      }
      div.stButton > button:hover {
        filter: brightness(1.06);
        transform: translateY(-1px);
      }
      textarea {
        border-radius: 12px !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def _gate() -> bool:
    password = (os.getenv("APP_PASSWORD") or "").strip()
    if not password:
        return True
    if st.session_state.get("authed"):
        return True
    st.markdown(
        '<div class="vl-hero"><div class="vl-brand-row">'
        '<p class="vl-brand">Verdict Loop</p>'
        '<span class="vl-chip">v2 · OpenRouter</span></div>'
        '<h1 class="vl-title">Enter to continue</h1>'
        "<p class=\"vl-lede\">This public demo is password-protected.</p></div>",
        unsafe_allow_html=True,
    )
    entered = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Password")
    if st.button("Enter") and entered == password:
        st.session_state["authed"] = True
        st.rerun()
    if entered:
        st.error("Wrong password")
    return False


_LOGO_DIR = Path(__file__).resolve().parent / "web" / "static" / "logos"

# provider logo file, provider name, role caption — mirrors the config.yaml lineup
_MODEL_STRIP = (
    ("openai", "OpenAI", "Scout + Skeptic · GPT-5 mini"),
    ("xai", "xAI", "Advocate · Grok 4.20"),
    ("anthropic", "Anthropic", "Judge · Claude Sonnet 5"),
    ("google", "Google", "Promo + Critic · Gemini 2.5 Flash"),
    ("bfl", "Black Forest Labs", "Images · FLUX.2 Pro"),
)


def _model_strip_html() -> str:
    items = []
    for logo, provider, role in _MODEL_STRIP:
        try:
            svg = (_LOGO_DIR / f"{logo}.svg").read_text(encoding="utf-8")
        except OSError:
            svg = ""
        items.append(
            '<div class="vl-model">'
            + svg
            + f'<span><span class="vl-model-name">{provider}</span>'
            + f'<span class="vl-model-role">{role}</span></span></div>'
        )
    return (
        '<div class="vl-models">'
        '<p class="vl-models-label">Model roster · OpenRouter edition</p>'
        + "".join(items)
        + "</div>"
    )


def _verdict_class(rec: str) -> str:
    rec = (rec or "").lower().replace("-", "").replace(" ", "")
    if rec in {"do", "go", "yes"}:
        return "do"
    if rec in {"dont", "don't", "no"}:
        return "dont"
    return "only_if"


def main() -> None:
    if not _gate():
        return

    st.markdown(
        """
        <div class="vl-hero">
          <div class="vl-brand-row">
            <p class="vl-brand">Verdict Loop</p>
            <span class="vl-chip">v2 · OpenRouter</span>
          </div>
          <h1 class="vl-title">Stress-test a plan.<br/><em>Then ship creatives.</em></h1>
          <p class="vl-lede">
            A multi-model red team — research, argue both sides, judge the case,
            then optionally generate promo copy and images through OpenRouter.
          </p>
        </div>
        <div class="vl-steps">
          <div class="vl-step"><strong>1 · Scout</strong>Maps risks & unknowns</div>
          <div class="vl-step"><strong>2 · Debate</strong>Advocate vs Skeptic</div>
          <div class="vl-step"><strong>3 · Judge</strong>Do / don’t / only if</div>
          <div class="vl-step"><strong>4 · Creative</strong>Copy + image QA loop</div>
        </div>
        """
        + _model_strip_html(),
        unsafe_allow_html=True,
    )

    st.markdown('<div class="vl-panel">', unsafe_allow_html=True)
    claim = st.text_area(
        "Your plan or claim",
        height=150,
        placeholder="e.g. Should I launch a weekend newsletter about city walks for local businesses?",
        label_visibility="visible",
    )
    c1, c2 = st.columns([2, 1])
    with c1:
        with_images = st.checkbox("Also run promo + image loop", value=True)
    with c2:
        st.caption("v2 · OpenRouter models")

    missing = []
    has_openrouter = bool(os.getenv("OPENROUTER_API_KEY"))
    if not has_openrouter:
        if not os.getenv("GROQ_API_KEY"):
            missing.append("GROQ_API_KEY")
        if not os.getenv("GEMINI_API_KEY"):
            missing.append("GEMINI_API_KEY")
        if missing:
            st.warning(
                "Add **OPENROUTER_API_KEY** (preferred) or "
                + " + ".join(missing)
                + " in Streamlit Cloud → Settings → Secrets."
            )
    else:
        st.caption("OpenRouter key detected")
        missing = []  # keys ok

    run = st.button(
        "Run Verdict Loop v2",
        type="primary",
        disabled=not claim.strip() or (not has_openrouter and bool(
            (not os.getenv("GROQ_API_KEY")) or (not os.getenv("GEMINI_API_KEY"))
        )),
    )
    st.markdown("</div>", unsafe_allow_html=True)

    if run:
        progress = st.progress(0, text="Starting…")
        status = st.empty()

        def on_progress(event: str, payload: dict) -> None:
            labels = {
                "scout_start": ("Researching…", 0.12),
                "advocate_start": ("Building the case for…", 0.28),
                "skeptic_start": ("Stress-testing the plan…", 0.42),
                "judge_start": ("Judging the debate…", 0.55),
                "promoter_start": ("Writing promo…", 0.68),
                "image_gen_start": ("Generating images…", 0.8),
                "image_critic_start": ("QA-checking images…", 0.9),
                "run_done": ("Done", 1.0),
            }
            if event in labels:
                text, pct = labels[event]
                progress.progress(pct, text=text)
                status.caption(text)

        with st.spinner("Running the loop — usually 1–3 minutes…"):
            try:
                result = run_pipeline(
                    claim.strip(),
                    with_images=with_images,
                    on_progress=on_progress,
                )
            except Exception as exc:
                progress.empty()
                st.error(str(exc))
                return
        progress.progress(1.0, text="Done")
        st.session_state["last_result"] = result

    result = st.session_state.get("last_result")
    if not result:
        return

    verdict = result["debate"]["verdict"]
    rec = str(verdict.get("recommendation") or "only_if")
    st.markdown(
        f"""
        <div class="vl-verdict {_verdict_class(rec)}">
          <div class="vl-badge">{rec} · score {verdict.get('score')}</div>
          <div style="font-family:Fraunces,Georgia,serif;font-size:1.35rem;margin-bottom:0.4rem;">Verdict</div>
          <div style="color:#334155;line-height:1.5;">{verdict.get('reasoning') or ''}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    conditions = verdict.get("conditions") or []
    if conditions:
        st.markdown("**Only proceed if**")
        for c in conditions:
            st.markdown(f"- {c}")

    st.markdown("### Debate transcript")
    for rnd in result["debate"]["rounds"]:
        with st.expander(
            f"Round {rnd['round']} — judge score {rnd['judgment'].get('score')}",
            expanded=(rnd["round"] == len(result["debate"]["rounds"])),
        ):
            left, right = st.columns(2)
            with left:
                st.markdown("**Advocate**")
                st.write(rnd["advocate"])
            with right:
                st.markdown("**Skeptic**")
                st.write(rnd["skeptic"])

    creative = result.get("creative")
    if creative:
        promo = creative.get("promo") or {}
        st.markdown("### Promo pack")
        st.markdown(f"#### {promo.get('headline') or 'Promo'}")
        st.caption(promo.get("tagline") or "")
        st.write(promo.get("promo_blurb") or "")
        run_dir = Path(result["run_dir"])
        approved = creative.get("approved") or []
        if approved:
            cols = st.columns(min(2, len(approved)))
            for i, asset in enumerate(approved):
                img_path = run_dir / asset["path"]
                with cols[i % len(cols)]:
                    if img_path.exists():
                        st.image(
                            str(img_path),
                            caption=f"{asset.get('purpose')} · score {asset.get('critique', {}).get('score')}",
                            use_container_width=True,
                        )


if __name__ == "__main__":
    main()
