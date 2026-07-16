"""Starter claim templates for the Verdict Loop UI."""

from __future__ import annotations

TEMPLATES: list[dict[str, str]] = [
    {
        "id": "custom",
        "label": "Custom (blank)",
        "claim": "",
    },
    {
        "id": "side_hustle",
        "label": "Side hustle test",
        "claim": "Should I test a weekend side hustle for 4 weeks before deciding to scale it?",
    },
    {
        "id": "launch",
        "label": "Launch a product / newsletter",
        "claim": "Should I launch a simple paid newsletter this month for a niche audience I already know?",
    },
    {
        "id": "buy",
        "label": "Buy / don’t buy",
        "claim": "Should I buy this tool/equipment now, or wait 90 days and keep using what I have?",
    },
    {
        "id": "quit_stay",
        "label": "Quit or stay",
        "claim": "Should I leave my current job within 6 months to pursue this plan full-time?",
    },
    {
        "id": "hire",
        "label": "Hire help / DIY",
        "claim": "Should I hire help for this work, or keep doing it myself for the next quarter?",
    },
    {
        "id": "finance",
        "label": "Personal finance / take-home",
        "claim": (
            "I make $85,000 gross per year. Assuming a 28% effective tax rate, "
            "should I keep my current job or take a $95,000 offer in the same city?"
        ),
    },
]


def template_labels() -> list[str]:
    return [t["label"] for t in TEMPLATES]


def claim_for_label(label: str) -> str:
    for t in TEMPLATES:
        if t["label"] == label:
            return t["claim"]
    return ""
