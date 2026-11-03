"""Security-focused unit tests for webstat."""

import asyncio
from unittest.mock import patch, MagicMock
import httpx
import pytest

from webstat.core.checker import HttpChecker
from webstat.core.models import CheckResult, MonitoredSite, SiteStatus
from webstat.core.notifier import OmarchyNotifier, FreeDesktopNotifier
from webstat.core.store import SiteStore


@pytest.mark.anyio
async def test_redirect_oversized_body_not_buffered():
    """Verify that when a server rejects HEAD with 405 and returns a 302 redirect with an
    oversized body on GET, the body is never buffered and memory is preserved.
    """

    class StreamingMockTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.redirect_body_read = False

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if request.method == "HEAD" and request.url == "https://monitored.test/status":
                # Reject HEAD with 405 Method Not Allowed
                return httpx.Response(status_code=405, request=request)

            elif request.method == "GET" and request.url == "https://monitored.test/status":
                # Return 302 redirect to /final with an infinite/oversized stream
                async def infinite_stream():
                    try:
                        while True:
                            yield b"A" * 65536
                    except GeneratorExit:
                        pass

                return httpx.Response(
                    status_code=302,
                    headers={"Location": "https://monitored.test/final"},
                    content=infinite_stream(),
                    request=request,
                )

            elif request.url == "https://monitored.test/final":
                return httpx.Response(status_code=200, request=request)

            return httpx.Response(status_code=404, request=request)

    transport = StreamingMockTransport()
    checker = HttpChecker(timeout=5.0)

    # Patch httpx.AsyncClient to use our mock transport
    original_client_init = httpx.AsyncClient.__init__

    def mock_client_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        original_client_init(self, *args, **kwargs)

    with patch.object(httpx.AsyncClient, "__init__", mock_client_init):
        result = await checker.check("https://monitored.test/status")

    assert result.status == SiteStatus.ONLINE
    assert result.status_code == 200
    assert len(result.redirect_chain) == 1
    assert "302 -> https://monitored.test/final" in result.redirect_chain[0]


def test_notifier_arguments_do_not_disclose_credentials():
    """Verify that sensitive credentials and query tokens in site URLs are never passed
    in command-line arguments to omarchy-notification-send or notify-send.
    """
    sensitive_url = "https://admin:super_secret_password@internal.corp:8443/api?token=super_secret_token"
    site = MonitoredSite(
        id="internal-corp-8443-abcd1234ef",
        url=sensitive_url,
        display_name="internal.corp:8443",
        raw_input=sensitive_url,
        notify_on_up=True,
    )
    result = CheckResult(
        url=sensitive_url,
        status=SiteStatus.ONLINE,
        status_code=200,
        latency_ms=12.5,
    )

    # 1. OmarchyNotifier
    omarchy_notifier = OmarchyNotifier()
    with patch.object(omarchy_notifier, "is_available", return_value=True), \
         patch("subprocess.run") as mock_run:
        omarchy_notifier.notify_up(site, result)

        assert mock_run.called
        cmd_args = mock_run.call_args[0][0]

        # Verify neither password nor token appears anywhere in argv
        for arg in cmd_args:
            assert "super_secret_password" not in arg
            assert "super_secret_token" not in arg
            assert "admin:super_secret_password" not in arg

        # Verify that display_name is used in description
        assert any("internal.corp:8443" in arg for arg in cmd_args)
        # Verify that --exec invokes webstat open --id <site.id>
        exec_idx = cmd_args.index("--exec")
        assert cmd_args[exec_idx + 1 :] == ["webstat", "open", "--id", site.id]

    # 2. FreeDesktopNotifier
    freedesktop_notifier = FreeDesktopNotifier()
    with patch.object(freedesktop_notifier, "is_available", return_value=True), \
         patch("subprocess.run") as mock_run:
        freedesktop_notifier.notify_up(site, result)

        assert mock_run.called
        cmd_args = mock_run.call_args[0][0]

        for arg in cmd_args:
            assert "super_secret_password" not in arg
            assert "super_secret_token" not in arg
            assert "admin:super_secret_password" not in arg

        assert any("internal.corp:8443" in arg for arg in cmd_args)


def test_cli_stdin_and_id_options(tmp_path):
    """Verify webstat check and add commands with --stdin and --id."""
    from typer.testing import CliRunner
    from webstat.cli import app

    runner = CliRunner()
    store_file = tmp_path / "sites.json"

    with patch("webstat.cli.SiteStore", return_value=SiteStore(file_path=store_file)):
        # 1. Add site via stdin
        secret_url = "https://user:pass@test-site.org/health?token=abc"
        res_add = runner.invoke(app, ["add", "--stdin"], input=f"{secret_url}\n")
        assert res_add.exit_code == 0
        assert "Added:" in res_add.output
        assert "test-site.org" in res_add.output

        # Verify site is in store
        store = SiteStore(file_path=store_file)
        sites = store.load_all()
        assert len(sites) == 1
        site = sites[0]

        # 2. Check site via --id
        async def fake_check_id(url):
            return CheckResult(url=site.url, status=SiteStatus.ONLINE, status_code=200, latency_ms=15.0)

        with patch.object(HttpChecker, "check", side_effect=fake_check_id):
            res_check_id = runner.invoke(app, ["check", "--id", site.id, "--json"])
            assert res_check_id.exit_code == 0
            assert '"status": "ONLINE"' in res_check_id.output

        # 3. Check site via --stdin
        async def fake_check_stdin(url):
            return CheckResult(url="https://example.com", status=SiteStatus.ONLINE, status_code=200, latency_ms=10.0)

        with patch.object(HttpChecker, "check", side_effect=fake_check_stdin):
            res_check_stdin = runner.invoke(app, ["check", "--stdin", "--json"], input="https://example.com\n")
            assert res_check_stdin.exit_code == 0
            assert '"status": "ONLINE"' in res_check_stdin.output

        # 4. Open site via --id
        with patch("webbrowser.open") as mock_browser_open:
            res_open = runner.invoke(app, ["open", "--id", site.id])
            assert res_open.exit_code == 0
            assert mock_browser_open.called
            assert mock_browser_open.call_args[0][0] == site.url
