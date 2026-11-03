"""URL utilities for webstat."""

import re
from urllib.parse import urlparse


def normalize_url(raw_url: str) -> str:
    """Normalize a user-provided URL or hostname.

    Examples:
        - "github.com" -> "https://github.com"
        - "localhost:3000" -> "http://localhost:3000"
        - "127.0.0.1:8000" -> "http://127.0.0.1:8000"
        - "http://example.com" -> "http://example.com"
        - "https://mysite.org/health" -> "https://mysite.org/health"
    """
    url = raw_url.strip()
    if not url:
        raise ValueError("URL cannot be empty")

    # If scheme is already present, validate
    if re.match(r"^https?://", url, re.IGNORECASE):
        parsed = urlparse(url)
        if not parsed.netloc:
            raise ValueError(f"Invalid URL: {raw_url}")
        return url

    # Default to http:// for localhost or IP with port, https:// otherwise
    if url.startswith("localhost") or url.startswith("127.0.0.1") or url.startswith("0.0.0.0"):
        url = f"http://{url}"
    else:
        url = f"https://{url}"

    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError(f"Invalid URL or hostname: {raw_url}")

    return url


def get_display_name(url: str) -> str:
    """Extract a friendly clean name for display and notifications."""
    try:
        parsed = urlparse(url)
        host = parsed.netloc or parsed.path
        # Strip port if standard or keep if non-standard
        return host
    except Exception:
        return url
