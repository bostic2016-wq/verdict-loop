"""Manga Storyboard — local Streamlit app.

Run from this folder:
  streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from pipeline.analyze import analyze_transcript, apply_answers
from pipeline.creative_bible import build_bible
from pipeline.export import export_zip
from pipeline.pdf_ingest import extract_transcript
from pipeline.router import DirectorRouter, ProviderError
from pipeline.run import generate_batch, regenerate_one
from pipeline.style_library import (
    add_drawing,
    load_character_map,
    load_library,
    merge_saved_characters,
    remove_drawing,
    resolve_ref_path,
    save_character_map,
    upsert_character,
)
from pipeline.util import list_styles, load_settings, new_run_dir, save_json

st.set_page_config(page_title="Manga Storyboard", page_icon="📖", layout="wide")

# Load secrets/env before anything else that needs API keys
settings = load_settings()

# Optional public-page lock (Streamlit Cloud secrets: APP_PASSWORD)
_app_password = __import__("os").environ.get("APP_PASSWORD", "").strip()
if _app_password:
    if "authed" not in st.session_state:
        st.session_state.authed = False
    if not st.session_state.authed:
        st.title("Manga Storyboard")
        pw = st.text_input("Password", type="password")
        if st.button("Enter") and pw == _app_password:
            st.session_state.authed = True
            st.rerun()
        st.stop()

# --- Session defaults ---
DEFAULTS = {
    "step": "intake",  # intake | brief | pilot | continue
    "transcript": "",
    "transcript_name": "",
    "aesthetic": "jjk_inspired",
    "analysis": None,
    "brief": None,
    "bible": None,
    "run_dir": None,
    "pilot_panels": [],
    "all_panels": [],
    "sequence": None,
    "qa_round": 0,
}


def init_state() -> None:
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()
styles = list_styles()
style_ids = [s["id"] for s in styles]


def router() -> DirectorRouter:
    return DirectorRouter(settings)


# ---------- Sidebar: style library ----------
with st.sidebar:
    st.header("Character library")
    st.caption("Upload a drawing + name it once. The app remembers the character forever — even after refresh.")
    uploads = st.file_uploader(
        "Add drawings",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key="lib_upload",
    )
    character = st.text_input("Character name", key="lib_char", placeholder="e.g. Kaito")
    tags_raw = st.text_input("Tags (comma-separated)", key="lib_tags")
    if st.button("Save to library", type="primary", use_container_width=True) and uploads:
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        for f in uploads:
            add_drawing(f.getvalue(), filename=f.name, tags=tags, character=character)
            if character.strip():
                # Remember this character ↔ drawing mapping permanently
                upsert_character(character, ref=f.name)
        st.success(f"Saved {len(uploads)} drawing(s)" + (f" as **{character}**" if character.strip() else ""))
        st.rerun()

    items = load_library()
    if items:
        for item in items:
            cols = st.columns([3, 1])
            with cols[0]:
                label = item.get("character") or "untagged"
                st.caption(f"**{label}** — {item.get('original_name')}")
                if Path(item["path"]).exists():
                    st.image(item["path"], use_container_width=True)
            with cols[1]:
                if st.button("✕", key=f"del_{item['id']}"):
                    remove_drawing(item["id"])
                    st.rerun()
    else:
        st.info("No drawings yet. Upload one per character — it becomes their permanent reference.")

    saved_chars = load_character_map()
    if saved_chars:
        with st.expander(f"Remembered characters ({len(saved_chars)})"):
            for sc in saved_chars:
                has_ref = "🖼️" if resolve_ref_path(sc.get("ref")) or resolve_ref_path(sc.get("name")) else "—"
                st.caption(f"{has_ref} **{sc.get('name')}** {('· ' + sc.get('look', '')[:60]) if sc.get('look') else ''}")

    st.divider()
    import os

    mock = st.checkbox(
        "Mock images (no API spend)",
        value=False,
        help="OFF = real panels (Nano Banana Pro → GPT Image). ON = placeholder panels only.",
    )
    if mock:
        settings.setdefault("models", {})["image_backend"] = "mock"
        os.environ["MANGA_MOCK_IMAGES"] = "1"
        os.environ["MANGA_FORCE_MOCK"] = "1"
        st.caption("⚠️ Mock mode — panels will be placeholders, not art.")
    else:
        os.environ.pop("MANGA_MOCK_IMAGES", None)
        os.environ.pop("MANGA_FORCE_MOCK", None)
        settings.setdefault("models", {})["image_backend"] = "openrouter"
        st.caption("Image backend: Nano Banana Pro → FLUX (character refs on)")

    try:
        from pipeline.generate import IMAGE_PIPELINE_BUILD

        st.caption(f"Build: {IMAGE_PIPELINE_BUILD}")
    except Exception:
        st.caption("Build: (old — reboot the app)")


# ---------- Header ----------
st.title("Manga Storyboard")
st.caption("PDF → analyze → brief → 5-panel pilot → lock & continue. Editorial QA built in.")

step = st.session_state.step

# Step progress indicator
_STEPS = [("intake", "1 · Script"), ("brief", "2 · Brief"), ("pilot", "3 · Pilot"), ("continue", "4 · Continue")]
_current = next((i for i, (k, _) in enumerate(_STEPS) if k == step), 0)
_ind_cols = st.columns(len(_STEPS))
for i, (key, label) in enumerate(_STEPS):
    with _ind_cols[i]:
        if i < _current:
            st.markdown(f"✅ ~~{label}~~")
        elif i == _current:
            st.markdown(f"**🔵 {label}**")
        else:
            st.markdown(f"<span style='color:gray'>○ {label}</span>", unsafe_allow_html=True)
st.divider()

# ============================================================
# STEP 1 — Intake
# ============================================================
if step == "intake":
    st.subheader("1. Intake")
    left, right = st.columns([2, 1])
    with left:
        pdf = st.file_uploader("Drop transcript PDF (or TXT/MD)", type=["pdf", "txt", "md"], key="transcript_file")
        pasted = st.text_area("Or paste script", height=200, placeholder="PAGE 1\nPanel 1: ...")
    with right:
        aesthetic = st.radio(
            "Aesthetic",
            options=style_ids,
            format_func=lambda i: next((s["name"] for s in styles if s["id"] == i), i),
            index=style_ids.index(settings.get("defaults", {}).get("aesthetic", "jjk_inspired"))
            if settings.get("defaults", {}).get("aesthetic", "jjk_inspired") in style_ids
            else 0,
        )
        st.session_state.aesthetic = aesthetic
        for s in styles:
            if s["id"] == aesthetic:
                st.caption(Path(s["path"]).read_text(encoding="utf-8").split("description:")[-1].split("positive")[0][:280].strip(" >\n"))

    if st.button("Analyze script", type="primary", use_container_width=True):
        transcript = ""
        name = "pasted.txt"
        if pdf is not None:
            tmp = ROOT / "outputs" / f"_upload_{pdf.name}"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(pdf.getvalue())
            try:
                transcript = extract_transcript(tmp)
            except ValueError as e:
                st.error(str(e))
                st.stop()
            name = pdf.name
        elif pasted.strip():
            transcript = pasted.strip()
        else:
            st.warning("Upload a PDF/TXT or paste a script.")
            st.stop()

        st.session_state.transcript = transcript
        st.session_state.transcript_name = name
        with st.spinner("Director analyzing transcript…"):
            try:
                analysis = analyze_transcript(router(), transcript, aesthetic)
            except ProviderError as e:
                st.error(str(e))
                st.stop()
            except Exception as e:  # noqa: BLE001
                st.error(f"Analysis failed: {e}")
                st.stop()
        st.session_state.analysis = analysis
        st.session_state.brief = analysis.get("brief") or {}
        st.session_state.step = "brief"
        st.rerun()

# ============================================================
# STEP 2 — Brief + gap Q&A
# ============================================================
elif step == "brief":
    st.subheader("2. Creative brief")
    analysis = st.session_state.analysis or {}
    brief = dict(st.session_state.brief or {})

    st.markdown(f"**Summary:** {analysis.get('summary', '—')}")
    if analysis.get("beats"):
        st.markdown("**Beats:** " + " · ".join(analysis["beats"][:8]))
    if analysis.get("risks"):
        with st.expander("Risks / ambiguities"):
            for r in analysis["risks"]:
                st.write(f"- {r}")

    st.markdown("#### Editable brief (tap what is wrong)")
    c1, c2, c3 = st.columns(3)
    with c1:
        brief["aesthetic"] = st.selectbox(
            "Aesthetic",
            style_ids,
            index=style_ids.index(brief.get("aesthetic", st.session_state.aesthetic))
            if brief.get("aesthetic", st.session_state.aesthetic) in style_ids
            else 0,
        )
        brief["tone"] = st.text_input("Tone", value=brief.get("tone") or analysis.get("tone") or "")
    with c2:
        dens = brief.get("panel_density") or "cinematic"
        brief["panel_density"] = st.selectbox(
            "Panel density",
            ["cinematic", "dense"],
            index=0 if dens != "dense" else 1,
        )
        brief["world"] = st.text_input("World / setting", value=brief.get("world") or "")
    with c3:
        st.text_area("First-5 focus", value=analysis.get("first_five_focus") or "", disabled=True, height=100)

    st.markdown("**Characters**")
    st.caption("Mapped drawings are sent to the image model as reference art — and remembered across sessions.")
    maps = list(brief.get("character_maps") or [])
    lib_names = [i.get("original_name") or i["filename"] for i in load_library()]
    if not maps and analysis.get("characters"):
        maps = [
            {
                "name": c.get("name"),
                "look": c.get("visual_guess", ""),
                "ref": c.get("suggested_ref"),
            }
            for c in analysis["characters"]
        ]
    # Overlay remembered characters (saved refs/looks survive refresh)
    maps = merge_saved_characters(maps)
    new_maps = []
    for i, row in enumerate(maps):
        cols = st.columns([1, 2, 3, 3])
        thumb = resolve_ref_path(row.get("ref")) or resolve_ref_path(row.get("name"))
        with cols[0]:
            if thumb:
                st.image(str(thumb), use_container_width=True)
            else:
                st.markdown("<div style='color:gray;text-align:center;padding-top:12px'>no ref</div>", unsafe_allow_html=True)
        with cols[1]:
            name = st.text_input("Name", value=row.get("name") or "", key=f"cn_{i}")
        with cols[2]:
            look = st.text_input("Look", value=row.get("look") or "", key=f"cl_{i}")
        with cols[3]:
            options = ["(none)"] + lib_names
            current = row.get("ref") or "(none)"
            idx = options.index(current) if current in options else 0
            ref = st.selectbox("Ref drawing", options, index=idx, key=f"cr_{i}")
        new_maps.append({"name": name, "look": look, "ref": None if ref == "(none)" else ref})
    brief["character_maps"] = new_maps
    st.session_state.brief = brief

    # Gap questions
    questions = analysis.get("questions") or []
    answers_payload = []
    if questions and not analysis.get("ready"):
        st.markdown("#### Clarifying questions")
        st.caption("AI-generated for this script — pick an option or Other.")
        for q in questions:
            st.markdown(f"**{q.get('prompt')}**")
            opts = list(q.get("options") or [])
            labels = [o.get("label", o.get("id", "")) for o in opts] + ["Other"]
            choice = st.radio(
                q.get("id", "q"),
                labels,
                key=f"q_{st.session_state.qa_round}_{q.get('id')}",
                label_visibility="collapsed",
            )
            other_text = ""
            if choice == "Other":
                other_text = st.text_input("Elaborate", key=f"qo_{st.session_state.qa_round}_{q.get('id')}")
            answers_payload.append(
                {
                    "id": q.get("id"),
                    "prompt": q.get("prompt"),
                    "choice": choice,
                    "other": other_text,
                }
            )

        b1, b2 = st.columns(2)
        with b1:
            if st.button("Submit answers", type="primary", use_container_width=True):
                for a in answers_payload:
                    if a["choice"] == "Other" and not (a.get("other") or "").strip():
                        st.warning("Fill in Other text or pick an option.")
                        st.stop()
                with st.spinner("Updating brief…"):
                    try:
                        updated = apply_answers(router(), analysis, answers_payload)
                    except Exception as e:  # noqa: BLE001
                        st.error(str(e))
                        st.stop()
                st.session_state.analysis = updated
                st.session_state.brief = updated.get("brief") or brief
                st.session_state.qa_round += 1
                st.rerun()
        with b2:
            if st.button("Skip to pilot", use_container_width=True):
                analysis["ready"] = True
                st.session_state.analysis = analysis
                st.rerun()
    else:
        st.success("Brief ready — no blocking questions.")

    st.divider()
    go1, go2 = st.columns(2)
    with go1:
        if st.button("Generate 5-panel pilot", type="primary", use_container_width=True):
            # Remember this cast permanently (survives refresh / new scripts)
            save_character_map(merge_saved_characters(brief.get("character_maps") or []))
            bible = build_bible(brief, aesthetic=brief.get("aesthetic"), analysis=analysis)
            run_dir = new_run_dir()
            save_json(run_dir / "analysis.json", analysis)
            save_json(run_dir / "brief.json", brief)
            save_json(run_dir / "bible.json", bible)
            (run_dir / "transcript.txt").write_text(st.session_state.transcript, encoding="utf-8")
            st.session_state.bible = bible
            st.session_state.run_dir = str(run_dir)

            progress = st.progress(0, text="Planning panels…")
            events: list[str] = []

            def emit(event: str, payload: dict) -> None:
                events.append(event)
                if event == "panels_planned":
                    progress.progress(0.1, text="Panels planned — generating…")
                elif event == "panel_start":
                    idx = payload.get("index", 0)
                    progress.progress(
                        min(0.1 + 0.15 * max(int(idx) - 1, 0), 0.9),
                        text=f"Generating panel {idx}…",
                    )
                elif event == "panel_done":
                    idx = payload.get("index", 0)
                    progress.progress(min(0.1 + 0.15 * int(idx), 0.9), text=f"Panel {idx} done")
                elif event == "sequence_done":
                    progress.progress(0.95, text="Sequence QA…")

            try:
                batch = generate_batch(
                    router(),
                    settings,
                    bible,
                    st.session_state.transcript,
                    run_dir,
                    start_index=1,
                    count=int(settings.get("pilot", {}).get("panel_count", 5)),
                    emit=emit,
                )
            except ProviderError as e:
                st.error(str(e))
                st.stop()
            except Exception as e:  # noqa: BLE001
                st.error(f"Generation failed: {e}")
                st.stop()

            progress.progress(1.0, text="Pilot ready")
            st.session_state.pilot_panels = batch["panels"]
            st.session_state.all_panels = list(batch["panels"])
            st.session_state.sequence = batch.get("sequence")
            st.session_state.step = "pilot"
            st.rerun()
    with go2:
        if st.button("Back to intake", use_container_width=True):
            st.session_state.step = "intake"
            st.rerun()

# ============================================================
# STEP 3 — Pilot filmstrip
# ============================================================
elif step in {"pilot", "continue"}:
    st.subheader("3. Storyboard filmstrip" if step == "pilot" else "4. Continue")
    bible = st.session_state.bible or {}
    run_dir = Path(st.session_state.run_dir) if st.session_state.run_dir else None
    panels = st.session_state.all_panels or []

    with st.expander("Creative bible (locked)", expanded=False):
        st.json(
            {
                "aesthetic": bible.get("aesthetic_name"),
                "tone": bible.get("tone"),
                "characters": bible.get("characters"),
                "do_not": bible.get("do_not"),
            }
        )

    seq = st.session_state.sequence or {}
    if seq:
        if seq.get("sequence_pass"):
            st.success(f"Sequence QA passed (score {seq.get('score', '—')}). {seq.get('notes', '')}")
        else:
            st.warning(
                f"Sequence notes: {seq.get('notes', '')} · issues: {', '.join(seq.get('pacing_issues') or []) or '—'}"
            )

    if not panels:
        st.info("No panels yet.")
    else:
        # Render all panels in rows of 5
        for row_start in range(0, len(panels), 5):
            chunk = panels[row_start : row_start + 5]
            cols = st.columns(len(chunk))
            for col, p in zip(cols, chunk):
                with col:
                    status = "needs review" if p.get("needs_review") else ("passed" if p.get("passed") else "check")
                    st.markdown(f"**P{p.get('index')}** · `{p.get('shot_type')}` · {status}")
                    if p.get("path") and Path(p["path"]).exists():
                        st.image(p["path"], use_container_width=True)
                    st.caption(p.get("dialogue") or p.get("action") or "")
                    edit = st.text_input("Edit note", key=f"edit_{p.get('index')}", placeholder="optional tweak")
                    if st.button("Regen", key=f"regen_{p.get('index')}", use_container_width=True):
                        if not run_dir:
                            st.error("Missing run dir")
                        else:
                            with st.spinner(f"Regenerating panel {p.get('index')}…"):
                                try:
                                    updated = regenerate_one(
                                        router(),
                                        settings,
                                        bible,
                                        p,
                                        run_dir,
                                        edit_notes=edit,
                                    )
                                except Exception as e:  # noqa: BLE001
                                    st.error(str(e))
                                    st.stop()
                            # Replace in all_panels
                            new_list = []
                            for old in st.session_state.all_panels:
                                if old.get("index") == updated.get("index"):
                                    new_list.append(updated)
                                else:
                                    new_list.append(old)
                            st.session_state.all_panels = new_list
                            if step == "pilot":
                                st.session_state.pilot_panels = [
                                    x for x in new_list if int(x.get("index", 0)) <= 5
                                ]
                            st.rerun()

    st.divider()
    a, b, c = st.columns(3)
    with a:
        if step == "pilot" and st.button("Looks good — continue", type="primary", use_container_width=True):
            st.session_state.step = "continue"
            st.rerun()
    with b:
        if step == "continue" and st.button("Generate next 5", type="primary", use_container_width=True):
            if not run_dir:
                st.error("Missing run dir")
            else:
                start = max(int(p.get("index", 0)) for p in panels) + 1 if panels else 1
                with st.spinner("Generating next batch…"):
                    try:
                        batch = generate_batch(
                            router(),
                            settings,
                            bible,
                            st.session_state.transcript,
                            run_dir,
                            start_index=start,
                            count=int(settings.get("pilot", {}).get("batch_size", 5)),
                        )
                    except Exception as e:  # noqa: BLE001
                        st.error(str(e))
                        st.stop()
                st.session_state.all_panels = panels + batch["panels"]
                st.session_state.sequence = batch.get("sequence")
                st.rerun()
    with c:
        if run_dir and panels and st.button("Export ZIP", use_container_width=True):
            zpath = export_zip(run_dir, panels)
            st.download_button(
                "Download storyboard.zip",
                data=zpath.read_bytes(),
                file_name="storyboard.zip",
                mime="application/zip",
                use_container_width=True,
            )

    if st.button("Start over"):
        for k, v in DEFAULTS.items():
            st.session_state[k] = v
        st.rerun()
