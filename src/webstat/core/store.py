"""Atomic XDG state storage for webstat monitored sites."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from webstat.core.models import MonitoredSite
from webstat.utils.url import get_display_name, normalize_url


def get_default_state_path() -> Path:
    """Return the state file path respecting XDG_STATE_HOME."""
    state_dir = os.environ.get("XDG_STATE_HOME")
    if state_dir:
        base = Path(state_dir)
    else:
        base = Path.home() / ".local" / "state"
    target_dir = base / "webstat"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / "sites.json"


def generate_site_id(url: str) -> str:
    """Generate a stable, clean identifier for a URL."""
    normalized = normalize_url(url)
    h = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
    host = get_display_name(normalized).replace(".", "-").replace(":", "-")
    return f"{host}-{h}"


class SiteStore:
    """Thread-safe and process-safe state store using atomic JSON file replacement."""

    def __init__(self, file_path: Path | None = None):
        self.file_path = file_path or get_default_state_path()

    def load_all(self) -> list[MonitoredSite]:
        if not self.file_path.exists():
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data: list[dict[str, Any]] = json.load(f)
                return [MonitoredSite.from_dict(item) for item in data]
        except Exception:
            return []

    def save_all(self, sites: list[MonitoredSite]) -> None:
        raw_data = [s.to_dict() for s in sites]
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = self.file_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        # Atomic replacement on POSIX
        temp_path.replace(self.file_path)

    def get_by_id_or_url(self, id_or_url: str) -> MonitoredSite | None:
        sites = self.load_all()
        clean = id_or_url.strip()
        for s in sites:
            if s.id == clean or s.url == clean or s.display_name == clean or s.raw_input == clean:
                return s
        try:
            normalized = normalize_url(clean)
            for s in sites:
                if s.url == normalized:
                    return s
        except Exception:
            pass
        return None

    def add(
        self,
        raw_url: str,
        auto_open: bool = False,
        notify_on_up: bool = True,
        keep_watching: bool = False,
    ) -> MonitoredSite:
        normalized = normalize_url(raw_url)
        site_id = generate_site_id(normalized)
        sites = self.load_all()

        existing = next((s for s in sites if s.id == site_id), None)
        if existing:
            existing.auto_open = auto_open or existing.auto_open
            existing.notify_on_up = notify_on_up
            existing.keep_watching = keep_watching
            self.save_all(sites)
            return existing

        site = MonitoredSite(
            id=site_id,
            url=normalized,
            display_name=get_display_name(normalized),
            raw_input=raw_url,
            auto_open=auto_open,
            notify_on_up=notify_on_up,
            keep_watching=keep_watching,
        )
        sites.append(site)
        self.save_all(sites)
        return site

    def update_site(self, site: MonitoredSite) -> None:
        sites = self.load_all()
        for idx, s in enumerate(sites):
            if s.id == site.id:
                sites[idx] = site
                break
        else:
            sites.append(site)
        self.save_all(sites)

    def remove(self, id_or_url: str) -> bool:
        site = self.get_by_id_or_url(id_or_url)
        if not site:
            return False
        sites = self.load_all()
        sites = [s for s in sites if s.id != site.id]
        self.save_all(sites)
        return True

    def clear(self) -> None:
        self.save_all([])
