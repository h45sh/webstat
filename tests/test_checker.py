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
