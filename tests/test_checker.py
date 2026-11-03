"""Unit tests for HttpChecker and scheduler."""

import pytest
from webstat.core.checker import HttpChecker
from webstat.core.models import CheckResult, MonitoredSite, SiteStatus
from webstat.core.scheduler import WatchScheduler


import asyncio


def test_check_unreachable():
    checker = HttpChecker(timeout=1.0)
    # Using an invalid domain or closed port
    result = asyncio.run(checker.check("http://127.0.0.1:59999"))
    assert result.status == SiteStatus.UNREACHABLE
    assert result.is_up is False
    assert result.error_message is not None


def test_scheduler_backoff():
    scheduler = WatchScheduler(poll_interval=5.0, max_interval=60.0, adaptive_backoff=True)
    assert scheduler.compute_delay(0) == 5.0
    assert scheduler.compute_delay(2) == 5.0
    # factor = min(3 // 3, 4) = 1 -> 5.0 * 1.5 = 7.5
    assert scheduler.compute_delay(3) == 7.5
    # factor = min(6 // 3, 4) = 2 -> 5.0 * 2.25 = 11.25
    assert scheduler.compute_delay(6) == 11.25


class DummyOnlineChecker:
    async def check(self, url: str) -> CheckResult:
        return CheckResult(url=url, status=SiteStatus.ONLINE, status_code=200, latency_ms=10.0)


class DummyDispatcher:
    def __init__(self):
        self.dispatched = []

    def dispatch_site_up(self, site, result):
        self.dispatched.append(site.id)


def test_scheduler_flapping_cooldown(tmp_path):
    store_file = tmp_path / "sites.json"
    from webstat.core.store import SiteStore
    import time

    store = SiteStore(file_path=store_file)
    site = store.add("https://flapping-test.com")
    site.status = SiteStatus.UNREACHABLE
    site.retries = 2
    store.update_site(site)

    dispatcher = DummyDispatcher()
    scheduler = WatchScheduler(
        store=store,
        dispatcher=dispatcher,
        checker=DummyOnlineChecker(),
        notification_cooldown=30.0,
    )

    # First recovery -> should trigger notification
    result, just_recovered = asyncio.run(scheduler.check_and_update(site))
    assert just_recovered is True
    assert len(dispatcher.dispatched) == 1
    assert site.last_notified_at is not None

    # Immediate second flapping cycle -> should be throttled by cooldown
    site.status = SiteStatus.UNREACHABLE
    site.retries = 1
    store.update_site(site)

    result2, just_recovered2 = asyncio.run(scheduler.check_and_update(site))
    assert just_recovered2 is False
    assert len(dispatcher.dispatched) == 1  # No additional dispatch

    # Advance beyond cooldown -> should notify again
    site.last_notified_at = time.time() - 35.0
    site.status = SiteStatus.UNREACHABLE
    site.retries = 1
    store.update_site(site)

    result3, just_recovered3 = asyncio.run(scheduler.check_and_update(site))
    assert just_recovered3 is True
    assert len(dispatcher.dispatched) == 2

