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


def test_store_file_permissions(tmp_path: Path):
    store_file = tmp_path / "webstat" / "sites.json"
    store = SiteStore(file_path=store_file)

    store.add("example.org")
    assert store_file.exists()

    # File permissions must be 0600 (owner read/write only)
    mode = store_file.stat().st_mode & 0o777
    assert mode == 0o600

    # Directory permissions must be 0700 (owner rwx only)
    dir_mode = store_file.parent.stat().st_mode & 0o777
    assert dir_mode == 0o700


def test_store_reentrant_lock(tmp_path: Path):
    store_file = tmp_path / "sites.json"
    store = SiteStore(file_path=store_file)

    # Should be able to acquire lock reentrantly without deadlock
    with store._file_lock(shared=False):
        site = store.add("test-lock.org")
        with store._file_lock(shared=True):
            sites = store.load_all()
            assert len(sites) == 1
            assert sites[0].id == site.id

