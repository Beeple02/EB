"""
Converts the structured data dict from fetcher.py into markdown sections.
"""

from datetime import datetime


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_num(value, decimals=2):
    """Format a number with commas and fixed decimal places, or 'N/A'."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_pct(value, decimals=1):
    """Format a percentage value, or 'N/A'."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimals}f}%"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_large(value):
    """Format large numbers (market cap etc.) in billions/millions with 2dp."""
    if value is None:
        return "N/A"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if abs(v) >= 1e12:
        return f"{v / 1e12:,.2f}T"
    if abs(v) >= 1e9:
        return f"{v / 1e9:,.2f}B"
    if abs(v) >= 1e6:
        return f"{v / 1e6:,.2f}M"
    return f"{v:,.2f}"


def _fmt_period(period_str):
    """Turn '2024-03-31' into 'Q1 2024' style label where possible."""
    if not period_str:
        return "N/A"
    try:
        dt = datetime.strptime(period_str, "%Y-%m-%d")
        q = (dt.month - 1) // 3 + 1
        return f"Q{q} {dt.year}"
    except ValueError:
        return period_str


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def build_snapshot(snapshot: dict, ticker: str) -> str:
    s = snapshot
    lines = [
        f"## 1. Snapshot — {ticker}",
        "",
        f"| Metric            | Value                     |",
        f"|-------------------|---------------------------|",
        f"| Current Price     | {_fmt_num(s.get('current_price'))} |",
        f"| Market Cap        | {_fmt_large(s.get('market_cap'))} |",
        f"| P/E               | {_fmt_num(s.get('pe_ratio'))} |",
        f"| EV/EBITDA         | {_fmt_num(s.get('ev_ebitda'))} |",
        f"| P/S               | {_fmt_num(s.get('ps_ratio'))} |",
        f"| P/B               | {_fmt_num(s.get('pb_ratio'))} |",
        f"| 52-Week High      | {_fmt_num(s.get('week52_high'))} |",
        f"| 52-Week Low       | {_fmt_num(s.get('week52_low'))} |",
    ]
    return "\n".join(lines)


def build_earnings(earnings: list) -> str:
    if not earnings:
        return "## 2. Earnings Trend\n\nN/A"

    header = (
        "## 2. Earnings Trend\n\n"
        "| Quarter   | Revenue       | Net Income    | EPS Actual | EPS Est. | Rev YoY   | NI YoY    |\n"
        "|-----------|---------------|---------------|------------|----------|-----------|-----------|\n"
    )
    rows = []
    for q in earnings:
        rows.append(
            f"| {_fmt_period(q.get('period')):<9} "
            f"| {_fmt_large(q.get('revenue')):<13} "
            f"| {_fmt_large(q.get('net_income')):<13} "
            f"| {_fmt_num(q.get('eps_actual')):<10} "
            f"| {_fmt_num(q.get('eps_estimate')):<8} "
            f"| {_fmt_pct(q.get('revenue_yoy')):<9} "
            f"| {_fmt_pct(q.get('net_income_yoy')):<9} |"
        )
    return header + "\n".join(rows)


def build_margins(margins: list) -> str:
    if not margins:
        return "## 3. Margins\n\nN/A"

    header = (
        "## 3. Margins\n\n"
        "| Year   | Gross Margin | Operating Margin | Net Margin |\n"
        "|--------|--------------|------------------|------------|\n"
    )
    rows = []
    for m in margins:
        rows.append(
            f"| {str(m.get('period', 'N/A')):<6} "
            f"| {_fmt_pct(m.get('gross_margin')):<12} "
            f"| {_fmt_pct(m.get('operating_margin')):<16} "
            f"| {_fmt_pct(m.get('net_margin')):<10} |"
        )
    return header + "\n".join(rows)


def build_analyst(analyst: dict) -> str:
    a = analyst

    buy = a.get("buy")
    hold = a.get("hold")
    sell = a.get("sell")

    total = None
    if buy is not None and hold is not None and sell is not None:
        total = buy + hold + sell

    lines = [
        "## 4. Analyst Consensus",
        "",
        f"| Metric              | Value          |",
        f"|---------------------|----------------|",
        f"| Buy                 | {buy if buy is not None else 'N/A'} |",
        f"| Hold                | {hold if hold is not None else 'N/A'} |",
        f"| Sell                | {sell if sell is not None else 'N/A'} |",
        f"| Total Analysts      | {total if total is not None else 'N/A'} |",
        f"| Median Price Target | {_fmt_num(a.get('median_price_target'))} |",
        f"| Upside / Downside   | {_fmt_pct(a.get('upside_pct'))} |",
    ]
    return "\n".join(lines)


def build_catalysts(catalysts: list) -> str:
    if not catalysts:
        return "## 5. Recent Catalysts\n\nN/A"

    lines = ["## 5. Recent Catalysts", ""]
    for item in catalysts:
        date = item.get("date") or "N/A"
        headline = item.get("headline") or "N/A"
        lines.append(f"- **{date}** — {headline}")
    return "\n".join(lines)


def build_verdict(verdict: str) -> str:
    return f"## 6. One-Line Verdict\n\n{verdict}"


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------

def build_markdown(data: dict, verdict: str) -> str:
    ticker = data.get("ticker", "UNKNOWN")
    source_note = f"*Data source: {data.get('source', 'unknown')}*"
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    sections = [
        f"# Equity Brief: {ticker}",
        f"*Generated: {generated_at}*  ",
        source_note,
        "",
        build_snapshot(data.get("snapshot") or {}, ticker),
        "",
        build_earnings(data.get("earnings") or []),
        "",
        build_margins(data.get("margins") or []),
        "",
        build_analyst(data.get("analyst") or {}),
        "",
        build_catalysts(data.get("catalysts") or []),
        "",
        build_verdict(verdict),
    ]
    return "\n".join(sections) + "\n"
