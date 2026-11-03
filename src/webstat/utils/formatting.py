"""Formatting helpers for rich terminal output."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from webstat.core.models import CheckResult, MonitoredSite, SiteStatus


def get_status_badge(status: SiteStatus, status_code: int | None = None) -> Text:
    """Generate a stylized text badge for a site status."""
    code_text = f" {status_code}" if status_code else ""

    if status == SiteStatus.ONLINE:
        return Text(f"● ONLINE{code_text}", style="bold green")
    elif status == SiteStatus.REDIRECT:
        return Text(f"↗ REDIRECT{code_text}", style="bold cyan")
    elif status == SiteStatus.CLIENT_ERROR:
        return Text(f"▲ CLIENT ERROR{code_text}", style="bold yellow")
    elif status == SiteStatus.SERVER_ERROR:
        return Text(f"✖ SERVER ERROR{code_text}", style="bold red")
    elif status == SiteStatus.UNREACHABLE:
        return Text("✖ UNREACHABLE", style="bold red on default")
    else:
        return Text("? UNKNOWN", style="dim")


def get_latency_text(latency_ms: float | None) -> Text:
    """Format latency with appropriate color coding."""
    if latency_ms is None:
        return Text("—", style="dim")
    if latency_ms < 200:
        return Text(f"{latency_ms} ms", style="green")
    elif latency_ms < 800:
        return Text(f"{latency_ms} ms", style="yellow")
    else:
        return Text(f"{latency_ms} ms", style="magenta")


def build_sites_table(sites: list[MonitoredSite]) -> Table:
    """Construct a clean Rich table of all monitored sites."""
    table = Table(
        title="Webstat Monitored Sites",
        title_style="bold cyan",
        header_style="bold",
        border_style="dim",
        expand=True,
    )

    table.add_column("Site", style="bold white", no_wrap=True)
    table.add_column("Status", justify="left")
    table.add_column("Latency", justify="right")
    table.add_column("Retries", justify="right")
    table.add_column("Auto Open", justify="center")
    table.add_column("Last Error / Details", style="dim")

    for site in sites:
        badge = get_status_badge(site.status, site.status_code)
        latency = get_latency_text(site.latency_ms)
        retries = str(site.retries) if site.retries > 0 else "—"
        auto_open = "✓ Yes" if site.auto_open else "No"
        details = site.last_error or "—"

        table.add_row(
            site.display_name,
            badge,
            latency,
            retries,
            auto_open,
            details,
        )

    return table
