"""Unit tests for atomic store persistence."""

import json
from pathlib import Path

from webstat.core.models import SiteStatus
from webstat.core.store import SiteStore


def test_store_add_and_load(tmp_path: Path):
    store_file = tmp_path / "sites.json"
    store = SiteStore(file_path=store_file)

    assert store.load_all() == []

    site = store.add("github.com", auto_open=True)
    assert site.url == "https://github.com"
    assert site.auto_open is True
    assert site.display_name == "github.com"

    # Reload from disk
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].id == site.id
    assert loaded[0].url == site.url
    assert loaded[0].auto_open is True


def test_store_update_and_remove(tmp_path: Path):
    store_file = tmp_path / "sites.json"
    store = SiteStore(file_path=store_file)

    site = store.add("example.com")
    site.status = SiteStatus.ONLINE
    site.status_code = 200
    site.latency_ms = 45.2
    store.update_site(site)

    # Check updated values
    refreshed = store.get_by_id_or_url("example.com")
    assert refreshed is not None
    assert refreshed.status == SiteStatus.ONLINE
    assert refreshed.status_code == 200
    assert refreshed.latency_ms == 45.2

    # Remove
    assert store.remove("example.com") is True
    assert store.load_all() == []
    assert store.remove("example.com") is False
