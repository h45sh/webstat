"""Monitoring loop and scheduler for watching website status and triggering reminders."""

from __future__ import annotations

import asyncio
import time
from typing import Callable

from webstat.core.checker import HttpChecker
from webstat.core.models import CheckResult, MonitoredSite, SiteStatus
from webstat.core.notifier import NotificationDispatcher
from webstat.core.store import SiteStore


class WatchScheduler:
    """Orchestrates polling sites, detecting recovery, and dispatching notifications."""

    def __init__(
        self,
        store: SiteStore | None = None,
        dispatcher: NotificationDispatcher | None = None,
        checker: HttpChecker | None = None,
        poll_interval: float = 5.0,
        max_interval: float = 60.0,
        adaptive_backoff: bool = True,
        notification_cooldown: float = 60.0,
    ):
        self.store = store or SiteStore()
        self.dispatcher = dispatcher or NotificationDispatcher()
        self.checker = checker or HttpChecker()
        self.poll_interval = poll_interval
        self.max_interval = max_interval
        self.adaptive_backoff = adaptive_backoff
        self.notification_cooldown = notification_cooldown
        self._running = False

    def compute_delay(self, retries: int) -> float:
        """Compute poll delay with optional adaptive backoff."""
        if not self.adaptive_backoff:
            return self.poll_interval
        factor = min(retries // 3, 4)
        return min(self.poll_interval * (1.5**factor), self.max_interval)

    async def check_and_update(self, site: MonitoredSite) -> tuple[CheckResult, bool]:
        """Check a single site, update store, and dispatch notification if recovered.

        Returns (CheckResult, just_recovered: bool).
        """
        was_down = not site.is_up and site.status != SiteStatus.UNKNOWN
        result = await self.checker.check(site.url)

        site.status = result.status
        site.status_code = result.status_code
        site.latency_ms = result.latency_ms
        site.last_checked = result.timestamp
        site.last_error = result.error_message

        just_recovered = False
        now = time.time()
        if result.is_up:
            if was_down or site.retries > 0:
                # Enforce cooldown window to debounce flapping endpoints and prevent browser/notification floods
                if site.last_notified_at is None or (now - site.last_notified_at) >= self.notification_cooldown:
                    just_recovered = True
                    site.last_notified_at = now
                    self.dispatcher.dispatch_site_up(site, result)
            site.retries = 0
        else:
            site.retries += 1

        self.store.update_site(site)
        return result, just_recovered

    async def watch_sites(
        self,
        sites: list[MonitoredSite],
        on_tick: Callable[[MonitoredSite, CheckResult, bool], None] | None = None,
    ) -> None:
        """Watch a list of sites until all are online (unless keep_watching is True)."""
        self._running = True
        active_sites = list(sites)

        try:
            while self._running and active_sites:
                remaining: list[MonitoredSite] = []

                for site in active_sites:
                    result, just_recovered = await self.check_and_update(site)
                    if on_tick:
                        on_tick(site, result, just_recovered)

                    if result.is_up and not site.keep_watching:
                        # Site is up and completed reminder
                        continue
                    remaining.append(site)

                active_sites = remaining
                if not active_sites:
                    break

                # Determine sleep delay from min retry count
                min_retries = min(s.retries for s in active_sites)
                delay = self.compute_delay(min_retries)
                await asyncio.sleep(delay)

        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False
