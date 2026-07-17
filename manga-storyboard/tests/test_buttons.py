"""Button smoke loop — every primary Streamlit control is clicked under mock mode
and asserted to drive the state/side effect it is wired to."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from tests.conftest import APP_PATH, make_analysis


def _app() -> AppTest:
    return AppTest.from_file(APP_PATH, default_timeout=30)


def _button(at: AppTest, label: str):
    matches = [b for b in at.button if b.label == label]
    assert matches, f"button not found: {label!r} (have: {[b.label for b in at.button]})"
    return matches[0]


def _click(at: AppTest, label: str) -> AppTest:
    _button(at, label).click()
    return at.run()


def _to_brief(at: AppTest) -> AppTest:
    at.run()
    at.text_area[0].input("PAGE 1\nPanel 1: rooftop standoff between Kaito and Ren")
    return _click(at, "Analyze script")


def _to_pilot(at: AppTest) -> AppTest:
    at = _to_brief(at)
    return _click(at, "Generate 5-panel pilot")


def test_password_gate_enter_button(patched_app, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "sesame")
    at = _app()
    at.run()
    assert not at.session_state["authed"]

    at.text_input[0].input("wrong")
    at = _click(at, "Enter")
    assert not at.session_state["authed"]

    at.text_input[0].input("sesame")
    at = _click(at, "Enter")
    assert at.session_state["authed"]


def test_analyze_script_button(patched_app):
    at = _to_brief(_app())
    assert at.session_state["step"] == "brief"
    assert at.session_state["analysis"]["summary"].startswith("Two rivals")


def test_analyze_script_warns_without_input(patched_app):
    at = _app()
    at.run()
    at = _click(at, "Analyze script")
    assert at.session_state["step"] == "intake"
    assert any("Upload a PDF/TXT or paste a script." in w.value for w in at.warning)


def test_submit_answers_and_skip_buttons(patched_app, monkeypatch):
    import pipeline.analyze as analyze_mod

    monkeypatch.setattr(
        analyze_mod,
        "analyze_transcript",
        lambda router, transcript, aesthetic: make_analysis(questions=True),
    )
    at = _to_brief(_app())
    assert at.session_state["qa_round"] == 0

    at = _click(at, "Submit answers")
    assert at.session_state["qa_round"] == 1

    # Fresh app: questions again, this time skip
    at2 = _to_brief(_app())
    at2 = _click(at2, "Skip to pilot")
    assert at2.session_state["analysis"]["ready"] is True


def test_generate_pilot_button(patched_app):
    at = _to_pilot(_app())
    assert at.session_state["step"] == "pilot"
    assert len(at.session_state["all_panels"]) == 5
    assert at.session_state["run_dir"] == str(patched_app.run_dir)


def test_back_to_intake_button(patched_app):
    at = _to_brief(_app())
    at = _click(at, "Back to intake")
    assert at.session_state["step"] == "intake"
    assert at.session_state["analysis"] is None


def test_select_pilot_and_clear_buttons(patched_app):
    at = _to_pilot(_app())
    at = _click(at, "Select pilot")
    assert at.session_state["selected_panels"] == [1, 2, 3, 4, 5]

    at = _click(at, "Clear selection")
    assert at.session_state["selected_panels"] == []


def test_panel_select_checkbox(patched_app):
    at = _to_pilot(_app())
    boxes = [c for c in at.checkbox if c.key == "sel_2"]
    assert boxes, "panel select checkbox sel_2 missing"
    boxes[0].check()
    at = at.run()
    assert at.session_state["selected_panels"] == [2]


def test_continue_and_back_buttons(patched_app):
    at = _to_pilot(_app())
    at = _click(at, "Looks good — continue")
    assert at.session_state["step"] == "continue"

    at = _click(at, "Back to pilot")
    assert at.session_state["step"] == "pilot"


def test_generate_still_requires_one_selection(patched_app):
    at = _to_pilot(_app())
    at = _click(at, "Generate")  # source defaults to "Selected panels", none selected
    assert "Select exactly one panel" in (at.session_state["create_error"] or "")


def test_generate_still_regenerates_selected_panel(patched_app):
    at = _to_pilot(_app())
    at = _click(at, "Select pilot")
    at = _click(at, "Clear selection")
    box = [c for c in at.checkbox if c.key == "sel_1"][0]
    box.check()
    at = at.run()
    at = _click(at, "Generate")
    result = at.session_state["create_result"]
    assert result and result["type"] == "still" and result["panel_indexes"] == [1]
    assert at.session_state["create_error"] is None


def test_accept_regenerate_edit_buttons(patched_app):
    at = _to_pilot(_app())
    panel_path = at.session_state["all_panels"][0]["path"]
    seed = {
        "output_id": "still_1",
        "type": "still",
        "panel_indexes": [1],
        "path": panel_path,
        "qa": {"pass": False, "score": 0.5, "issues": ["off-model"], "rewrite_notes": "add Kaito"},
        "accepted": False,
    }

    at.session_state["create_result"] = dict(seed)
    at = at.run()
    at = _click(at, "Accept")
    assert at.session_state["create_result"]["accepted"] is True

    at.session_state["create_result"] = dict(seed)
    at = at.run()
    at = _click(at, "Regenerate")  # applies QA note + auto re-runs Generate once
    result = at.session_state["create_result"]
    assert result and result["type"] == "still"
    assert at.session_state["create_direction"] == "add Kaito"

    at.session_state["create_result"] = dict(seed)
    at = at.run()
    at = _click(at, "Edit direction")
    assert at.session_state["create_result"] is None
    assert at.session_state["create_auto_generate"] is False


def test_export_zip_button(patched_app):
    at = _to_pilot(_app())
    at = _click(at, "Export ZIP")
    zip_path = at.session_state["export_zip_path"]
    assert zip_path and zip_path.endswith("storyboard.zip")


def test_start_over_button(patched_app):
    at = _to_pilot(_app())
    at = _click(at, "Start over")
    assert at.session_state["step"] == "intake"
    assert at.session_state["all_panels"] == []
    assert at.session_state["run_dir"] is None
