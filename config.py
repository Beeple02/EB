import os
import sys


EODHD_API_KEY = os.environ.get("EODHD_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

EODHD_BASE_URL = "https://eodhd.com/api"
CLAUDE_MODEL = "claude-sonnet-4-20250514"


def validate_keys():
    missing = []
    if not EODHD_API_KEY:
        missing.append("EODHD_API_KEY")
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if missing:
        print(
            f"Warning: missing environment variable(s): {', '.join(missing)}",
            file=sys.stderr,
        )
