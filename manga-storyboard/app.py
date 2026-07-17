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
from pipeline.tokens import load_usage, record_image, record_video, summarize_usage
from pipeline.video import (
    VideoGenError,
    check_video_job,
    download_video,
    save_output_record,
    submit_selected_clip,
)
from pipeline.video_qa import critique_video, save_qa
from pipeline.util import list_styles, load_settings, new_run_dir, save_json

APP_VERSION = "v5"

st.set_page_config(page_title=f"Manga Storyboard {APP_VERSION}", page_icon="📖", layout="wide")

# Load secrets/env before anything else that needs API keys
settings = load_settings()

# Ensure Desktop model folders exist (Nano Banana / Seedream / FLUX / …)
try:
    from pipeline.desktop_export import ensure_model_folders

    ensure_model_folders()
except Exception:
    pass

# Optional public-page lock (Streamlit Cloud secrets: APP_PASSWORD)
_app_password = __import__("os").environ.get("APP_PASSWORD", "").strip()
if _app_password:
    if "authed" not in st.session_state:
        st.session_state.authed = False
    if not st.session_state.authed:
        st.title(f"Manga Storyboard {APP_VERSION}")
        pw = st.text_input("Password", type="password")
        if st.button("Enter"):
            if pw == _app_password:
                st.session_state.authed = True
                st.rerun()
            st.error("Incorrect password.")
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
    "selected_panels": [],
    "create_source": "Selected panels",
    "create_output": "Still panels",
    "create_direction": "",
    "create_error": None,
    "create_job_meta": None,  # pending video submit metadata
    "create_result": None,    # latest still/video output review card
    "create_auto_generate": False,  # Regenerate should re-run Generate once
    "export_zip_path": None,
    "video_duration": 4,
    "video_aspect": "9:16",
    "video_motion": "subtle",
}


def init_state() -> None:
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v
    # Widget-owned keys (text_input/radio/checkbox) can only be written before
    # their widgets instantiate. Handlers that run after the widgets stage
    # values here; we apply them at the top of the next rerun.
    pending = st.session_state.pop("_widget_pending", None)
    if pending:
        for k, v in pending.items():
            st.session_state[k] = v


def _panel_indexes(panels: list) -> list[int]:
    return [int(p.get("index") or 0) for p in panels if p.get("index") is not None]


def _sync_selection_widgets(panels: list, indexes: list[int]) -> None:
    """Keep checkbox widget keys in sync with selected_panels (Streamlit ignores value= after first render)."""
    wanted = set(int(i) for i in indexes)
    for idx in _panel_indexes(panels):
        st.session_state[f"sel_{idx}"] = idx in wanted
    st.session_state.selected_panels = sorted(wanted)


def _pilot_indexes(panels: list) -> list[int]:
    pilot = st.session_state.get("pilot_panels") or []
    if pilot:
        return _panel_indexes(pilot)
    return [i for i in _panel_indexes(panels) if i <= 5] or _panel_indexes(panels)[:5]


def _clear_selection_widgets(panels: list | None = None) -> None:
    panels = panels if panels is not None else (st.session_state.get("all_panels") or [])
    for idx in _panel_indexes(panels):
        st.session_state[f"sel_{idx}"] = False
    # Also drop any orphaned sel_* keys from prior runs
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith("sel_"):
            st.session_state[key] = False
    st.session_state.selected_panels = []


def _reset_app_state() -> None:
    for k, v in DEFAULTS.items():
        st.session_state[k] = v if not isinstance(v, list) else list(v)
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith("sel_"):
            del st.session_state[key]


init_state()
styles = list_styles()
style_ids = [s["id"] for s in styles]


def router() -> DirectorRouter:
    run_dir = Path(st.session_state.run_dir) if st.session_state.get("run_dir") else None
    return DirectorRouter(settings, run_dir=run_dir)


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
    if st.button("Save to library", type="primary", use_container_width=True):
        if not uploads:
            st.warning("Choose one or more drawings first.")
        else:
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
        help="OFF = real panels (Nano Banana Pro → FLUX). ON = placeholder panels only.",
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

    profiles = (settings.get("models") or {}).get("image_profiles") or {}
    profile_ids = list(profiles.keys()) or ["nano_banana_flux"]
    current_profile = (settings.get("models") or {}).get("image_profile") or profile_ids[0]
    if current_profile not in profile_ids:
        current_profile = profile_ids[0]
    profile_labels = {
        "nano_banana_flux": "Nano Banana Pro → FLUX (fallback chain)",
        "anime_seedream": "Seedream 4.5 → FLUX (fallback chain)",
    }

    from pipeline.image_catalog import image_catalog, merge_catalog_with_live

    run_mode = st.radio(
        "Image run mode",
        ["Fallback chain", "Run all selected"],
        index=1 if (settings.get("models") or {}).get("image_run_mode") == "all_selected" else 0,
        help=(
            "Fallback chain: try one profile's models until one succeeds. "
            "Run all selected: generate with every checked model (Nano Banana + Seedream + …) "
            "and save each to its Desktop folder."
        ),
    )
    settings.setdefault("models", {})["image_run_mode"] = (
        "all_selected" if run_mode == "Run all selected" else "fallback"
    )

    if run_mode == "Run all selected":
        catalog = list(st.session_state.get("image_catalog_live") or image_catalog(settings))
        if not catalog:
            catalog = image_catalog(settings)
        id_to_label = {c["id"]: c["label"] for c in catalog}
        default_selected = list(
            (settings.get("models") or {}).get("image_models_selected")
            or [
                "google/gemini-3-pro-image",
                "bytedance-seed/seedream-4.5",
            ]
        )
        # Keep only ids that still exist in the catalog
        default_selected = [m for m in default_selected if m in id_to_label] or [catalog[0]["id"]]
        chosen_models = st.multiselect(
            "Models to run",
            options=[c["id"] for c in catalog],
            default=default_selected,
            format_func=lambda i: id_to_label.get(i, i),
            help="Each selected model gets its own prompt + Desktop folder copy.",
        )
        if not chosen_models:
            st.warning("Select at least one model — falling back to Nano Banana Pro.")
            chosen_models = ["google/gemini-3-pro-image"]
        settings.setdefault("models", {})["image_models_selected"] = chosen_models
        if st.button("Refresh OpenRouter image models", use_container_width=True):
            live = merge_catalog_with_live(settings)
            st.session_state.image_catalog_live = live
            st.success(f"Loaded {len(live)} image models.")
            st.rerun()
        st.caption(
            f"Will run {len(chosen_models)} model(s) per panel. "
            "Copies land in ~/Desktop/Manga Storyboard/<model>/."
        )
    else:
        chosen = st.selectbox(
            "Image model profile",
            profile_ids,
            index=profile_ids.index(current_profile),
            format_func=lambda i: profile_labels.get(i, i),
            help="Anime profile uses Seedream 4.5 for stronger stylized manga look.",
        )
        settings.setdefault("models", {})["image_profile"] = chosen
        settings.setdefault("models", {})["image_run_mode"] = "fallback"
        st.caption(f"Active: {profile_labels.get(chosen, chosen)}")
        st.caption(
            "Prompts are shaped for the chosen model. Finished panels auto-save to "
            "~/Desktop/Manga Storyboard/<Nano Banana|Seedream|FLUX>/."
        )

    st.divider()
    st.caption("Use the Create drawer on the filmstrip to make stills or video from selected panels.")

    if st.session_state.get("run_dir"):
        try:
            summary = summarize_usage(load_usage(Path(st.session_state.run_dir)), settings)
            st.markdown("**Run usage**")
            st.caption(
                f"~{summary['tokens']:,} tokens · {summary['images']} imgs · "
                f"{summary['videos']} videos · est ${summary['est_cost_usd']:.3f}"
            )
        except Exception:
            pass

    try:
        from pipeline.generate import IMAGE_PIPELINE_BUILD

        st.caption(f"{APP_VERSION} · Build: {IMAGE_PIPELINE_BUILD}")
    except Exception:
        st.caption(f"{APP_VERSION} · Build: (old — reboot the app)")


# ---------- Header ----------
st.title(f"Manga Storyboard {APP_VERSION}")
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
        brief["color_mode"] = st.selectbox(
            "Art color",
            ["full color", "black & white"],
            index=0 if (brief.get("color_mode") or "full color") == "full color" else 1,
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
            # Keep library / remembered characters; clear this script run
            st.session_state.step = "intake"
            st.session_state.analysis = None
            st.session_state.brief = None
            st.session_state.bible = None
            st.session_state.run_dir = None
            st.session_state.pilot_panels = []
            st.session_state.all_panels = []
            st.session_state.sequence = None
            st.session_state.qa_round = 0
            st.session_state.selected_panels = []
            st.session_state.create_error = None
            st.session_state.create_job_meta = None
            st.session_state.create_result = None
            st.session_state.create_auto_generate = False
            st.session_state.export_zip_path = None
            for key in list(st.session_state.keys()):
                if isinstance(key, str) and key.startswith("sel_"):
                    del st.session_state[key]
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
        q1, q2, q3 = st.columns(3)
        with q1:
            if st.button("Select pilot", use_container_width=True, help="Select the pilot panels (usually P1–P5)"):
                _sync_selection_widgets(panels, _pilot_indexes(panels))
                st.rerun()
        with q2:
            if st.button("Clear selection", use_container_width=True):
                _clear_selection_widgets(panels)
                st.rerun()
        with q3:
            selected_count = len(st.session_state.get("selected_panels") or [])
            st.caption(f"{selected_count} selected")

        # Initialize checkbox keys once from selected_panels, then let widget keys own the state
        for p in panels:
            idx = int(p.get("index") or 0)
            key = f"sel_{idx}"
            if key not in st.session_state:
                st.session_state[key] = idx in set(st.session_state.get("selected_panels") or [])

        for row_start in range(0, len(panels), 5):
            chunk = panels[row_start : row_start + 5]
            cols = st.columns(len(chunk))
            for col, p in zip(cols, chunk):
                idx = int(p.get("index") or 0)
                with col:
                    status = "needs review" if p.get("needs_review") else ("passed" if p.get("passed") else "check")
                    st.markdown(f"**P{idx}** · `{p.get('shot_type')}` · {status}")
                    if p.get("path") and Path(p["path"]).exists():
                        st.image(p["path"], use_container_width=True)
                    variants = [v for v in (p.get("variants") or []) if v.get("ok") and v.get("path")]
                    if len(variants) > 1:
                        with st.expander(f"All models ({len(variants)})", expanded=False):
                            vcols = st.columns(min(len(variants), 3))
                            for i, v in enumerate(variants):
                                with vcols[i % len(vcols)]:
                                    label = (v.get("model") or "").split("/")[-1]
                                    st.caption(label)
                                    if Path(v["path"]).exists():
                                        st.image(v["path"], use_container_width=True)
                    st.caption(p.get("dialogue") or p.get("action") or "")
                    st.checkbox("Select", key=f"sel_{idx}")

        st.session_state.selected_panels = sorted(
            idx for idx in _panel_indexes(panels) if st.session_state.get(f"sel_{idx}")
        )

    # Usage summary before Create so errors never hide spend
    if run_dir:
        try:
            summary = summarize_usage(load_usage(run_dir), settings)
            with st.expander("Run usage (tokens / cost estimate)", expanded=False):
                st.write(
                    f"**Tokens:** ~{summary['tokens']:,}  ·  **Images:** {summary['images']}  ·  "
                    f"**Videos:** {summary['videos']}  ·  **Est. cost:** ${summary['est_cost_usd']:.3f}"
                )
                if summary.get("by_role"):
                    st.caption("By role: " + ", ".join(f"{k}={v}" for k, v in summary["by_role"].items()))
        except Exception:
            pass

    # ---------- Create drawer (unified still + video) ----------
    st.divider()
    st.markdown("### Create")
    st.caption("Choose source → output → optional direction → Generate. Same review actions for stills and video.")

    c1, c2 = st.columns(2)
    with c1:
        source = st.radio(
            "Source",
            ["Selected panels", "Next story beat", "Custom note"],
            key="create_source",
            horizontal=True,
        )
    with c2:
        output = st.radio(
            "Output",
            ["Still panels", "Video clip"],
            key="create_output",
            horizontal=True,
        )

    direction = st.text_input(
        "Direction (optional)",
        key="create_direction",
        placeholder="e.g. close-up on the punch · animate only hair and camera push-in",
    )

    with st.expander("Advanced video options", expanded=False):
        vid_cfg = settings.get("video") or {}
        dur_opts = [4, 5, 6, 8]
        asp_opts = ["9:16", "16:9", "3:4"]
        mot_opts = ["subtle", "action", "camera pan", "zoom-in", "hold frame"]
        cur_dur = int(st.session_state.get("video_duration") or 4)
        cur_asp = st.session_state.get("video_aspect") or "9:16"
        cur_mot = st.session_state.get("video_motion") or "subtle"
        duration = st.selectbox(
            "Duration (sec)",
            dur_opts,
            index=dur_opts.index(cur_dur) if cur_dur in dur_opts else 0,
        )
        aspect = st.selectbox(
            "Aspect ratio",
            asp_opts,
            index=asp_opts.index(cur_asp) if cur_asp in asp_opts else 0,
        )
        motion = st.selectbox(
            "Motion style",
            mot_opts,
            index=mot_opts.index(cur_mot) if cur_mot in mot_opts else 0,
        )
        st.session_state.video_duration = int(duration)
        st.session_state.video_aspect = aspect
        st.session_state.video_motion = motion
        st.caption(f"Model: {vid_cfg.get('model', 'google/veo-3.1-lite')}")

    selected_idxs = st.session_state.get("selected_panels") or []
    if output == "Video clip" and len(selected_idxs) > 1:
        st.warning("Multi-panel video is less exact — single-panel animation is recommended.")
    if output == "Video clip" and source != "Selected panels":
        st.info("Video clips need selected panels as the source.")

    if st.session_state.get("create_error"):
        st.error(st.session_state.create_error)

    # Poll in-flight video job
    job_meta = st.session_state.get("create_job_meta")
    if job_meta and job_meta.get("job"):
        try:
            status = check_video_job(job_meta["job"])
        except VideoGenError as e:
            st.session_state.create_error = str(e)
            st.session_state.create_job_meta = None
            st.rerun()
        if status["status"] == "completed" and run_dir:
            out_id = job_meta.get("output_id", "clip")
            out = run_dir / "video" / f"output_{out_id}.mp4"
            try:
                vpath = download_video(status["url"], out)
                record_video(run_dir, 1)
                qa_cfg = (settings.get("video") or {}).get("qa") or {}
                qa = {"pass": True, "score": 1.0, "issues": [], "rewrite_notes": ""}
                if qa_cfg.get("enabled", True):
                    with st.spinner("Running video QA…"):
                        src_panels = [
                            p
                            for p in panels
                            if int(p.get("index", -1)) in set(job_meta.get("panel_indexes") or [])
                        ]
                        src_paths = [Path(p["path"]) for p in src_panels if p.get("path") and Path(p["path"]).exists()]
                        qa = critique_video(
                            router(),
                            bible,
                            src_panels,
                            vpath,
                            src_paths,
                            direction=job_meta.get("direction") or "",
                            pass_score=float(qa_cfg.get("pass_score", 0.65)),
                            expected_duration=float((settings.get("video") or {}).get("duration", 4)),
                        )
                        save_qa(run_dir, out_id, qa)
                record = {
                    "output_id": out_id,
                    "type": "video",
                    "panel_indexes": job_meta.get("panel_indexes"),
                    "prompt": job_meta.get("prompt"),
                    "model": job_meta.get("model"),
                    "path": str(vpath),
                    "direction": job_meta.get("direction"),
                    "qa": qa,
                    "accepted": False,
                }
                save_output_record(run_dir, record)
                st.session_state.create_result = record
            except Exception as e:  # noqa: BLE001
                st.session_state.create_error = f"Video finish failed: {e}"
            st.session_state.create_job_meta = None
            st.rerun()
        elif status["status"] in {"failed", "cancelled", "expired"}:
            st.session_state.create_error = f"Video job {status['status']}: {status.get('error', '')}"
            st.session_state.create_job_meta = None
            st.rerun()
        else:
            st.info(f"Video rendering… status: {status['status']}. This can take a few minutes.")
            import time as _time

            _time.sleep(5)
            st.rerun()

    # Review card for latest create result
    result = st.session_state.get("create_result")
    if result:
        st.markdown("#### Review")
        if result.get("accepted"):
            st.success("Accepted.")
        rtype = result.get("type")
        rpath = result.get("path") or ""
        if rtype == "video" and rpath and Path(rpath).exists():
            st.video(rpath)
        elif rtype == "still" and rpath and Path(rpath).exists():
            st.image(rpath, use_container_width=True)
        elif rtype == "still_batch":
            batch_idxs = set(int(i) for i in (result.get("panel_indexes") or []) if i is not None)
            batch_panels = [p for p in panels if int(p.get("index", -1)) in batch_idxs][:5]
            if batch_panels:
                bcols = st.columns(len(batch_panels))
                for col, p in zip(bcols, batch_panels):
                    with col:
                        if p.get("path") and Path(p["path"]).exists():
                            st.image(p["path"], use_container_width=True)
                        st.caption(f"P{p.get('index')}")
        qa = result.get("qa") or {}
        if qa.get("pass"):
            st.success(f"QA passed · score {qa.get('score', '—')}")
        else:
            st.warning(f"QA needs work · score {qa.get('score', '—')}")
        if qa.get("issues"):
            for issue in qa["issues"][:6]:
                st.caption(f"• {issue}")
        if qa.get("rewrite_notes"):
            st.caption(f"Suggested fix: {qa['rewrite_notes']}")

        r1, r2, r3 = st.columns(3)
        with r1:
            if st.button("Accept", type="primary", use_container_width=True, disabled=bool(result.get("accepted"))):
                result["accepted"] = True
                if run_dir:
                    save_output_record(run_dir, result)
                st.session_state.create_result = result
                st.rerun()
        with r2:
            if st.button("Regenerate", use_container_width=True, disabled=bool(job_meta)):
                # Pre-fill direction with QA notes and immediately re-run Generate.
                # These are widget-owned keys, so stage them for the next rerun.
                pending: dict = {}
                note = (qa.get("rewrite_notes") or "").strip()
                if note:
                    pending["create_direction"] = note
                st.session_state.create_result = None
                st.session_state.create_error = None

                def _stage_selection(indexes: list[int]) -> None:
                    wanted = set(int(i) for i in indexes)
                    for idx in _panel_indexes(panels):
                        pending[f"sel_{idx}"] = idx in wanted
                    st.session_state.selected_panels = sorted(wanted)

                if result.get("type") == "video":
                    pending["create_output"] = "Video clip"
                    pending["create_source"] = "Selected panels"
                    # Restore the panels that produced this clip
                    prior = [int(i) for i in (result.get("panel_indexes") or []) if i is not None]
                    if prior:
                        _stage_selection(prior)
                elif result.get("type") == "still":
                    pending["create_output"] = "Still panels"
                    pending["create_source"] = "Selected panels"
                    prior = [int(i) for i in (result.get("panel_indexes") or []) if i is not None]
                    if prior:
                        _stage_selection(prior)
                else:
                    # still_batch → make another next-beat batch
                    pending["create_output"] = "Still panels"
                    pending["create_source"] = "Next story beat"
                st.session_state._widget_pending = pending
                st.session_state.create_auto_generate = True
                st.rerun()
        with r3:
            if st.button("Edit direction", use_container_width=True):
                st.session_state.create_result = None
                st.session_state.create_auto_generate = False
                st.rerun()

    do_generate = st.button(
        "Generate",
        type="primary",
        use_container_width=True,
        disabled=bool(job_meta),
    ) or bool(st.session_state.get("create_auto_generate"))

    if do_generate:
        st.session_state.create_auto_generate = False
        st.session_state.create_error = None
        st.session_state.create_result = None
        # Re-read controls after Regenerate may have rewritten them
        source = st.session_state.get("create_source", source)
        output = st.session_state.get("create_output", output)
        direction = st.session_state.get("create_direction", direction)
        selected_idxs = st.session_state.get("selected_panels") or []
        duration = int(st.session_state.get("video_duration") or duration)
        aspect = st.session_state.get("video_aspect") or aspect
        motion = st.session_state.get("video_motion") or motion

        if not run_dir:
            st.session_state.create_error = "Missing run dir"
            st.rerun()

        # ---- Still panels ----
        if output == "Still panels":
            if source == "Selected panels":
                if len(selected_idxs) != 1:
                    st.session_state.create_error = "Select exactly one panel to regenerate as a still."
                    st.rerun()
                panel = next((p for p in panels if int(p.get("index", -1)) == selected_idxs[0]), None)
                if not panel:
                    st.session_state.create_error = "Selected panel not found."
                    st.rerun()
                with st.spinner(f"Regenerating panel {selected_idxs[0]}…"):
                    try:
                        updated = regenerate_one(
                            router(),
                            settings,
                            bible,
                            panel,
                            run_dir,
                            edit_notes=direction,
                        )
                    except Exception as e:  # noqa: BLE001
                        st.session_state.create_error = str(e)
                        st.rerun()
                new_list = [
                    updated if old.get("index") == updated.get("index") else old
                    for old in st.session_state.all_panels
                ]
                st.session_state.all_panels = new_list
                if step == "pilot":
                    st.session_state.pilot_panels = [x for x in new_list if int(x.get("index", 0)) <= 5]
                st.session_state.create_result = {
                    "output_id": f"still_{selected_idxs[0]}",
                    "type": "still",
                    "panel_indexes": selected_idxs,
                    "path": updated.get("path"),
                    "qa": (updated.get("critique") or {"pass": updated.get("passed"), "score": None, "issues": []}),
                    "accepted": False,
                }
                st.rerun()
            else:
                # Next story beat or custom note → generate next batch
                start = max(int(p.get("index", 0)) for p in panels) + 1 if panels else 1
                transcript = st.session_state.transcript
                if source == "Custom note" and direction.strip():
                    transcript = f"{transcript}\n\nDIRECTOR NOTE FOR NEXT PANELS: {direction.strip()}"
                count = int(settings.get("pilot", {}).get("batch_size", 5))
                with st.spinner(f"Generating {count} still panels…"):
                    try:
                        batch = generate_batch(
                            router(),
                            settings,
                            bible,
                            transcript,
                            run_dir,
                            start_index=start,
                            count=count,
                        )
                    except Exception as e:  # noqa: BLE001
                        st.session_state.create_error = str(e)
                        st.rerun()
                st.session_state.all_panels = panels + batch["panels"]
                st.session_state.sequence = batch.get("sequence")
                st.session_state.create_result = {
                    "output_id": f"batch_{start}",
                    "type": "still_batch",
                    "panel_indexes": [p.get("index") for p in batch["panels"]],
                    "qa": {"pass": True, "score": 1.0, "issues": [], "rewrite_notes": ""},
                    "accepted": False,
                }
                st.rerun()

        # ---- Video clip ----
        else:
            if source != "Selected panels" or not selected_idxs:
                st.session_state.create_error = "Select one or more panels to animate."
                st.rerun()
            src_panels = [p for p in panels if int(p.get("index", -1)) in set(selected_idxs)]
            panel_paths = [Path(p["path"]) for p in src_panels if p.get("path") and Path(p["path"]).exists()]
            if not panel_paths:
                st.session_state.create_error = "Selected panels have no image files on disk."
                st.rerun()
            try:
                meta = submit_selected_clip(
                    settings,
                    bible,
                    src_panels,
                    panel_paths,
                    direction=direction,
                    motion_style=motion,
                    duration=int(duration),
                    aspect_ratio=aspect,
                )
                st.session_state.create_job_meta = meta
            except VideoGenError as e:
                st.session_state.create_error = str(e)
            except Exception as e:  # noqa: BLE001
                st.session_state.create_error = f"Video submit failed: {e}"
            st.rerun()

    st.divider()
    nav1, nav2, nav3 = st.columns(3)
    with nav1:
        if step == "pilot" and st.button("Looks good — continue", use_container_width=True):
            st.session_state.step = "continue"
            st.rerun()
        elif step == "continue":
            if st.button("Back to pilot", use_container_width=True):
                st.session_state.step = "pilot"
                st.rerun()
    with nav2:
        if run_dir and panels and st.button("Export ZIP", use_container_width=True):
            zpath = export_zip(run_dir, panels)
            st.session_state.export_zip_path = str(zpath)
            st.rerun()
        zip_path = st.session_state.get("export_zip_path")
        if zip_path and Path(zip_path).exists():
            st.download_button(
                "Download storyboard.zip",
                data=Path(zip_path).read_bytes(),
                file_name="storyboard.zip",
                mime="application/zip",
                use_container_width=True,
            )
    with nav3:
        if st.button("Start over", use_container_width=True):
            _reset_app_state()
            st.rerun()
