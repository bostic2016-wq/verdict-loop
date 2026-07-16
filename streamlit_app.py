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
    page_title="Verdict Loop v4",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
      :root {
        --ink: #10141c;
        --muted: #5a6573;
        --panel: #ffffff;
        --accent: #0c8f7c;
        --accent-deep: #0a7264;
        --line: rgba(16,20,28,0.10);
        --soft: #f3f5f7;
      }
      html, body, .stApp, [class*="css"],
      .stMarkdown, .stChatMessage, .stCaption,
      [data-testid="stMarkdownContainer"],
      [data-testid="stChatMessage"],
      [data-testid="stCaptionContainer"],
      [data-testid="stWidgetLabel"],
      p, li, span, label, textarea, input, button, h1, h2, h3, h4, h5, h6 {
        font-family: "Manrope", sans-serif !important;
        letter-spacing: 0 !important;
        text-shadow: none !important;
        filter: none !important;
      }
      .stApp {
        background: var(--soft);
      }
      .block-container {
        max-width: 880px;
        padding-top: 1.5rem;
        padding-bottom: 4rem;
      }
      #MainMenu, footer { visibility: hidden; }
      .vl-hero { margin-bottom: 1.25rem; }
      .vl-brand-row {
        display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;
        margin: 0 0 0.75rem;
      }
      .vl-brand {
        font-size: 1.35rem; font-weight: 800; color: var(--ink);
        margin: 0; letter-spacing: -0.02em;
      }
      .vl-chip {
        font-size: 0.7rem; font-weight: 700; letter-spacing: 0.06em;
        text-transform: uppercase; padding: 0.3rem 0.65rem; border-radius: 999px;
        background: var(--accent); color: #fff;
      }
      .vl-title {
        font-size: clamp(1.85rem, 4vw, 2.45rem);
        line-height: 1.15; color: var(--ink); margin: 0 0 0.55rem;
        font-weight: 800; letter-spacing: -0.03em;
      }
      .vl-lede {
        color: var(--muted); font-size: 1.02rem; line-height: 1.55;
        max-width: 36rem; margin: 0;
      }
      .vl-panel {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 1.15rem 1.2rem 1.25rem;
        box-shadow: 0 8px 24px rgba(16,20,28,0.04);
        margin-bottom: 0.5rem;
      }
      .vl-verdict {
        border-radius: 14px; padding: 1.1rem 1.15rem;
        border: 1px solid var(--line); margin: 1rem 0;
        background: #fff;
      }
      .vl-verdict.do { background: #e8f7f2; }
      .vl-verdict.dont { background: #fdeceb; }
      .vl-verdict.only_if { background: #eef3f8; }
      .vl-badge {
        display: inline-block; font-size: 0.72rem; letter-spacing: 0.06em;
        text-transform: uppercase; font-weight: 700; padding: 0.25rem 0.5rem;
        border-radius: 999px; background: var(--ink); color: #fff; margin-bottom: 0.5rem;
      }
      .vl-ask {
        background: #e8f7f2; border: 1px solid rgba(12,143,124,0.28);
        border-radius: 14px; padding: 0.95rem 1.05rem; margin: 0.75rem 0 1rem;
      }
      .vl-ask-label {
        font-size: 0.7rem; font-weight: 800; letter-spacing: 0.08em;
        text-transform: uppercase; color: var(--accent-deep); margin: 0 0 0.35rem;
      }
      .vl-ask-q {
        font-size: 1.05rem; font-weight: 650; color: var(--ink);
        line-height: 1.4; margin: 0;
      }
      .vl-reply {
        font-family: "Manrope", sans-serif !important;
        font-size: 0.98rem; line-height: 1.6; color: var(--ink);
        white-space: pre-wrap; word-break: break-word;
      }
      .vl-meta {
        font-size: 0.78rem; color: var(--muted); margin: 0.35rem 0 0;
      }
      .vl-steps {
        display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem;
        margin: 1rem 0 0.25rem;
      }
      .vl-step {
        background: #fff; border: 1px solid var(--line); border-radius: 12px;
        padding: 0.65rem 0.7rem; font-size: 0.78rem; color: var(--muted);
      }
      .vl-step strong { display: block; color: var(--ink); font-size: 0.84rem; margin-bottom: 0.1rem; }
      @media (max-width: 720px) { .vl-steps { grid-template-columns: 1fr 1fr; } }
      div.stButton > button[kind="primary"],
      div.stButton > button {
        background: var(--accent) !important; color: #fff !important;
        border: 0 !important; border-radius: 12px !important; font-weight: 700 !important;
      }
      textarea, [data-baseweb="select"] { border-radius: 10px !important; }
      /* Kill Streamlit markdown italics looking like a second font */
      em, i, strong, b { font-family: inherit !important; }
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
        '<span class="vl-chip">v4</span></div>'
        '<h1 class="vl-title">Enter to continue</h1>'
        '<p class="vl-lede">This public demo is password-protected.</p></div>',
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


def _plain(text: str) -> None:
    import html as _html

    safe = _html.escape(text or "").replace("\n", "<br>")
    st.markdown(f'<div class="vl-reply">{safe}</div>', unsafe_allow_html=True)


def _render_verdict_card(result: dict, *, title: str = "Bottom line") -> None:
    import html as _html

    debate = result.get("debate") or {}
    verdict = debate.get("verdict") or {}
    rec = str(verdict.get("recommendation") or "only_if")
    bottom = _html.escape(str(verdict.get("bottom_line") or verdict.get("reasoning") or ""))
    st.markdown(
        f"""
        <div class="vl-verdict {_verdict_class(rec)}">
          <div class="vl-badge">{_html.escape(rec)} · score {verdict.get('score')}</div>
          <div style="font-weight:700;font-size:1.05rem;margin-bottom:0.35rem;">{_html.escape(title)}</div>
          <div class="vl-reply">{bottom}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    conditions = verdict.get("conditions") or []
    if conditions:
        st.markdown("**Only proceed if**")
        for c in conditions[:3]:
            st.write(f"• {c}")


def _render_debate(result: dict, *, detail: str) -> None:
    debate = result.get("debate") or {}
    rounds = debate.get("rounds") or []
    if not rounds:
        return
    with st.expander("Full debate", expanded=(detail == "detailed")):
        notes = debate.get("final_notes") or {}
        if notes.get("summary"):
            st.caption("Research summary")
            _plain(str(notes.get("summary")))
        for rnd in rounds:
            st.write(f"Round {rnd['round']} — judge score {rnd['judgment'].get('score')}")
            left, right = st.columns(2)
            with left:
                st.write("Advocate")
                _plain(str(rnd.get("advocate") or ""))
            with right:
                st.write("Skeptic")
                _plain(str(rnd.get("skeptic") or ""))


def _render_creative(result: dict) -> None:
    creative = result.get("creative")
    if not creative:
        return
    promo = creative.get("promo") or {}
    st.markdown("### Promo pack")
    st.write(promo.get("headline") or "Promo")
    st.caption(promo.get("tagline") or "")
    _plain(str(promo.get("promo_blurb") or ""))
    run_dir = Path(result["run_dir"])
    approved = creative.get("approved") or []
    if approved:
        cols = st.columns(min(2, len(approved)))
        for i, asset in enumerate(approved):
            img_path = run_dir / asset["path"]
            with cols[i % len(cols)]:
                if img_path.exists():
                    st.image(str(img_path), use_container_width=True)


def _keys_ok() -> bool:
    if os.getenv("OPENROUTER_API_KEY"):
        return True
    return bool(os.getenv("GROQ_API_KEY") and os.getenv("GEMINI_API_KEY"))


def _render_money_facts(result: dict) -> None:
    money = result.get("money_facts") or {}
    if not money.get("has_money_signal"):
        return
    with st.expander("Verified money math", expanded=True):
        if money.get("gross") is not None:
            st.write(f"Gross used: ${money['gross']:,.0f}/yr")
        if money.get("net") is not None and money.get("tax_rate") is not None:
            st.write(
                f"After-tax: ${money['net']:,.0f}/yr "
                f"at {money['tax_rate'] * 100:g}% effective tax"
            )
        for c in money.get("calculations") or []:
            st.write(f"• {c}")
        for m in money.get("missing") or []:
            st.warning(m)


def _model_picker_ui() -> tuple[list[str], dict[str, str]]:
    from harness.chat import default_chat_catalog
    from harness.config import load_settings

    settings = load_settings()
    catalog = default_chat_catalog(settings)
    id_to_label = {m["id"]: m["label"] for m in catalog}
    id_to_model = {m["id"]: m["model"] for m in catalog}
    all_ids = [m["id"] for m in catalog]
    defaults = list((settings.get("chat") or {}).get("default_panel") or all_ids[:3])
    defaults = [d for d in defaults if d in id_to_label] or all_ids[:3]

    st.markdown("#### Models")
    st.caption(
        "These models vote into one consensus answer (QA’d by o3). "
        "Also set who plays each debate role."
    )

    if "v4_model_multiselect_onset" not in st.session_state:
        st.session_state["v4_model_multiselect_onset"] = defaults
    else:
        st.session_state["v4_model_multiselect_onset"] = [
            mid for mid in st.session_state["v4_model_multiselect_onset"] if mid in id_to_label
        ] or defaults

    selected = st.multiselect(
        "Consensus panel (up to 3 used per answer)",
        options=all_ids,
        format_func=lambda mid: id_to_label.get(mid, mid),
        key="v4_model_multiselect_onset",
        max_selections=6,
    )
    st.session_state["v4_model_ids"] = selected

    role_defaults = {
        "scout": "gpt-5.4-mini",
        "advocate": "grok-4.5",
        "skeptic": "gemini-2.5-flash",
        "judge": "claude-fable-5",
    }
    for role, default_id in list(role_defaults.items()):
        if default_id not in id_to_model and all_ids:
            role_defaults[role] = all_ids[0]

    st.caption("Debate lineup")
    r1, r2 = st.columns(2)
    with r1:
        scout_id = st.selectbox(
            "Scout", all_ids,
            index=all_ids.index(role_defaults["scout"]) if role_defaults["scout"] in all_ids else 0,
            format_func=lambda mid: id_to_label.get(mid, mid), key="role_scout",
        )
        skeptic_id = st.selectbox(
            "Skeptic", all_ids,
            index=all_ids.index(role_defaults["skeptic"]) if role_defaults["skeptic"] in all_ids else 0,
            format_func=lambda mid: id_to_label.get(mid, mid), key="role_skeptic",
        )
    with r2:
        advocate_id = st.selectbox(
            "Advocate", all_ids,
            index=all_ids.index(role_defaults["advocate"]) if role_defaults["advocate"] in all_ids else 0,
            format_func=lambda mid: id_to_label.get(mid, mid), key="role_advocate",
        )
        judge_id = st.selectbox(
            "Judge", all_ids,
            index=all_ids.index(role_defaults["judge"]) if role_defaults["judge"] in all_ids else 0,
            format_func=lambda mid: id_to_label.get(mid, mid), key="role_judge",
        )

    overrides = {
        "scout": id_to_model[scout_id],
        "advocate": id_to_model[advocate_id],
        "skeptic": id_to_model[skeptic_id],
        "judge": id_to_model[judge_id],
    }
    return selected, overrides


def _ask_followup(result: dict, detail_used: str) -> None:
    """System-led consensus chat: one answer + next question to the user."""
    from harness.chat import (
        append_turn,
        ask_consensus,
        create_chat,
        default_chat_catalog,
    )
    from harness.config import load_settings
    from harness.followup import append_followup, opening_question
    from harness.router import ModelRouter

    settings = load_settings()
    catalog = default_chat_catalog(settings)
    catalog_by_id = {m["id"]: m for m in catalog}
    id_to_label = {m["id"]: m["label"] for m in catalog}
    defaults = list((settings.get("chat") or {}).get("default_panel") or [])
    selected = list(st.session_state.get("v4_model_ids") or defaults)
    selected = [mid for mid in selected if mid in catalog_by_id] or defaults
    selected = [mid for mid in selected if mid in catalog_by_id]

    st.markdown("---")
    st.markdown("### Continue the conversation")
    panel_labels = ", ".join(id_to_label.get(m, m) for m in selected[:3]) or "default panel"
    st.caption(f"Consensus from {panel_labels}. Fact-checked by o3 QA.")

    chat_key = "v4_chat"
    run_dir_now = result.get("run_dir") or (result.get("result_a") or {}).get("run_dir")
    if st.session_state.get("v4_chat_run_dir") != run_dir_now:
        st.session_state.pop(chat_key, None)
        st.session_state.pop("v4_chat_id", None)

    open_q = opening_question(result)
    if not st.session_state.get(chat_key):
        chat = create_chat(
            settings,
            model_ids=selected,
            run_result=result,
            detail=detail_used,
            pending_question=open_q,
        )
        st.session_state[chat_key] = chat
        st.session_state["v4_chat_id"] = chat["id"]
        st.session_state["v4_chat_run_dir"] = chat.get("run_dir")
    else:
        chat = st.session_state[chat_key]
        chat["models"] = [catalog_by_id[mid] for mid in selected if mid in catalog_by_id]

    # History
    for msg in chat.get("messages") or []:
        if msg.get("role") == "user":
            with st.chat_message("user"):
                _plain(str(msg.get("content") or ""))
        elif msg.get("role") == "assistant":
            with st.chat_message("assistant"):
                _plain(str(msg.get("content") or ""))
                if msg.get("qa_notes") and str(msg.get("qa_notes")).lower() not in {"none", "issues: none"}:
                    st.caption(f"QA · {msg.get('qa_notes')}")
                nq = msg.get("next_question")
                if nq:
                    st.markdown(
                        f'<div class="vl-ask"><p class="vl-ask-label">Next for you</p>'
                        f'<p class="vl-ask-q">{__import__("html").escape(nq)}</p></div>',
                        unsafe_allow_html=True,
                    )

    pending = chat.get("pending_question") or open_q
    if not chat.get("messages"):
        st.markdown(
            f'<div class="vl-ask"><p class="vl-ask-label">We need one thing from you</p>'
            f'<p class="vl-ask-q">{__import__("html").escape(pending)}</p></div>',
            unsafe_allow_html=True,
        )
    elif chat.get("pending_question"):
        # Already shown via last assistant turn; keep a sticky reminder if useful
        pass

    c1, c2 = st.columns([3, 1])
    with c2:
        if st.button("Reset chat"):
            chat = create_chat(
                settings,
                model_ids=selected,
                run_result=result,
                detail=detail_used,
                pending_question=open_q,
            )
            st.session_state[chat_key] = chat
            st.rerun()

    answer = st.chat_input("Answer the question above, or ask your own…")
    if not answer:
        return
    if not selected:
        st.warning("Pick at least one model in the panel above.")
        return

    chat["models"] = [catalog_by_id[mid] for mid in selected if mid in catalog_by_id]
    user_text = answer.strip()

    with st.chat_message("user"):
        _plain(user_text)
    with st.chat_message("assistant"):
        status = st.empty()
        status.caption("Building consensus + QA…")
        try:
            router = ModelRouter(settings)
            out = ask_consensus(
                router, settings, chat, user_text, model_ids=selected
            )
        except Exception as exc:
            status.empty()
            st.error(f"Couldn’t answer: {exc}")
            return
        status.empty()
        _plain(out["consensus"])
        if out.get("qa_notes") and str(out["qa_notes"]).lower() not in {"none", "issues: none"}:
            st.caption(f"QA · {out['qa_notes']} ({out.get('qa_verdict')})")
        nq = out.get("next_question") or ""
        if nq:
            st.markdown(
                f'<div class="vl-ask"><p class="vl-ask-label">Next for you</p>'
                f'<p class="vl-ask-q">{__import__("html").escape(nq)}</p></div>',
                unsafe_allow_html=True,
            )
        with st.expander("Panel drafts (optional)"):
            for mid, text in (out.get("replies") or {}).items():
                st.write(id_to_label.get(mid, mid))
                _plain(str(text))

    chat = append_turn(
        settings,
        chat,
        user_text,
        out.get("replies") or {},
        consensus=out.get("consensus"),
        next_question=out.get("next_question"),
        qa_notes=out.get("qa_notes"),
    )
    st.session_state[chat_key] = chat
    if run_dir_now:
        try:
            append_followup(run_dir_now, user_text, out.get("consensus") or "")
        except Exception:
            pass
    st.rerun()


def main() -> None:
    if not _gate():
        return

    st.markdown(
        """
        <div class="vl-hero">
          <div class="vl-brand-row">
            <p class="vl-brand">Verdict Loop</p>
            <span class="vl-chip">v4 · Consensus</span>
          </div>
          <h1 class="vl-title">Stress-test a plan. Get one clear answer.</h1>
          <p class="vl-lede">
            Models debate, then we return a QA-checked consensus — and we ask
            you the next clarifying question.
          </p>
        </div>
        <div class="vl-steps">
          <div class="vl-step"><strong>1 · Scout</strong>Map risks</div>
          <div class="vl-step"><strong>2 · Debate</strong>Advocate vs Skeptic</div>
          <div class="vl-step"><strong>3 · Judge</strong>Do / don’t / only if</div>
          <div class="vl-step"><strong>4 · Consensus</strong>QA’d follow-up</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="vl-panel">', unsafe_allow_html=True)
    chat_model_ids, model_overrides = _model_picker_ui()

    mode = st.radio("Mode", ["Single", "Compare"], horizontal=True, index=0)
    detail_label = st.radio(
        "Response length", ["Brief", "Detailed"], horizontal=True, index=0,
        help="Brief is short. Detailed includes the debate transcript.",
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
            "Your plan or claim", height=130, key="claim_box",
            placeholder="e.g. Should I launch a weekend newsletter about city walks?",
        )
        with_images = st.checkbox("Also generate promo + images", value=False)
        claim_a = claim_b = ""
        can_run = bool(claim.strip())
    else:
        st.caption("Images stay off in Compare mode.")
        claim_a = st.text_area("Plan A", height=100, key="claim_a")
        claim_b = st.text_area("Plan B", height=100, key="claim_b")
        claim = ""
        with_images = False
        can_run = bool(claim_a.strip() and claim_b.strip())

    has_keys = _keys_ok()
    if not has_keys:
        st.warning("Add OPENROUTER_API_KEY in Streamlit Cloud → Settings → Secrets.")
    if not chat_model_ids:
        st.warning("Select at least one model for the consensus panel.")

    run = st.button(
        "Run Verdict Loop",
        type="primary",
        disabled=not can_run or not has_keys or not chat_model_ids,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    if run:
        progress = st.progress(0, text="Starting…")
        status = st.empty()

        def on_progress(event: str, payload: dict) -> None:
            labels_map = {
                "scout_start": ("Researching…", 0.15),
                "advocate_start": ("Building the case…", 0.35),
                "skeptic_start": ("Stress-testing…", 0.5),
                "judge_start": ("Judging…", 0.7),
                "promoter_start": ("Writing promo…", 0.8),
                "image_gen_start": ("Generating images…", 0.88),
                "a_scout_start": ("Plan A…", 0.2),
                "b_scout_start": ("Plan B…", 0.2),
                "a_run_done": ("Plan A done…", 0.7),
                "b_run_done": ("Plan B done…", 0.7),
                "run_done": ("Done", 1.0),
            }
            if event in labels_map:
                text, pct = labels_map[event]
                progress.progress(pct, text=text)
                status.caption(text)

        with st.spinner("Running…" + (" A & B in parallel" if mode == "Compare" else "")):
            try:
                if mode == "Compare":
                    result = run_compare(
                        claim_a.strip(), claim_b.strip(), detail=detail,
                        on_progress=on_progress, model_overrides=model_overrides,
                    )
                else:
                    result = run_pipeline(
                        claim.strip(), with_images=with_images, detail=detail,
                        on_progress=on_progress, model_overrides=model_overrides,
                    )
            except Exception as exc:
                progress.empty()
                st.error(str(exc))
                return
        progress.progress(1.0, text="Done")
        st.session_state["last_result"] = result
        st.session_state["detail_used"] = detail
        st.session_state.pop("v4_chat", None)
        st.session_state.pop("v4_chat_id", None)
        st.session_state.pop("v4_chat_run_dir", None)

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
        _render_money_facts(result)
        _render_debate(result, detail=detail_used)
        _render_creative(result)

    _ask_followup(result, detail_used)


if __name__ == "__main__":
    main()
