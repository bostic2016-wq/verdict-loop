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

from harness.pipeline import run_compare, run_pipeline  # noqa: E402
from harness.templates import claim_for_label, template_labels  # noqa: E402

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
        --ink: #0e1218;
        --muted: #5c6675;
        --paper: #e8ebf0;
        --panel: rgba(255,255,255,0.9);
        --accent: #0f9d8a;
        --accent-deep: #0b7a6b;
        --signal: #0f9d8a;
        --warn: #b42318;
        --line: rgba(14,18,24,0.10);
      }
      html, body, [class*="css"]  {
        font-family: "Manrope", sans-serif;
      }
      .stApp {
        background:
          radial-gradient(ellipse 58% 46% at 0% 0%, rgba(15,157,138,0.22) 0%, transparent 55%),
          radial-gradient(ellipse 50% 40% at 100% 5%, rgba(30,58,95,0.14) 0%, transparent 50%),
          radial-gradient(ellipse 40% 35% at 60% 100%, rgba(15,157,138,0.08) 0%, transparent 55%),
          linear-gradient(168deg, #e6eaef 0%, #eef1f4 48%, #e2e7ed 100%);
        background-attachment: fixed;
      }
      .block-container {
        max-width: 940px;
        padding-top: 1.2rem;
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
        margin: 0 0 0.55rem;
      }
      .vl-brand {
        font-family: "Manrope", sans-serif;
        font-size: clamp(1.7rem, 3.4vw, 2.25rem);
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
        font-size: 0.72rem;
        letter-spacing: 0.07em;
        text-transform: uppercase;
        font-weight: 800;
        padding: 0.38rem 0.75rem;
        border-radius: 999px;
        background: linear-gradient(135deg, #0f9d8a, #0b7a6b);
        color: #fff;
        box-shadow: 0 8px 22px rgba(15,157,138,0.35);
        animation: pulse-soft 2.2s ease-in-out infinite;
      }
      .vl-banner {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        margin: 0 0 0.85rem;
        padding: 0.45rem 0.8rem;
        border-radius: 12px;
        background: rgba(15,157,138,0.12);
        border: 1px solid rgba(15,157,138,0.28);
        color: var(--accent-deep);
        font-size: 0.82rem;
        font-weight: 650;
        animation: rise 0.55s ease-out both;
      }
      .vl-banner strong {
        color: var(--ink);
        letter-spacing: 0.04em;
        text-transform: uppercase;
        font-size: 0.72rem;
      }
      .vl-title {
        font-family: "Instrument Serif", Georgia, serif;
        font-size: clamp(2.2rem, 5.2vw, 3.35rem);
        line-height: 1.04;
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
        box-shadow: 0 22px 48px rgba(14,18,24,0.08);
        animation: rise 0.85s ease-out both;
      }
      .vl-verdict {
        border-radius: 18px;
        padding: 1.2rem 1.3rem;
        border: 1px solid var(--line);
        animation: rise 0.55s ease-out both;
        margin: 1rem 0;
      }
      .vl-verdict.do { background: linear-gradient(135deg, #d5f3ea, #eefaf6); }
      .vl-verdict.dont { background: linear-gradient(135deg, #fde8e4, #fff5f3); }
      .vl-verdict.only_if { background: linear-gradient(135deg, #e4eef5, #f2f7fb); }
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
        background: rgba(255,255,255,0.78);
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
        border-color: rgba(15,157,138,0.45);
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
        background: rgba(255,255,255,0.85);
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 0.45rem 0.65rem;
        transition: transform 0.2s ease, border-color 0.2s ease;
      }
      .vl-model:hover {
        transform: translateY(-1px);
        border-color: rgba(15,157,138,0.45);
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
        0%, 100% { box-shadow: 0 8px 22px rgba(15,157,138,0.3); }
        50% { box-shadow: 0 10px 28px rgba(15,157,138,0.48); }
      }
      div.stButton > button {
        background: linear-gradient(135deg, #0f9d8a, #0b7a6b) !important;
        color: #fff !important;
        border: 0 !important;
        border-radius: 14px !important;
        font-weight: 700 !important;
        padding: 0.7rem 1.25rem !important;
        transition: transform 0.15s ease, filter 0.15s ease !important;
        box-shadow: 0 10px 24px rgba(15,157,138,0.3) !important;
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
        '<span class="vl-chip">v3 · Brief + Memory</span></div>'
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
        '<p class="vl-models-label">Model roster · OpenRouter</p>'
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


def _render_verdict_card(result: dict, *, title: str = "Bottom line") -> None:
    debate = result.get("debate") or {}
    verdict = debate.get("verdict") or {}
    rec = str(verdict.get("recommendation") or "only_if")
    bottom = verdict.get("bottom_line") or verdict.get("reasoning") or ""
    st.markdown(
        f"""
        <div class="vl-verdict {_verdict_class(rec)}">
          <div class="vl-badge">{rec} · score {verdict.get('score')}</div>
          <div style="font-family:Instrument Serif,Georgia,serif;font-size:1.4rem;margin-bottom:0.35rem;">{title}</div>
          <div style="color:#334155;line-height:1.5;font-size:1.05rem;">{bottom}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    conditions = verdict.get("conditions") or []
    if conditions:
        st.markdown("**Only proceed if**")
        for c in conditions[:3]:
            st.markdown(f"- {c}")


def _render_debate(result: dict, *, detail: str) -> None:
    debate = result.get("debate") or {}
    rounds = debate.get("rounds") or []
    if not rounds:
        return
    expanded = detail == "detailed"
    label = "Full debate" if detail == "brief" else "Debate transcript"
    with st.expander(label, expanded=expanded):
        notes = debate.get("final_notes") or {}
        if notes.get("summary"):
            st.caption("Research summary")
            st.write(notes.get("summary"))
        for rnd in rounds:
            st.markdown(
                f"**Round {rnd['round']}** — judge score {rnd['judgment'].get('score')}"
            )
            left, right = st.columns(2)
            with left:
                st.markdown("**Advocate**")
                st.write(rnd["advocate"])
            with right:
                st.markdown("**Skeptic**")
                st.write(rnd["skeptic"])


def _render_creative(result: dict) -> None:
    creative = result.get("creative")
    if not creative:
        return
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
                        caption=(
                            f"{asset.get('purpose')} · "
                            f"score {asset.get('critique', {}).get('score')}"
                        ),
                        use_container_width=True,
                    )


def _keys_ok() -> bool:
    if os.getenv("OPENROUTER_API_KEY"):
        return True
    return bool(os.getenv("GROQ_API_KEY") and os.getenv("GEMINI_API_KEY"))


def main() -> None:
    if not _gate():
        return

    st.markdown(
        """
        <div class="vl-hero">
          <div class="vl-brand-row">
            <p class="vl-brand">Verdict Loop</p>
            <span class="vl-chip">v3 · Brief + Memory</span>
          </div>
          <div class="vl-banner"><strong>New</strong> Brief answers · Compare plans · Follow-up chat</div>
          <h1 class="vl-title">Stress-test a plan.<br/><em>Ask follow-ups.</em></h1>
          <p class="vl-lede">
            Brief by default. Compare two plans. Keep chatting about the verdict
            with session memory — no wall of text unless you ask for Detailed.
          </p>
        </div>
        <div class="vl-steps">
          <div class="vl-step"><strong>1 · Scout</strong>Maps risks & unknowns</div>
          <div class="vl-step"><strong>2 · Debate</strong>Advocate vs Skeptic</div>
          <div class="vl-step"><strong>3 · Judge</strong>Do / don’t / only if</div>
          <div class="vl-step"><strong>4 · Follow-up</strong>Ask about the answer</div>
        </div>
        """
        + _model_strip_html(),
        unsafe_allow_html=True,
    )

    st.markdown('<div class="vl-panel">', unsafe_allow_html=True)

    mode = st.radio(
        "Mode",
        ["Single", "Compare"],
        horizontal=True,
        index=0,
    )
    detail_label = st.radio(
        "Response length",
        ["Brief", "Detailed"],
        horizontal=True,
        index=0,
        help="Brief is short and scannable. Detailed shows the full debate.",
    )
    detail = "detailed" if detail_label == "Detailed" else "brief"

    labels = template_labels()
    tmpl = st.selectbox("Starter template", labels, index=0)
    if "tmpl_applied" not in st.session_state:
        st.session_state["tmpl_applied"] = ""

    if mode == "Single":
        if tmpl != st.session_state["tmpl_applied"]:
            st.session_state["tmpl_applied"] = tmpl
            filled = claim_for_label(tmpl)
            if filled:
                st.session_state["claim_box"] = filled
        claim = st.text_area(
            "Your plan or claim",
            height=130,
            key="claim_box",
            placeholder="e.g. Should I launch a weekend newsletter about city walks?",
        )
        with_images = st.checkbox(
            "Also generate promo + images",
            value=False,
            help="Off by default to save time and credits.",
        )
        claim_a = claim_b = ""
        can_run = bool(claim.strip())
    else:
        st.caption("Images stay off in Compare mode to keep runs fast.")
        claim_a = st.text_area("Plan A", height=100, key="claim_a", placeholder="First option…")
        claim_b = st.text_area("Plan B", height=100, key="claim_b", placeholder="Second option…")
        claim = ""
        with_images = False
        can_run = bool(claim_a.strip() and claim_b.strip())

    has_keys = _keys_ok()
    if not has_keys:
        st.warning(
            "Add **OPENROUTER_API_KEY** in Streamlit Cloud → Settings → Secrets."
        )
    else:
        st.caption("OpenRouter ready · Brief default · Memory on")

    run = st.button(
        "Run Verdict Loop v3",
        type="primary",
        disabled=not can_run or not has_keys,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    if run:
        progress = st.progress(0, text="Starting…")
        status = st.empty()

        def on_progress(event: str, payload: dict) -> None:
            labels_map = {
                "scout_start": ("Researching…", 0.15),
                "advocate_start": ("Building the case for…", 0.35),
                "skeptic_start": ("Stress-testing…", 0.5),
                "judge_start": ("Judging…", 0.7),
                "promoter_start": ("Writing promo…", 0.8),
                "image_gen_start": ("Generating images…", 0.88),
                "image_critic_start": ("QA-checking images…", 0.94),
                "a_scout_start": ("Plan A · researching…", 0.1),
                "a_judge_start": ("Plan A · judging…", 0.35),
                "a_run_done": ("Plan A done · starting Plan B…", 0.45),
                "b_scout_start": ("Plan B · researching…", 0.55),
                "b_judge_start": ("Plan B · judging…", 0.8),
                "run_done": ("Done", 1.0),
                "b_run_done": ("Done", 1.0),
            }
            # Strip a_/b_ prefixes for generic matches
            key = event
            if event not in labels_map and "_" in event:
                # a_scout_start already listed; fall back
                pass
            if event in labels_map:
                text, pct = labels_map[event]
                progress.progress(pct, text=text)
                status.caption(text)

        with st.spinner("Running…" + (" compare can take a few minutes" if mode == "Compare" else "")):
            try:
                if mode == "Compare":
                    result = run_compare(
                        claim_a.strip(),
                        claim_b.strip(),
                        detail=detail,
                        on_progress=on_progress,
                    )
                else:
                    result = run_pipeline(
                        claim.strip(),
                        with_images=with_images,
                        detail=detail,
                        on_progress=on_progress,
                    )
            except Exception as exc:
                progress.empty()
                st.error(str(exc))
                return
        progress.progress(1.0, text="Done")
        st.session_state["last_result"] = result
        st.session_state["followup_messages"] = []
        st.session_state["detail_used"] = detail

    result = st.session_state.get("last_result")
    if not result:
        return

    detail_used = result.get("detail") or st.session_state.get("detail_used") or "brief"

    if result.get("mode") == "compare":
        st.markdown("### Compare results")
        st.info(result.get("pick") or "")
        col_a, col_b = st.columns(2)
        with col_a:
            st.caption("Plan A")
            st.write(result.get("claim_a") or "")
            _render_verdict_card(result["result_a"], title="Plan A")
            _render_debate(result["result_a"], detail=detail_used)
        with col_b:
            st.caption("Plan B")
            st.write(result.get("claim_b") or "")
            _render_verdict_card(result["result_b"], title="Plan B")
            _render_debate(result["result_b"], detail=detail_used)
    else:
        _render_verdict_card(result, title="Bottom line")
        _render_debate(result, detail=detail_used)
        _render_creative(result)

    st.markdown("---")
    st.markdown("### Ask a follow-up")
    st.caption("Memory lasts for this browser session and is saved with the run.")

    for msg in st.session_state.get("followup_messages") or []:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    c1, c2 = st.columns([4, 1])
    with c2:
        if st.button("Clear chat"):
            st.session_state["followup_messages"] = []
            st.rerun()

    question = st.chat_input("Ask about this verdict…")
    if question:
        history = list(st.session_state.get("followup_messages") or [])
        history.append({"role": "user", "content": question})
        try:
            from harness.config import load_settings
            from harness.followup import answer_followup, append_followup
            from harness.router import ModelRouter

            router = ModelRouter(load_settings())
            answer = answer_followup(
                router,
                result,
                question,
                history[:-1],
                detail=detail_used,
            )
        except Exception as exc:
            answer = f"Couldn’t answer that follow-up: {exc}"
        history.append({"role": "assistant", "content": answer})
        st.session_state["followup_messages"] = history
        run_dir = result.get("run_dir") or (
            (result.get("result_a") or {}).get("run_dir")
        )
        if run_dir:
            try:
                append_followup(run_dir, question, answer)
            except Exception:
                pass
        st.rerun()


if __name__ == "__main__":
    main()
