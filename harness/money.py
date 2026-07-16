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
_DEBT_HINT = re.compile(
    r"\b(debt|credit\s*card|card\s*balance|apr|interest(?:\s*rate)?|loan|owes?|owed|"
    r"balance\s*transfer|pay\s*(?:off|down)|payoff|mortgage|refinanc\w*|principal)\b",
    re.IGNORECASE,
)
_INCOME_WORD = re.compile(
    r"\b(gross|salary|income|earn(?:ing)?s?|wages?|paycheck|comp(?:ensation)?|"
    r"before[\s-]?tax|take[\s-]?home|after[\s-]?tax)\b",
    re.IGNORECASE,
)
_DEBT_RATE_NEAR = re.compile(r"\bapr\b|interest|cash\s*back|rewards?|match", re.IGNORECASE)


def _tax_percents(claim: str) -> list[float]:
    """Percents usable as a tax rate — skip ones sitting next to APR/interest words."""
    out: list[float] = []
    for m in _PERCENT_RE.finditer(claim):
        window = claim[max(0, m.start() - 40) : m.end() + 40]
        if _DEBT_RATE_NEAR.search(window):
            continue
        raw = m.group(1) or m.group(2)
        try:
            p = float(raw)
        except ValueError:
            continue
        if 0 < p < 100 and not any(abs(p - x) < 0.01 for x in out):
            out.append(p)
    return out


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
    debt_context = bool(_DEBT_HINT.search(claim))
    income_context = bool(_INCOME_WORD.search(claim))
    # In debt/APR contexts, a bare dollar amount is a balance, not a salary.
    has_gross = bool(_GROSS_HINT.search(claim)) or (bool(amounts) and not debt_context)
    has_net = bool(_NET_HINT.search(claim))
    tax_percents = _tax_percents(claim)
    has_tax = bool(_TAX_HINT.search(claim)) or bool(tax_percents)
    monthly = bool(_MONTH_HINT.search(claim))

    calculations: list[str] = []
    assumptions: list[str] = []
    missing: list[str] = []
    primary_gross: float | None = None
    tax_rate: float | None = None
    net: float | None = None
    per_amount: list[dict[str, float]] = []

    if debt_context and not income_context:
        # Debt/APR question: report figures as stated; never invent take-home pay.
        for a in amounts:
            calculations.append(f"Figure stated in question: {_fmt_money(a)}.")
        for p in percents:
            calculations.append(f"Rate stated in question: {p:g}% (APR/interest, not a tax rate).")
        if len(amounts) >= 1 and percents:
            bal = amounts[0]
            apr = percents[0] / 100.0
            yearly_interest = bal * apr
            calculations.append(
                f"If {_fmt_money(bal)} is a balance carried at {percents[0]:g}% APR, "
                f"interest ≈ {_fmt_money(yearly_interest)}/yr "
                f"(~{_fmt_money(yearly_interest / 12)}/mo), simple approximation."
            )
        assumptions.append(
            "This reads as a debt/interest question, so no salary or after-tax math applies."
        )
        return {
            "amounts": amounts,
            "percents": percents,
            "gross": None,
            "tax_rate": None,
            "net": None,
            "per_amount": [],
            "calculations": calculations,
            "assumptions": assumptions,
            "missing": missing,
            "has_money_signal": bool(amounts) or bool(percents),
        }

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

    if tax_percents and (has_tax or has_gross):
        tax_rate = tax_percents[0] / 100.0
        assumptions.append(
            f"Using {tax_percents[0]:g}% as the effective tax rate from your message."
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


_AFTER_TAX_SENT = re.compile(
    r"\b(after[\s-]?tax|take[\s-]?home|net\s+(?:pay|income)|post[\s-]?tax)\b",
    re.IGNORECASE,
)


def _allowed_figures(facts: dict[str, Any]) -> set[float]:
    """Every dollar figure a draft may legitimately state, incl. monthly variants."""
    vals: set[float] = set()

    def _add(v: Any) -> None:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return
        if f > 0:
            vals.add(round(f, 2))
            vals.add(round(f / 12, 2))

    _add(facts.get("gross"))
    _add(facts.get("net"))
    for a in facts.get("amounts") or []:
        _add(a)
    for pa in facts.get("per_amount") or []:
        for key in ("gross", "net", "tax"):
            _add(pa.get(key))
        # differences between scenarios are fair game too
    per = facts.get("per_amount") or []
    if len(per) >= 2:
        _add(abs(per[1]["net"] - per[0]["net"]))
    # ESTIMATE scenarios (no tax rate given): flat 20/28/35% bands
    if facts.get("tax_rate") is None:
        for a in facts.get("amounts") or []:
            for rate in (0.20, 0.28, 0.35):
                _add(a * (1 - rate))
    return vals


def _matches(value: float, allowed: set[float]) -> bool:
    for a in allowed:
        if abs(value - a) <= max(2.0, a * 0.005):
            return True
    return False


def check_draft_numbers(draft: str, facts: dict[str, Any] | None) -> list[str]:
    """
    Deterministic gate: find after-tax/take-home dollar figures in the draft that
    conflict with the verified money math. Returns a list of issue strings.
    """
    if not draft or not facts or not facts.get("has_money_signal"):
        return []
    allowed = _allowed_figures(facts)
    issues: list[str] = []
    no_rate = facts.get("tax_rate") is None and facts.get("net") is None

    for sentence in re.split(r"(?<=[.!?])\s+|\n", draft):
        if not _AFTER_TAX_SENT.search(sentence):
            continue
        for amount in extract_amounts(sentence):
            if _matches(amount, allowed):
                continue
            if no_rate:
                issues.append(
                    f"Draft states an after-tax figure ({_fmt_money(amount)}) but no "
                    "tax rate was given — only labeled ESTIMATE bands are allowed."
                )
            else:
                issues.append(
                    f"Draft's after-tax figure {_fmt_money(amount)} does not match "
                    "the verified money math."
                )
    return issues


def attach_money_context(claim: str) -> tuple[str, dict[str, Any]]:
    facts = analyze_money(claim)
    block = format_money_block(facts)
    if not block:
        return claim, facts
    return f"{claim.strip()}\n\n{block}", facts
