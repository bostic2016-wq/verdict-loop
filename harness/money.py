"""Deterministic money/tax helpers so models don't invent take-home pay."""

from __future__ import annotations

import re
from typing import Any


_MONEY_RE = re.compile(
    r"(?<!\w)(?:\$|USD\s*)?\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\s*[kK])?",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(
    r"(\d{1,2}(?:\.\d+)?)\s*%|\b(\d{1,2}(?:\.\d+)?)\s*percent\b",
    re.IGNORECASE,
)
_GROSS_HINT = re.compile(
    r"\b(gross|salary|income|earn|make|making|pay|paid|wages|before[\s-]?tax)\b",
    re.IGNORECASE,
)
_NET_HINT = re.compile(
    r"\b(net|take[\s-]?home|after[\s-]?tax|post[\s-]?tax)\b",
    re.IGNORECASE,
)
_TAX_HINT = re.compile(
    r"\b(tax|effective\s+rate|withholding|bracket)\b",
    re.IGNORECASE,
)
_MONTH_HINT = re.compile(r"\b(month|monthly|/mo|per month)\b", re.IGNORECASE)


def _parse_amount(token: str) -> float | None:
    text = token.strip().lower().replace(",", "").replace("$", "").replace("usd", "")
    text = text.strip()
    if not text:
        return None
    mult = 1.0
    if text.endswith("k"):
        mult = 1000.0
        text = text[:-1].strip()
    try:
        return float(text) * mult
    except ValueError:
        return None


def _fmt_money(n: float) -> str:
    if abs(n - round(n)) < 0.005:
        return f"${n:,.0f}"
    return f"${n:,.2f}"


def extract_amounts(claim: str) -> list[float]:
    found: list[float] = []
    for m in _MONEY_RE.finditer(claim):
        token = m.group(0)
        digits = re.sub(r"[^\d]", "", token)
        if re.fullmatch(r"20\d{2}", digits):
            continue
        val = _parse_amount(token)
        if val is None or val <= 0:
            continue
        if val < 100 and "$" not in token and "k" not in token.lower():
            continue
        found.append(val)
    out: list[float] = []
    for v in found:
        if not any(abs(v - x) < 0.01 for x in out):
            out.append(v)
    return out


def extract_percents(claim: str) -> list[float]:
    out: list[float] = []
    for m in _PERCENT_RE.finditer(claim):
        raw = m.group(1) or m.group(2)
        try:
            p = float(raw)
        except ValueError:
            continue
        if 0 < p < 100:
            out.append(p)
    dedup: list[float] = []
    for p in out:
        if not any(abs(p - x) < 0.01 for x in dedup):
            dedup.append(p)
    return dedup


def analyze_money(claim: str) -> dict[str, Any]:
    """Build verified math from numbers stated in the claim."""
    amounts = extract_amounts(claim)
    percents = extract_percents(claim)
    has_gross = bool(_GROSS_HINT.search(claim)) or bool(amounts)
    has_net = bool(_NET_HINT.search(claim))
    has_tax = bool(_TAX_HINT.search(claim)) or bool(percents)
    monthly = bool(_MONTH_HINT.search(claim))

    calculations: list[str] = []
    assumptions: list[str] = []
    missing: list[str] = []
    primary_gross: float | None = None
    tax_rate: float | None = None
    net: float | None = None
    per_amount: list[dict[str, float]] = []

    # Prefer the first salary-like amount as "current", not always the max
    # (e.g. "$85k now vs $95k offer" should not treat 95k as the only gross).
    if amounts:
        primary_gross = amounts[0]
        if monthly:
            calculations.append(
                f"Monthly figures detected — annualizing each amount ×12."
            )
            amounts = [a * 12 for a in amounts]
            primary_gross = amounts[0]

    if percents and (has_tax or has_gross):
        tax_rate = percents[0] / 100.0
        assumptions.append(
            f"Using {percents[0]:g}% as the effective tax rate from your message."
        )

    if amounts and tax_rate is not None:
        for gross in amounts:
            take_home = gross * (1.0 - tax_rate)
            tax_paid = gross - take_home
            per_amount.append({"gross": gross, "net": take_home, "tax": tax_paid})
            calculations.append(
                f"Gross {_fmt_money(gross)} − tax at {tax_rate * 100:g}% "
                f"({_fmt_money(tax_paid)}) = after-tax {_fmt_money(take_home)}/yr "
                f"(~{_fmt_money(take_home / 12)}/mo)."
            )
        # Primary = first amount (usually "I make X")
        primary_gross = amounts[0]
        net = per_amount[0]["net"]
        if len(per_amount) >= 2:
            delta = per_amount[1]["net"] - per_amount[0]["net"]
            sign = "more" if delta >= 0 else "less"
            calculations.append(
                f"Difference in after-tax pay (2nd vs 1st amount): "
                f"{_fmt_money(abs(delta))}/yr {sign} "
                f"(~{_fmt_money(abs(delta) / 12)}/mo)."
            )
    elif primary_gross is not None and has_net and len(amounts) >= 2:
        candidate_net = min(amounts)
        if candidate_net < primary_gross:
            implied = 1.0 - (candidate_net / primary_gross)
            net = candidate_net
            tax_rate = implied
            calculations.append(
                f"Numbers consistent with gross {_fmt_money(primary_gross)} and "
                f"after-tax {_fmt_money(candidate_net)} "
                f"(implied effective tax {implied * 100:.1f}%)."
            )
    elif primary_gross is not None:
        missing.append(
            "No tax rate given — cannot compute a single accurate after-tax figure."
        )
        for gross in amounts[:3]:
            for label, rate in (("low", 0.20), ("mid", 0.28), ("high", 0.35)):
                est = gross * (1 - rate)
                calculations.append(
                    f"ESTIMATE only for {_fmt_money(gross)} "
                    f"({label} {rate * 100:.0f}% effective tax): "
                    f"after-tax ≈ {_fmt_money(est)}/yr (~{_fmt_money(est / 12)}/mo)."
                )
        assumptions.append(
            "Estimate scenarios use flat effective rates (20/28/35%). "
            "Real take-home depends on filing status, state, deductions, FICA, etc."
        )
        missing.append(
            "Ask for filing status + state, or an effective tax % / paystub net."
        )

    return {
        "amounts": amounts,
        "percents": percents,
        "gross": primary_gross,
        "tax_rate": tax_rate,
        "net": net,
        "per_amount": per_amount,
        "calculations": calculations,
        "assumptions": assumptions,
        "missing": missing,
        "has_money_signal": bool(amounts) or has_net or has_tax,
    }


def format_money_block(facts: dict[str, Any]) -> str:
    if not facts or not facts.get("has_money_signal"):
        return ""
    lines = [
        "VERIFIED MONEY MATH (deterministic calculator — do NOT invent different "
        "after-tax numbers; if something is missing, say so):",
    ]
    if facts.get("gross") is not None:
        lines.append(f"- Gross income used: {_fmt_money(float(facts['gross']))}/yr")
    if facts.get("tax_rate") is not None and facts.get("net") is not None:
        lines.append(f"- Effective tax rate used: {float(facts['tax_rate']) * 100:g}%")
        lines.append(f"- After-tax income: {_fmt_money(float(facts['net']))}/yr")
    for c in facts.get("calculations") or []:
        lines.append(f"- {c}")
    for a in facts.get("assumptions") or []:
        lines.append(f"- Assumption: {a}")
    for m in facts.get("missing") or []:
        lines.append(f"- MISSING: {m}")
    lines.append(
        "- Never invent a single after-tax figure when MISSING lists a tax rate. "
        "Use ESTIMATE lines or ask for the rate / paystub."
    )
    return "\n".join(lines)


def attach_money_context(claim: str) -> tuple[str, dict[str, Any]]:
    facts = analyze_money(claim)
    block = format_money_block(facts)
    if not block:
        return claim, facts
    return f"{claim.strip()}\n\n{block}", facts
