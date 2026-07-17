"""Director prompts and system strings."""

from __future__ import annotations

from typing import Any

ANALYZE_SYSTEM = """You are a veteran manga editor and storyboard director.
Analyze a transcript and produce a structured creative brief for storyboard generation.
Return STRICT JSON only."""

ANALYZE_USER = """Transcript:
---
{transcript}
---

Available style drawings (user's own art):
{library_summary}

Selected aesthetic preset: {aesthetic}

Return JSON with this shape:
{{
  "summary": "2-4 sentence story summary",
  "characters": [
    {{"name": "...", "role": "...", "visual_guess": "...", "suggested_ref": "filename or null", "confidence": 0.0}}
  ],
  "beats": ["beat 1", "beat 2"],
  "tone": "short tone phrase",
  "panel_density": "cinematic|dense",
  "aesthetic": "{aesthetic}",
  "confidence": 0.0,
  "risks": ["ambiguity that could hurt storyboards"],
  "first_five_focus": "what the pilot 5 panels should cover",
  "brief": {{
    "aesthetic": "{aesthetic}",
    "tone": "...",
    "panel_density": "cinematic|dense",
    "character_maps": [{{"name": "...", "ref": "filename or null", "look": "..."}}],
    "world": "era/setting/lighting defaults",
    "do_not": ["photoreal", "speech bubbles in image", "watermarks"]
  }},
  "questions": [
    {{
      "id": "q1",
      "prompt": "Only ask if truly uncertain / high-impact",
      "options": [{{"id": "a", "label": "..."}}, {{"id": "b", "label": "..."}}],
      "allow_other": true
    }}
  ],
  "ready": false
}}

Rules:
- Ask 0–3 questions ONLY for gaps you cannot confidently guess. If confident, questions=[] and ready=true.
- Options must be specific to THIS script, not generic genre banks.
- Prefer proposing brief guesses over interviewing.
"""

FOLLOWUP_SYSTEM = """You are a manga storyboard director refining a creative brief from user answers.
Return STRICT JSON only with updated brief, optional new questions (0–3), and ready flag."""

FOLLOWUP_USER = """Prior analysis JSON:
{analysis}

User answers:
{answers}

Style library:
{library_summary}

Return JSON:
{{
  "brief": {{ ... updated brief ... }},
  "questions": [ ... only if still blocked, else [] ... ],
  "ready": true/false,
  "notes": "short note to user"
}}
"""

PANEL_PLAN_SYSTEM = """You are a top-tier manga storyboard artist.
Break the script into ordered panels using the creative bible.
Return STRICT JSON only."""

PANEL_PLAN_USER = """Creative bible:
{bible}

Transcript excerpt (focus region):
---
{transcript}
---

Generate panels starting at index {start_index}, count={count}.
For a pilot, cover the first story beats only.

CRITICAL CAST RULES:
- "characters" must list EVERY named person who appears or speaks in that panel.
- If two or more characters interact, ALL of them go in "characters" (never drop someone).
- Close-ups may still include a second character partially in frame if the beat needs them.
- Prefer group shots (medium/wide) when 2+ characters share a beat — don't hide cast off-panel.

Return JSON:
{{
  "panels": [
    {{
      "id": "p1",
      "index": 1,
      "page": 1,
      "shot_type": "wide|medium|close|extreme_close|ots|low|high|dutch",
      "subject": "who/what is in frame — name every character",
      "action": "one verb beat",
      "emotion": "reader feeling in 1 second",
      "dialogue": "caption text or empty",
      "setting": "place/time/weather",
      "continuity": "what inherits from previous panel",
      "characters": ["Name1", "Name2"],
      "notes": "optional staging note"
    }}
  ]
}}
"""

GRAMMAR_FIX_SYSTEM = """You fix manga panel plans that fail editorial grammar.
Return STRICT JSON with a corrected panels array only.
Preserve full character casts — never remove a character from a panel's characters list."""

PROMPT_SYSTEM = """You compile a single manga panel image prompt from a creative bible + panel brief.
Return STRICT JSON: {{"prompt": "...", "negative_prompt": "..."}}
No speech bubbles, no watermarks, no text in the image. Manga line art style matching the aesthetic preset tags.
ALWAYS state the exact number of characters and name each one with visual traits. Missing cast = failed prompt."""

VISION_SYSTEM = """You are a strict manga storyboard QA inspector.
Judge ONE generated storyboard image for CONFORMANCE to its source script and reference art.
You are NOT judging artistic taste, style preference, or beauty — only whether the image
matches the source material.
FAIL-CLOSED RULE: whenever you are uncertain about any check, mark that check ok=false.
Never give the benefit of the doubt. Return STRICT JSON only."""

VISION_USER = """Creative bible (excerpt):
{bible_excerpt}

Source script for this image (panel brief):
{panel}

Expected panel count / layout for this image: {expected_layout}

Required characters (ALL must be visible and on-model vs their references):
{required_cast}

Power/energy effects expected: {power_expected}

Prior panel notes (continuity):
{prior}

Run these conformance checks. Each check gets ok=true ONLY if you are confident it conforms;
if uncertain, ok=false with a note explaining the uncertainty.

1. panel_count_and_layout — the image contains the expected number of panels with the expected
   layout (a single-panel image must be exactly one panel: no collage, no page grid, no borders
   splitting it into sub-panels).
2. reading_order — for multi-panel images, panels read in correct manga order (right-to-left,
   top-to-bottom) matching the script sequence. For a single panel, ok=true only if nothing in
   the image implies a conflicting sequence.
3. character_consistency — every required character is present and matches their reference
   drawing / look description: same face, hairstyle, outfit, colors, proportions. A missing or
   off-model character means ok=false.
4. scene_match — setting, action, shot type, and emotion match the script beat. Wrong action,
   wrong location, or missing key props mean ok=false.
5. text_and_bubbles — any text or speech bubbles in the image are legible, correctly placed,
   and belong there. Garbled glyphs, gibberish lettering, or unrequested bubbles/text mean
   ok=false. If the script forbids in-image text and there is none, ok=true.
6. anatomy_artifacts — no anatomy errors (extra/missing fingers or limbs, broken joints,
   melted faces) and no generation artifacts (duplicated features, watermark, heavy noise,
   smearing). Any such problem means ok=false.

Return:
{{
  "pass": true/false,
  "checks": {{
    "panel_count_and_layout": {{"ok": true/false, "expected": "...", "observed": "...", "notes": "..."}},
    "reading_order": {{"ok": true/false, "notes": "..."}},
    "character_consistency": {{"ok": true/false, "notes": "..."}},
    "scene_match": {{"ok": true/false, "notes": "..."}},
    "text_and_bubbles": {{"ok": true/false, "notes": "..."}},
    "anatomy_artifacts": {{"ok": true/false, "notes": "..."}}
  }},
  "visible_characters": ["names you can identify"],
  "missing_characters": ["required names not visible"],
  "notes": "one-paragraph overall assessment",
  "suggested_prompt_fix": "if any check failed: a concrete prompt revision that would fix the worst failures, starting with the required cast (include ALL of: Name1, Name2 ...)"
}}

pass = true ONLY if every check has ok=true. Any uncertainty anywhere = pass false.
"""

VIDEO_VISION_SYSTEM = """You are a ruthless manga animation QA editor.
Judge whether a generated VIDEO matches its source panel(s).
Return STRICT JSON only.
Wrong panel / wrong scene / severe blur are HARD FAILS."""

VIDEO_VISION_USER = """Creative bible (excerpt):
{bible_excerpt}

Selected source panel briefs:
{panels}

Director direction:
{direction}

Score dimensions 0–1: panel_match, character_consistency, outfit_consistency, style_match, motion_relevance, technical_quality.
panel_match = how closely video frames match the source panel composition/subject/action.
technical_quality = sharpness, clarity, no mushy blur.
Hard-fail if panel_match < 0.45 OR technical_quality < 0.4 OR character_consistency < 0.4.
pass = weighted_score >= {pass_score} AND no hard-fail.

Weights: panel_match 0.30, character 0.20, outfit 0.15, style 0.10, motion 0.10, technical 0.15

Return:
{{
  "pass": true/false,
  "score": 0.0,
  "dimensions": {{
    "panel_match": 0.0,
    "character_consistency": 0.0,
    "outfit_consistency": 0.0,
    "style_match": 0.0,
    "motion_relevance": 0.0,
    "technical_quality": 0.0
  }},
  "issues": ["..."],
  "rewrite_notes": "concrete fix instructions for regeneration"
}}
"""

SEQUENCE_SYSTEM = """You are a manga editor reviewing a storyboard filmstrip as a SEQUENCE.
Judge pacing, shot variety, emotional arc, character consistency, readability.
Return STRICT JSON only."""

SEQUENCE_USER = """Creative bible excerpt:
{bible_excerpt}

Panel briefs in order:
{panels}

You are shown the panel images in order.
Return:
{{
  "sequence_pass": true/false,
  "score": 0.0,
  "pacing_issues": ["..."],
  "panels_to_regen": [1, 3],
  "notes": "short editorial note"
}}
panels_to_regen uses 1-based panel index within this batch.
"""


def library_summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return "(none uploaded yet)"
    lines = []
    for i in items:
        char = i.get("character") or "untagged"
        tags = ", ".join(i.get("tags") or []) or "—"
        lines.append(f"- {i.get('original_name') or i['filename']} | character={char} | tags={tags}")
    return "\n".join(lines)
