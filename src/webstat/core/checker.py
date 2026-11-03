"""Health check probe implementations for webstat."""

from __future__ import annotations

import abc
import socket
import ssl
import time
from urllib.parse import urlparse

import httpx

from webstat.core.models import CheckResult, SiteStatus
from webstat.utils.url import normalize_url


class BaseChecker(abc.ABC):
    """Abstract base class for all health checkers/probes."""

    @abc.abstractmethod
    async def check(self, url: str) -> CheckResult:
        """Execute the probe and return a CheckResult."""
        pass


class HttpChecker(BaseChecker):
    """Standard HTTP/HTTPS checker with latency measurement and error categorization."""

    def __init__(self, timeout: float = 8.0, user_agent: str = "webstat/0.1.0"):
        self.timeout = timeout
        self.user_agent = user_agent

    async def check(self, url: str) -> CheckResult:
        normalized = normalize_url(url)
        redirect_chain: list[str] = []
        start_time = time.perf_counter()

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "*/*",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers=headers,
                verify=True,
            ) as client:
                response = await client.get(normalized)
                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)

                if response.history:
                    for resp in response.history:
                        redirect_chain.append(f"{resp.status_code} -> {resp.url}")

                status_code = response.status_code

                if 200 <= status_code < 300:
                    status = SiteStatus.ONLINE
                elif 300 <= status_code < 400:
                    status = SiteStatus.REDIRECT
                elif 400 <= status_code < 500:
                    status = SiteStatus.CLIENT_ERROR
                else:
                    status = SiteStatus.SERVER_ERROR

                ssl_days = self._check_ssl_expiry(normalized) if normalized.startswith("https://") else None

                return CheckResult(
                    url=normalized,
                    status=status,
                    status_code=status_code,
                    latency_ms=elapsed_ms,
                    redirect_chain=redirect_chain,
                    ssl_expires_days=ssl_days,
                )

        except httpx.ConnectTimeout:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
            return CheckResult(
                url=normalized,
                status=SiteStatus.UNREACHABLE,
                latency_ms=elapsed_ms,
                error_message="Connection timed out",
            )
        except httpx.ReadTimeout:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
            return CheckResult(
                url=normalized,
                status=SiteStatus.UNREACHABLE,
                latency_ms=elapsed_ms,
                error_message="Response read timed out",
            )
        except httpx.ConnectError as e:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
            err_str = str(e)
            if "Name or service not known" in err_str or "getaddrinfo failed" in err_str:
                msg = "DNS lookup failed (host not found)"
            elif "Connection refused" in err_str:
                msg = "Connection refused (port closed or server down)"
            else:
                msg = f"Connection error: {err_str}"
            return CheckResult(
                url=normalized,
                status=SiteStatus.UNREACHABLE,
                latency_ms=elapsed_ms,
                error_message=msg,
            )
        except httpx.HTTPError as e:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
            return CheckResult(
                url=normalized,
                status=SiteStatus.UNREACHABLE,
                latency_ms=elapsed_ms,
                error_message=f"HTTP protocol error: {e}",
            )
        except Exception as e:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
            return CheckResult(
                url=normalized,
                status=SiteStatus.UNREACHABLE,
                latency_ms=elapsed_ms,
                error_message=str(e),
            )

    def _check_ssl_expiry(self, url: str) -> int | None:
        """Quick check for TLS certificate expiration days remaining."""
        try:
            parsed = urlparse(url)
            host = parsed.hostname
            port = parsed.port or 443
            if not host:
                return None

            ctx = ssl.create_default_context()
            with socket.create_connection((host, port), timeout=3.0) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()
                    if not cert or "notAfter" not in cert:
                        return None
                    # notAfter example: 'May 15 12:00:00 2026 GMT'
                    expiry_time = ssl.cert_time_to_seconds(cert["notAfter"])
                    remaining_seconds = expiry_time - time.time()
                    return max(0, int(remaining_seconds // 86400))
        except Exception:
            return None


async def check_url(url: str, timeout: float = 8.0) -> CheckResult:
    """Convenience helper to check a single URL asynchronously."""
    checker = HttpChecker(timeout=timeout)
    return await checker.check(url)
