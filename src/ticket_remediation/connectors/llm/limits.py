"""Shared bounds for LLM remediation providers' read_file tool loop.

Kept in one place so the Anthropic and Gemini providers (and any future ones)
can't drift apart on these values.
"""

MAX_FILE_READS = 15
MAX_FILE_BYTES = 20_000
