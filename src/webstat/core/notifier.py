"""Notification dispatcher for Omarchy and standard desktop environments."""

from __future__ import annotations

import abc
import re
import shutil
import subprocess
import sys
from typing import Any

from webstat.core.models import CheckResult, MonitoredSite


def _clean_notification_text(text: str) -> str:
    """Sanitize notification text by stripping control characters and carriage returns/newlines."""
    cleaned = text.replace("\r", " ").replace("\n", " ")
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", "", cleaned).strip()


class BaseNotifier(abc.ABC):
    """Abstract base class for notification providers."""

    @abc.abstractmethod
    def notify_up(self, site: MonitoredSite, result: CheckResult) -> bool:
        """Trigger notification that a site is back up."""
        pass


class OmarchyNotifier(BaseNotifier):
    """Native Omarchy desktop notification using `omarchy notification send`."""

    def __init__(self):
        self.omarchy_bin = shutil.which("omarchy")

    def is_available(self) -> bool:
        return self.omarchy_bin is not None

    def notify_up(self, site: MonitoredSite, result: CheckResult) -> bool:
        if not self.is_available():
            return False

        headline = _clean_notification_text(f"Site is UP: {site.display_name}")
        latency_str = f" in {result.latency_ms}ms" if result.latency_ms else ""
        code_str = f"{result.status_code} " if result.status_code else ""
        desc = _clean_notification_text(f"{site.display_name} is back online ({code_str}OK{latency_str}). Click to open.")

        cmd = [
            self.omarchy_bin,
            "notification",
            "send",
            "--app-name",
            "webstat",
            "-g",
            "globe",
            "-u",
            "normal",
            headline,
            desc,
            "--exec",
            "webstat",
            "open",
            "--id",
            site.id,
        ]

        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False


class FreeDesktopNotifier(BaseNotifier):
    """Standard Linux desktop notification via `notify-send`."""

    def __init__(self):
        self.notify_bin = shutil.which("notify-send")

    def is_available(self) -> bool:
        return self.notify_bin is not None

    def notify_up(self, site: MonitoredSite, result: CheckResult) -> bool:
        if not self.is_available():
            return False

        headline = _clean_notification_text(f"Site is UP: {site.display_name}")
        desc = _clean_notification_text(f"{site.display_name} is back online!")
        cmd = [self.notify_bin, "-a", "webstat", "-i", "network-idle", headline, desc]

        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False


class BrowserLauncher(BaseNotifier):
    """Directly opens the default browser using xdg-open."""

    def notify_up(self, site: MonitoredSite, result: CheckResult) -> bool:
        if not site.auto_open:
            return False
        xdg_bin = shutil.which("xdg-open")
        if not xdg_bin:
            return False
        try:
            subprocess.Popen(
                [xdg_bin, site.url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except Exception:
            return False


class TerminalBellNotifier(BaseNotifier):
    """Audible terminal bell trigger."""

    def notify_up(self, site: MonitoredSite, result: CheckResult) -> bool:
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
            return True
        except Exception:
            return False


class NotificationDispatcher:
    """Dispatches notifications across all applicable channels."""

    def __init__(self, with_bell: bool = True):
        self.omarchy = OmarchyNotifier()
        self.freedesktop = FreeDesktopNotifier()
        self.browser = BrowserLauncher()
        self.bell = TerminalBellNotifier()
        self.with_bell = with_bell

    def dispatch_site_up(self, site: MonitoredSite, result: CheckResult) -> dict[str, bool]:
        results: dict[str, bool] = {}

        # 1. Desktop Notification (Omarchy first, fallback to notify-send)
        if site.notify_on_up:
            if self.omarchy.is_available():
                results["omarchy"] = self.omarchy.notify_up(site, result)
            elif self.freedesktop.is_available():
                results["desktop"] = self.freedesktop.notify_up(site, result)

        # 2. Browser Auto-Open
        if site.auto_open:
            results["browser_open"] = self.browser.notify_up(site, result)

        # 3. Terminal Bell
        if self.with_bell:
            results["bell"] = self.bell.notify_up(site, result)

        return results
