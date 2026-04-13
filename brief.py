#!/usr/bin/env python3
"""
equity-brief: Generate a structured equity research brief for a stock ticker.

Usage:
    python brief.py MC.PA
    python brief.py AAPL
"""

import re
import sys

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, validate_keys
from data.fetcher import fetch_all
from data.formatter import build_markdown


# ---------------------------------------------------------------------------
# Ticker validation
# ---------------------------------------------------------------------------

# Accepts formats like AAPL, MC.PA, BRK.B, 7203.T, RDSA.AS
_TICKER_RE = re.compile(r"^[A-Z0-9]{1,10}(\.[A-Z]{1,3})?$", re.IGNORECASE)


def validate_ticker(ticker: str) -> str:
    cleaned = ticker.strip().upper()
    if not _TICKER_RE.match(cleaned):
        print(
            f"Error: '{ticker}' does not look like a valid ticker symbol. "
            "Expected format: AAPL, MC.PA, 7203.T, etc.",
            file=sys.stderr,
        )
        sys.exit(1)
    return cleaned


# ---------------------------------------------------------------------------
# Claude verdict
# ---------------------------------------------------------------------------

def generate_verdict(ticker: str, data: dict) -> str:
    if not ANTHROPIC_API_KEY:
        return "N/A (ANTHROPIC_API_KEY not set)"

    snap = data.get("snapshot") or {}
    analyst = data.get("analyst") or {}
    margins = data.get("margins") or []
    earnings = data.get("earnings") or []

    summary_lines = [
        f"Ticker: {ticker}",
        f"Current Price: {snap.get('current_price', 'N/A')}",
        f"Market Cap: {snap.get('market_cap', 'N/A')}",
        f"P/E: {snap.get('pe_ratio', 'N/A')}",
        f"EV/EBITDA: {snap.get('ev_ebitda', 'N/A')}",
        f"P/S: {snap.get('ps_ratio', 'N/A')}",
        f"P/B: {snap.get('pb_ratio', 'N/A')}",
        f"52W Range: {snap.get('week52_low', 'N/A')} - {snap.get('week52_high', 'N/A')}",
        f"Analyst consensus — Buy: {analyst.get('buy', 'N/A')}, Hold: {analyst.get('hold', 'N/A')}, Sell: {analyst.get('sell', 'N/A')}",
        f"Median price target: {analyst.get('median_price_target', 'N/A')} (upside: {analyst.get('upside_pct', 'N/A')}%)",
    ]
    if margins:
        m = margins[0]
        summary_lines.append(
            f"Latest year margins — Gross: {m.get('gross_margin', 'N/A')}%, "
            f"Operating: {m.get('operating_margin', 'N/A')}%, "
            f"Net: {m.get('net_margin', 'N/A')}%"
        )
    if earnings:
        q = earnings[0]
        summary_lines.append(
            f"Most recent quarter — Revenue YoY: {q.get('revenue_yoy', 'N/A')}%, "
            f"Net Income YoY: {q.get('net_income_yoy', 'N/A')}%"
        )

    prompt_content = (
        f"You are a sell-side analyst. Given this data for {ticker}, write exactly one sentence "
        "(under 30 words) summarizing the investment case. Be direct. No hedging.\n\n"
        + "\n".join(summary_lines)
    )

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=80,
            messages=[{"role": "user", "content": prompt_content}],
        )
        return message.content[0].text.strip()
    except Exception as exc:
        print(f"Warning: Claude API error — {exc}", file=sys.stderr)
        return "N/A (Claude API error)"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python brief.py <TICKER>", file=sys.stderr)
        print("Example: python brief.py MC.PA", file=sys.stderr)
        sys.exit(1)

    raw_ticker = sys.argv[1]
    ticker = validate_ticker(raw_ticker)

    validate_keys()

    print(f"Fetching data for {ticker}...")
    data = fetch_all(ticker)

    print("Generating one-line verdict via Claude...")
    verdict = generate_verdict(ticker, data)

    print("Building markdown report...")
    markdown = build_markdown(data, verdict)

    output_file = f"{ticker}_brief.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"Report written to: {output_file}")


if __name__ == "__main__":
    main()
