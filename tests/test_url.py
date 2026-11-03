"""Unit tests for URL normalization."""

import pytest
from webstat.utils.url import get_display_name, normalize_url


def test_normalize_plain_domain():
    assert normalize_url("github.com") == "https://github.com"
    assert normalize_url("google.com/search?q=test") == "https://google.com/search?q=test"


def test_normalize_with_scheme():
    assert normalize_url("http://example.com") == "http://example.com"
    assert normalize_url("https://mysite.org:8443/api") == "https://mysite.org:8443/api"


def test_normalize_localhost_and_ips():
    assert normalize_url("localhost:3000") == "http://localhost:3000"
    assert normalize_url("127.0.0.1:8080") == "http://127.0.0.1:8080"


def test_normalize_empty_fails():
    with pytest.raises(ValueError):
        normalize_url("   ")


def test_get_display_name():
    assert get_display_name("https://github.com/torvalds/linux") == "github.com"
    assert get_display_name("http://localhost:8000/dashboard") == "localhost:8000"
