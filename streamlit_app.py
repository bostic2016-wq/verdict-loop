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
        for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "POLLINATIONS_API_KEY", "APP_PASSWORD"):
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
    page_title="Verdict Loop",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,650&family=Sora:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
      :root {
        --ink: #101820;
        --muted: #5a6570;
        --paper: #eef3f1;
        --panel: rgba(255,255,255,0.82);
        --accent: #0b6e4f;
        --accent-deep: #084c37;
        --warn: #9a3412;
        --line: rgba(16,24,32,0.12);
      }
      html, body, [class*="css"]  {
        font-family: "Sora", sans-serif;
      }
      .stApp {
        background:
          radial-gradient(ellipse 70% 55% at 0% 0%, #cfe8df 0%, transparent 55%),
          radial-gradient(ellipse 60% 50% at 100% 10%, #d5e3f0 0%, transparent 50%),
          linear-gradient(165deg, #e8f0ec 0%, #eef3f1 45%, #e4ebe8 100%);
      }
      .block-container {
        max-width: 920px;
        padding-top: 1.5rem;
        padding-bottom: 3rem;
      }
      #MainMenu, footer { visibility: hidden; }
      .vl-hero {
        animation: rise 0.7s ease-out both;
        margin-bottom: 1.25rem;
      }
      .vl-brand {
        font-family: "Sora", sans-serif;
        font-size: 0.78rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: var(--accent);
        font-weight: 700;
        margin: 0 0 0.45rem;
      }
      .vl-title {
        font-family: "Fraunces", Georgia, serif;
        font-size: clamp(2rem, 4.5vw, 3rem);
        line-height: 1.08;
        color: var(--ink);
        margin: 0 0 0.65rem;
        font-weight: 650;
      }
      .vl-lede {
        color: var(--muted);
        font-size: 1.02rem;
        line-height: 1.55;
        max-width: 40rem;
        margin: 0;
      }
      .vl-panel {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 1.15rem 1.25rem 1.3rem;
        backdrop-filter: blur(10px);
        box-shadow: 0 18px 40px rgba(16,24,32,0.06);
        animation: rise 0.85s ease-out both;
      }
      .vl-verdict {
        border-radius: 18px;
        padding: 1.2rem 1.3rem;
        border: 1px solid var(--line);
        animation: rise 0.55s ease-out both;
        margin: 1rem 0;
      }
      .vl-verdict.do { background: linear-gradient(135deg, #d8f3e7, #eefaf4); }
      .vl-verdict.dont { background: linear-gradient(135deg, #fde8e4, #fff5f3); }
      .vl-verdict.only_if { background: linear-gradient(135deg, #e7eef8, #f4f7fc); }
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
        margin: 1rem 0 0.25rem;
      }
      .vl-step {
        background: rgba(255,255,255,0.55);
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 0.65rem 0.7rem;
        font-size: 0.78rem;
        color: var(--muted);
        animation: rise 0.9s ease-out both;
      }
      .vl-step strong {
        display: block;
        color: var(--ink);
        font-size: 0.82rem;
        margin-bottom: 0.15rem;
      }
      @media (max-width: 720px) {
        .vl-steps { grid-template-columns: 1fr 1fr; }
      }
      @keyframes rise {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
      }
      div.stButton > button {
        background: var(--accent) !important;
        color: #fff !important;
        border: 0 !important;
        border-radius: 12px !important;
        font-weight: 650 !important;
        padding: 0.65rem 1.15rem !important;
        transition: transform 0.15s ease, filter 0.15s ease !important;
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
        '<div class="vl-hero"><p class="vl-brand">Verdict Loop</p>'
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
          <p class="vl-brand">Verdict Loop</p>
          <h1 class="vl-title">Stress-test a plan.<br/>Then generate creatives.</h1>
          <p class="vl-lede">
            A multi-model red team for decisions — research, argue both sides,
            judge the case, then optionally ship promo copy and images.
          </p>
        </div>
        <div class="vl-steps">
          <div class="vl-step"><strong>1 · Scout</strong>Maps risks & unknowns</div>
          <div class="vl-step"><strong>2 · Debate</strong>Advocate vs Skeptic</div>
          <div class="vl-step"><strong>3 · Judge</strong>Do / don’t / only if</div>
          <div class="vl-step"><strong>4 · Creative</strong>Copy + image QA loop</div>
        </div>
        """,
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
        st.caption("Free-tier APIs · rate limits apply")

    missing = []
    if not os.getenv("GROQ_API_KEY"):
        missing.append("GROQ_API_KEY")
    if not os.getenv("GEMINI_API_KEY"):
        missing.append("GEMINI_API_KEY")
    if missing:
        st.warning(
            "Server secrets not configured yet: "
            + ", ".join(missing)
            + ". Add them in Streamlit Cloud → App settings → Secrets."
        )

    run = st.button("Run red team", type="primary", disabled=not claim.strip() or bool(missing))
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
