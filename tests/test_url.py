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


def test_normalize_rejects_unsupported_schemes():
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        normalize_url("file:///etc/passwd")

    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        normalize_url("ftp://ftp.example.com/files")


def test_normalize_strips_control_characters():
    assert normalize_url("github.com\r\n") == "https://github.com"
    assert normalize_url("\x1b[31mexample.com\x1b[0m") == "https://example.com"


def test_get_display_name_redacts_credentials():
    assert get_display_name("http://admin:secretPass123@api.internal:8080/v1") == "api.internal:8080"
    assert get_display_name("https://token@github.com") == "github.com"

