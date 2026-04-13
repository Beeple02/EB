import os
import sys


EODHD_API_KEY = os.environ.get("EODHD_API_KEY", "")
EODHD_BASE_URL = "https://eodhd.com/api"

# LLM provider — set one of these env vars; first found wins
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Model names per provider
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-1.5-flash"
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"


def active_llm_provider():
    """Return the name of the first configured LLM provider, or None."""
    if ANTHROPIC_API_KEY:
        return "anthropic"
    if GROQ_API_KEY:
        return "groq"
    if GEMINI_API_KEY:
        return "gemini"
    if OPENROUTER_API_KEY:
        return "openrouter"
    return None


def validate_keys():
    if not EODHD_API_KEY:
        print("Warning: EODHD_API_KEY not set — will fall back to yfinance.", file=sys.stderr)
    if active_llm_provider() is None:
        print(
            "Warning: no LLM API key found. Set one of: "
            "ANTHROPIC_API_KEY, GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY.",
            file=sys.stderr,
        )
