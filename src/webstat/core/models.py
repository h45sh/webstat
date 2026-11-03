"""Data models and enums for webstat."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class SiteStatus(str, Enum):
    ONLINE = "ONLINE"
    REDIRECT = "REDIRECT"
    CLIENT_ERROR = "CLIENT_ERROR"
    SERVER_ERROR = "SERVER_ERROR"
    UNREACHABLE = "UNREACHABLE"
    UNKNOWN = "UNKNOWN"

    @property
    def is_positive(self) -> bool:
        """True if the site responded positively and can be browsed."""
        return self in (SiteStatus.ONLINE, SiteStatus.REDIRECT)


@dataclass
class CheckResult:
    url: str
    status: SiteStatus
    status_code: int | None = None
    latency_ms: float | None = None
    redirect_chain: list[str] = field(default_factory=list)
    error_message: str | None = None
    ssl_expires_days: int | None = None
    timestamp: float = field(default_factory=time.time)

    @property
    def is_up(self) -> bool:
        return self.status.is_positive

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["is_up"] = self.is_up
        return data


@dataclass
class MonitoredSite:
    id: str
    url: str
    display_name: str
    raw_input: str
    auto_open: bool = False
    notify_on_up: bool = True
    keep_watching: bool = False
    status: SiteStatus = SiteStatus.UNKNOWN
    status_code: int | None = None
    latency_ms: float | None = None
    last_checked: float | None = None
    retries: int = 0
    last_error: str | None = None
    created_at: float = field(default_factory=time.time)
    last_notified_at: float | None = None

    @property
    def is_up(self) -> bool:
        return self.status.is_positive

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "display_name": self.display_name,
            "raw_input": self.raw_input,
            "auto_open": self.auto_open,
            "notify_on_up": self.notify_on_up,
            "keep_watching": self.keep_watching,
            "status": self.status.value,
            "status_code": self.status_code,
            "latency_ms": self.latency_ms,
            "last_checked": self.last_checked,
            "retries": self.retries,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "last_notified_at": self.last_notified_at,
            "is_up": self.is_up,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MonitoredSite:
        status_val = data.get("status", SiteStatus.UNKNOWN.value)
        try:
            status = SiteStatus(status_val)
        except ValueError:
            status = SiteStatus.UNKNOWN

        return cls(
            id=data["id"],
            url=data["url"],
            display_name=data.get("display_name", data["url"]),
            raw_input=data.get("raw_input", data["url"]),
            auto_open=data.get("auto_open", False),
            notify_on_up=data.get("notify_on_up", True),
            keep_watching=data.get("keep_watching", False),
            status=status,
            status_code=data.get("status_code"),
            latency_ms=data.get("latency_ms"),
            last_checked=data.get("last_checked"),
            retries=data.get("retries", 0),
            last_error=data.get("last_error"),
            created_at=data.get("created_at", time.time()),
            last_notified_at=data.get("last_notified_at"),
        )
