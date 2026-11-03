"""Health check probe implementations for webstat."""

from __future__ import annotations

import abc
import datetime
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

    def __init__(self, timeout: float = 5.0, user_agent: str = "webstat/0.1.0", check_ssl: bool = False):
        self.timeout = timeout
        self.user_agent = user_agent
        self.check_ssl = check_ssl

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
                follow_redirects=False,
                headers=headers,
                verify=True,
            ) as client:
                current_url = normalized
                max_redirects = 10
                redirect_count = 0
                status_code: int = 0

                while True:
                    response: httpx.Response | None = None
                    try:
                        # Try fast HEAD probe first to avoid downloading large bodies
                        head_req = client.build_request("HEAD", current_url)
                        try:
                            head_resp = await client.send(head_req, stream=True)
                            if head_resp.status_code in (405, 501):
                                await head_resp.aclose()
                                get_req = client.build_request("GET", current_url)
                                response = await client.send(get_req, stream=True)
                            else:
                                response = head_resp
                        except (httpx.RequestError, httpx.HTTPStatusError):
                            # Server failed or rejected HEAD probe; fallback to streaming GET
                            get_req = client.build_request("GET", current_url)
                            response = await client.send(get_req, stream=True)

                        status_code = response.status_code

                        # Check if response is a redirect (3xx with Location header)
                        if response.is_redirect and "location" in response.headers:
                            if redirect_count >= max_redirects:
                                await response.aclose()
                                raise httpx.TooManyRedirects(
                                    f"Exceeded maximum allowed redirects ({max_redirects})"
                                )

                            location = response.headers["location"]
                            next_url = str(response.url.join(location))

                            parsed_next = urlparse(next_url)
                            if parsed_next.scheme not in ("http", "https"):
                                await response.aclose()
                                raise httpx.RequestError(
                                    f"Unsupported redirect scheme: {parsed_next.scheme}"
                                )

                            redirect_chain.append(f"{response.status_code} -> {next_url}")
                            # Immediately close the redirect response WITHOUT reading or buffering body into RAM
                            await response.aclose()

                            redirect_count += 1
                            current_url = next_url
                            continue
                        else:
                            # Final response reached: immediately close without consuming body
                            await response.aclose()
                            break
                    except Exception:
                        if response is not None and not response.is_closed:
                            await response.aclose()
                        raise

                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)

                if 200 <= status_code < 300:
                    status = SiteStatus.ONLINE
                elif 300 <= status_code < 400:
                    status = SiteStatus.REDIRECT
                elif 400 <= status_code < 500:
                    status = SiteStatus.CLIENT_ERROR
                else:
                    status = SiteStatus.SERVER_ERROR

                ssl_days = None
                if self.check_ssl and normalized.startswith("https://"):
                    ssl_days = self._check_ssl_expiry(normalized)

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
        except httpx.TooManyRedirects as e:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)
            return CheckResult(
                url=normalized,
                status=SiteStatus.UNREACHABLE,
                latency_ms=elapsed_ms,
                redirect_chain=redirect_chain,
                error_message=f"Too many redirects: {e}",
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
                    expiry_dt = datetime.datetime.strptime(
                        cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
                    ).replace(tzinfo=datetime.timezone.utc)
                    now_dt = datetime.datetime.now(datetime.timezone.utc)
                    remaining_seconds = (expiry_dt - now_dt).total_seconds()
                    return max(0, int(remaining_seconds // 86400))
        except Exception:
            return None


async def check_url(url: str, timeout: float = 8.0) -> CheckResult:
    """Convenience helper to check a single URL asynchronously."""
    checker = HttpChecker(timeout=timeout)
    return await checker.check(url)
