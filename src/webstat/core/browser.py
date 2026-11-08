"""Secure browser launcher utilities preventing command-line argument leakage."""

import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Optional


def _cleanup_old_launchers(launcher_dir: str, max_age_seconds: float = 60.0) -> None:
    """Remove any stale trampoline HTML files older than max_age_seconds owned by current user."""
    try:
        now = time.time()
        current_uid = os.getuid() if hasattr(os, "getuid") else None
        for fname in os.listdir(launcher_dir):
            if fname.startswith("open_") and fname.endswith(".html"):
                fpath = os.path.join(launcher_dir, fname)
                try:
                    st = os.stat(fpath)
                    if current_uid is not None and st.st_uid != current_uid:
                        continue
                    if now - st.st_mtime > max_age_seconds:
                        os.unlink(fpath)
                except OSError:
                    pass
    except OSError:
        pass


def _schedule_file_cleanup(fpath: str, delay_seconds: float = 30.0) -> None:
    """Schedule detached asynchronous deletion of the temporary trampoline file."""
    try:
        code = (
            "import time, os, sys\n"
            "time.sleep(float(sys.argv[1]))\n"
            "try:\n"
            "    os.unlink(sys.argv[2])\n"
            "except OSError:\n"
            "    pass\n"
        )
        subprocess.Popen(
            [sys.executable, "-c", code, str(delay_seconds), fpath],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        def _remover():
            time.sleep(delay_seconds)
            try:
                if os.path.exists(fpath):
                    os.unlink(fpath)
            except OSError:
                pass

        t = threading.Thread(target=_remover, daemon=True)
        t.start()


def open_in_browser(url: str, display_name: Optional[str] = None) -> bool:
    """Open a URL in the user's default browser without exposing sensitive URL

    parameters (such as embedded credentials or query tokens) in child-process
    command line arguments (/proc/<pid>/cmdline).

    Creates a private, user-only temporary HTML trampoline file (0600 permissions
    in a 0700 directory) that immediately performs client-side redirect. Only
    the path to the private trampoline file is passed to xdg-open/gio.
    """
    if not url:
        return False

    launcher_bin = shutil.which("xdg-open") or shutil.which("gio")
    if not launcher_bin:
        return False

    from webstat.utils.url import get_display_name

    label = display_name or get_display_name(url)
    launcher_dir = os.path.expanduser("~/.local/state/webstat/open")
    try:
        os.makedirs(launcher_dir, mode=0o700, exist_ok=True)
        os.chmod(launcher_dir, 0o700)
    except OSError:
        uid_tag = str(os.getuid()) if hasattr(os, "getuid") else "user"
        launcher_dir = os.path.join(tempfile.gettempdir(), f"webstat-{uid_tag}-open")
        try:
            os.makedirs(launcher_dir, mode=0o700, exist_ok=True)
            os.chmod(launcher_dir, 0o700)
        except OSError:
            launcher_dir = tempfile.gettempdir()

    _cleanup_old_launchers(launcher_dir)

    escaped_url = html.escape(url, quote=True)
    escaped_label = html.escape(label)
    json_url = json.dumps(url).replace("<", "\\u003c").replace(">", "\\u003e")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url={escaped_url}">
  <title>Opening {escaped_label}</title>
  <script>
    window.location.replace({json_url});
  </script>
</head>
<body style="font-family: sans-serif; padding: 2rem; background: #121212; color: #fff;">
  <p>Opening <strong>{escaped_label}</strong>...</p>
  <p><a id="redir" href="{escaped_url}" style="color: #38bdf8;">Click here if your browser does not redirect automatically</a></p>
</body>
</html>"""

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=launcher_dir,
            prefix="open_",
            suffix=".html",
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as f:
            f.write(html_content)
            tmp_path = f.name

        os.chmod(tmp_path, 0o600)

        cmd = [launcher_bin, tmp_path] if "xdg-open" in launcher_bin else [launcher_bin, "open", tmp_path]

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        _schedule_file_cleanup(tmp_path, delay_seconds=30.0)
        return True
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False
