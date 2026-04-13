#!/usr/bin/env python3
"""
equity-brief: Generate a structured equity research brief for a stock ticker.

Usage:
    python brief.py MC.PA
    python brief.py AAPL

LLM provider is selected automatically from whichever key is set:
    ANTHROPIC_API_KEY  → Claude (claude-sonnet-4-20250514)
    GROQ_API_KEY       → Llama 3.3 70B via Groq (free tier)
    GEMINI_API_KEY     → Gemini 1.5 Flash via Google (free tier)
    OPENROUTER_API_KEY → Llama 3.3 70B via OpenRouter (free tier)
"""

import re
import sys

from config import (
    ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
    GROQ_API_KEY, GROQ_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
    OPENROUTER_API_KEY, OPENROUTER_MODEL,
    active_llm_provider, validate_keys,
)
from data.fetcher import fetch_all
from data.formatter import build_markdown


# ---------------------------------------------------------------------------
# Ticker validation
# ---------------------------------------------------------------------------

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
# Verdict helpers per provider
# ---------------------------------------------------------------------------

def _build_prompt(ticker: str, data: dict) -> str:
    snap = data.get("snapshot") or {}
    analyst = data.get("analyst") or {}
    margins = data.get("margins") or []
    earnings = data.get("earnings") or []

    lines = [
        f"Ticker: {ticker}",
        f"Current Price: {snap.get('current_price', 'N/A')}",
        f"Market Cap: {snap.get('market_cap', 'N/A')}",
        f"P/E: {snap.get('pe_ratio', 'N/A')}",
        f"EV/EBITDA: {snap.get('ev_ebitda', 'N/A')}",
        f"P/S: {snap.get('ps_ratio', 'N/A')}",
        f"P/B: {snap.get('pb_ratio', 'N/A')}",
        f"52W Range: {snap.get('week52_low', 'N/A')} - {snap.get('week52_high', 'N/A')}",
        f"Analyst consensus — Buy: {analyst.get('buy', 'N/A')}, "
        f"Hold: {analyst.get('hold', 'N/A')}, Sell: {analyst.get('sell', 'N/A')}",
        f"Median price target: {analyst.get('median_price_target', 'N/A')} "
        f"(upside: {analyst.get('upside_pct', 'N/A')}%)",
    ]
    if margins:
        m = margins[0]
        lines.append(
            f"Latest year margins — Gross: {m.get('gross_margin', 'N/A')}%, "
            f"Operating: {m.get('operating_margin', 'N/A')}%, "
            f"Net: {m.get('net_margin', 'N/A')}%"
        )
    if earnings:
        q = earnings[0]
        lines.append(
            f"Most recent quarter — Revenue YoY: {q.get('revenue_yoy', 'N/A')}%, "
            f"Net Income YoY: {q.get('net_income_yoy', 'N/A')}%"
        )

    return (
        f"You are a sell-side analyst. Given this data for {ticker}, write exactly one sentence "
        "(under 30 words) summarizing the investment case. Be direct. No hedging.\n\n"
        + "\n".join(lines)
    )


def _verdict_anthropic(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=80,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def _verdict_groq(prompt: str) -> str:
    import requests
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": GROQ_MODEL, "max_tokens": 80, "messages": [{"role": "user", "content": prompt}]},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _verdict_gemini(prompt: str) -> str:
    import requests
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    r = requests.post(
        url,
        params={"key": GEMINI_API_KEY},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def _verdict_openrouter(prompt: str) -> str:
    import requests
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
        json={"model": OPENROUTER_MODEL, "max_tokens": 80, "messages": [{"role": "user", "content": prompt}]},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Verdict dispatcher
# ---------------------------------------------------------------------------

def generate_verdict(ticker: str, data: dict) -> str:
    provider = active_llm_provider()
    if provider is None:
        return "N/A (no LLM API key set)"

    prompt = _build_prompt(ticker, data)
    print(f"Generating one-line verdict via {provider}...")

    try:
        if provider == "anthropic":
            return _verdict_anthropic(prompt)
        if provider == "groq":
            return _verdict_groq(prompt)
        if provider == "gemini":
            return _verdict_gemini(prompt)
        if provider == "openrouter":
            return _verdict_openrouter(prompt)
    except Exception as exc:
        print(f"Warning: {provider} API error — {exc}", file=sys.stderr)
        return f"N/A ({provider} API error)"

    return "N/A"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python brief.py <TICKER>", file=sys.stderr)
        print("Example: python brief.py MC.PA", file=sys.stderr)
        sys.exit(1)

    ticker = validate_ticker(sys.argv[1])
    validate_keys()

    print(f"Fetching data for {ticker}...")
    data = fetch_all(ticker)

    verdict = generate_verdict(ticker, data)

    print("Building markdown report...")
    markdown = build_markdown(data, verdict)

    output_file = f"{ticker}_brief.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"Report written to: {output_file}")


if __name__ == "__main__":
    main()
