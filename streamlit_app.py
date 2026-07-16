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
            if key in st.secrets and st.secrets[key]:
                os.environ[key] = str(st.secrets[key])
except Exception:
    pass

from harness.pipeline import run_pipeline  # noqa: E402

st.set_page_config(
    page_title="Verdict Loop",
    page_icon="⚖️",
    layout="centered",
)

st.markdown(
    """
    <style>
      .block-container { max-width: 820px; padding-top: 2rem; }
      h1 { font-family: Georgia, serif; font-weight: 600; }
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
    st.markdown("### Verdict Loop")
    st.caption("This public demo is password-protected.")
    entered = st.text_input("Password", type="password")
    if st.button("Enter") and entered == password:
        st.session_state["authed"] = True
        st.rerun()
    if entered:
        st.error("Wrong password")
    return False


def main() -> None:
    if not _gate():
        return

    st.markdown("**Verdict Loop**")
    st.title("Stress-test a plan. Then generate creatives.")
    st.write(
        "Scout researches. Advocate and Skeptic argue. Judge decides. "
        "Optionally Promoter writes the pitch, an image model draws, "
        "and a vision critic QA-checks."
    )

    claim = st.text_area(
        "Your plan or claim",
        height=140,
        placeholder="e.g. Should I launch a weekend newsletter about city walks for local businesses?",
    )
    with_images = st.checkbox("Run promo + image loop after the verdict", value=True)

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

    if st.button("Run red team", type="primary", disabled=not claim.strip()):
        with st.spinner("Running debate (and creatives if enabled). This can take a few minutes…"):
            try:
                result = run_pipeline(claim.strip(), with_images=with_images)
            except Exception as exc:
                st.error(str(exc))
                return

        st.session_state["last_result"] = result

    result = st.session_state.get("last_result")
    if not result:
        return

    verdict = result["debate"]["verdict"]
    st.subheader("Verdict")
    st.success(
        f"**{verdict.get('recommendation')}** · score {verdict.get('score')}"
    )
    st.write(verdict.get("reasoning") or "")
    conditions = verdict.get("conditions") or []
    if conditions:
        st.markdown("**Conditions**")
        for c in conditions:
            st.markdown(f"- {c}")

    st.subheader("Debate transcript")
    for rnd in result["debate"]["rounds"]:
        with st.expander(f"Round {rnd['round']} — judge score {rnd['judgment'].get('score')}"):
            st.markdown("**Advocate**")
            st.write(rnd["advocate"])
            st.markdown("**Skeptic**")
            st.write(rnd["skeptic"])

    creative = result.get("creative")
    if creative:
        promo = creative["promo"]
        st.subheader("Promo pack")
        st.markdown(f"**{promo.get('headline')}**")
        st.caption(promo.get("tagline") or "")
        st.write(promo.get("promo_blurb") or "")
        run_dir = Path(result["run_dir"])
        cols = st.columns(2)
        for i, asset in enumerate(creative.get("approved") or []):
            img_path = run_dir / asset["path"]
            with cols[i % 2]:
                if img_path.exists():
                    st.image(str(img_path), caption=f"{asset.get('purpose')} · score {asset['critique'].get('score')}")


if __name__ == "__main__":
    main()
