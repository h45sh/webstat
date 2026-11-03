"""URL utilities for webstat."""

import re
from urllib.parse import urlparse


def _strip_ansi_and_control(text: str) -> str:
    """Remove ANSI escape sequences and non-printable control characters."""
    # First strip ANSI escape sequences (e.g. \x1b[31m)
    no_ansi = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    # Then strip ASCII/Latin-1 C0 and C1 control characters
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", "", no_ansi).strip()


def normalize_url(raw_url: str) -> str:
    """Normalize a user-provided URL or hostname.

    Examples:
        - "github.com" -> "https://github.com"
        - "localhost:3000" -> "http://localhost:3000"
        - "127.0.0.1:8000" -> "http://127.0.0.1:8000"
        - "http://example.com" -> "http://example.com"
        - "https://mysite.org/health" -> "https://mysite.org/health"
    """
    url = _strip_ansi_and_control(raw_url)
    if not url:
        raise ValueError("URL cannot be empty")

    # If scheme is already present, validate that it is HTTP or HTTPS
    if "://" in url:
        if not re.match(r"^https?://", url, re.IGNORECASE):
            raise ValueError(f"Unsupported URL scheme. Only http:// and https:// are supported: {raw_url}")
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
    """Extract a friendly clean name for display and notifications, omitting embedded credentials."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or parsed.path
        if parsed.port and parsed.port not in (80, 443):
            host = f"{host}:{parsed.port}"
        # Strip any ANSI escape sequences or control characters
        host = _strip_ansi_and_control(host)
        return host or _strip_ansi_and_control(url)
    except Exception:
        return _strip_ansi_and_control(url)
