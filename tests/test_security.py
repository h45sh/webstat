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

        # 4. Open site via --id (verifying open_in_browser is called)
        with patch("webstat.core.browser.open_in_browser") as mock_open:
            mock_open.return_value = True
            res_open = runner.invoke(app, ["open", "--id", site.id])
            assert res_open.exit_code == 0
            assert mock_open.called
            assert mock_open.call_args[0][0] == site.url


def test_browser_launcher_never_exposes_credentials_in_args(tmp_path):
    """Verify that BrowserLauncher and open_in_browser write a private 0600 trampoline
    HTML file and pass ONLY the file path to xdg-open/gio without leaking credentials
    or query tokens into process cmdline arguments.
    """
    from webstat.core.browser import open_in_browser
    from webstat.core.notifier import BrowserLauncher

    sensitive_url = "https://user:very_secret_pass@internal.portal:9000/auth?token=confidential_jwt_token"
    site = MonitoredSite(
        id="internal-portal-1234",
        url=sensitive_url,
        display_name="internal.portal:9000",
        raw_input=sensitive_url,
        auto_open=True,
    )
    result = CheckResult(
        url=sensitive_url,
        status=SiteStatus.ONLINE,
        status_code=200,
        latency_ms=25.0,
    )

    launcher = BrowserLauncher()

    with patch("shutil.which", return_value="/usr/bin/xdg-open"), \
         patch("subprocess.Popen") as mock_popen:

        success = launcher.notify_up(site, result)
        assert success is True
        assert mock_popen.called

        cmd_args = mock_popen.call_args[0][0]
        assert cmd_args[0] == "/usr/bin/xdg-open"
        assert len(cmd_args) == 2

        trampoline_path = cmd_args[1]

        # Verify no credentials or query tokens appear in process arguments
        for arg in cmd_args:
            assert "very_secret_pass" not in arg
            assert "confidential_jwt_token" not in arg
            assert "user:very_secret_pass" not in arg
            assert sensitive_url not in arg

        # Verify trampoline file exists with private permissions 0600
        import os
        import stat

        assert os.path.exists(trampoline_path)
        file_mode = os.stat(trampoline_path).st_mode & 0o777
        assert file_mode == 0o600

        # Verify trampoline contents contain safe client-side redirect
        with open(trampoline_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert sensitive_url in content
            assert '<meta http-equiv="refresh"' in content
            assert "window.location.replace" in content

        # Clean up test file
        try:
            os.unlink(trampoline_path)
        except OSError:
            pass
