"""Command line interface for webstat."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import List, Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from webstat.core.checker import HttpChecker
from webstat.core.models import CheckResult, MonitoredSite, SiteStatus
from webstat.core.notifier import NotificationDispatcher
from webstat.core.scheduler import WatchScheduler
from webstat.core.store import SiteStore
from webstat.utils.formatting import build_sites_table, get_latency_text, get_status_badge
from webstat.utils.url import get_display_name, normalize_url

app = typer.Typer(
    name="webstat",
    help="Fast website status checker, background watcher, and desktop reminder.",
    no_args_is_help=False,
)
console = Console()


@app.command(name="check")
def check_command(
    url: str = typer.Argument(..., help="Website URL or domain name (e.g. github.com)"),
    watch: bool = typer.Option(
        False,
        "--watch",
        "-w",
        help="Automatically watch in foreground if site is down or not responding",
    ),
    open_browser: bool = typer.Option(
        False,
        "--open",
        "-o",
        help="Automatically open website in default browser when reachable",
    ),
    timeout: float = typer.Option(8.0, "--timeout", "-t", help="HTTP timeout in seconds"),
    check_ssl: bool = typer.Option(False, "--check-ssl", "-s", help="Check TLS/SSL certificate expiration days"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output raw JSON"),
) -> None:
    """Check the status of a website immediately."""
    if timeout <= 0:
        console.print("[bold red]Error:[/bold red] Timeout must be greater than 0.")
        raise typer.Exit(code=1)

    try:
        normalized = normalize_url(url)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    checker = HttpChecker(timeout=timeout, check_ssl=check_ssl)

    with console.status(f"[cyan]Checking[/cyan] {normalized}...", spinner="dots"):
        result = asyncio.run(checker.check(normalized))

    # Automatically update store if site is in watchlist
    store = SiteStore()
    site = store.get_by_id_or_url(normalized)
    if site:
        site.status = result.status
        site.status_code = result.status_code
        site.latency_ms = result.latency_ms
        site.last_checked = result.timestamp
        site.last_error = result.error_message
        if result.is_up:
            site.retries = 0
        else:
            site.retries += 1
        store.update_site(site)

    if json_output:
        print(json.dumps(result.to_dict(), indent=2))
        return

    badge = get_status_badge(result.status, result.status_code)
    latency = get_latency_text(result.latency_ms)

    details = []
    if result.latency_ms:
        details.append(f"Latency: {result.latency_ms} ms")
    if result.redirect_chain:
        details.append(f"Redirects: {' -> '.join(result.redirect_chain)}")
    if result.ssl_expires_days is not None:
        if result.ssl_expires_days < 7:
            details.append(f"[bold yellow]SSL Warning: Expires in {result.ssl_expires_days} days![/bold yellow]")
        else:
            details.append(f"SSL: Valid ({result.ssl_expires_days} days left)")
    if result.error_message:
        details.append(f"[red]Error: {result.error_message}[/red]")

    details_str = "\n".join(details)
    panel_content = f"{badge}  [bold white]{normalized}[/bold white]\n\n{details_str}"

    console.print(
        Panel(
            panel_content,
            title="[bold cyan]Webstat Status[/bold cyan]",
            border_style="green" if result.is_up else "red",
            expand=False,
        )
    )

    if result.is_up:
        if open_browser:
            import subprocess
            subprocess.Popen(["xdg-open", normalized], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return

    # Site is down or non-positive
    if watch:
        console.print("\n[yellow]Site is not responding positively. Entering watch mode...[/yellow]")
        run_watch_loop(
            urls=[url],
            auto_open=open_browser,
            poll_interval=5.0,
            keep_watching=False,
            with_bell=True,
        )


@app.command(name="watch")
def watch_command(
    urls: List[str] = typer.Argument(..., help="One or more website URLs or domains to monitor"),
    open_browser: bool = typer.Option(
        False,
        "--open",
        "-o",
        help="Automatically open website in default browser when reachable",
    ),
    interval: float = typer.Option(
        5.0,
        "--interval",
        "-i",
        help="Polling interval in seconds",
    ),
    keep: bool = typer.Option(
        False,
        "--keep",
        "-k",
        help="Keep watching even after site recovers",
    ),
    no_bell: bool = typer.Option(
        False,
        "--no-bell",
        help="Disable audible terminal bell on recovery",
    ),
) -> None:
    """Watch one or more websites and alert you with desktop notification when they are UP."""
    if interval < 0.5:
        console.print("[bold red]Error:[/bold red] Polling interval must be at least 0.5 seconds.")
        raise typer.Exit(code=1)

    run_watch_loop(
        urls=urls,
        auto_open=open_browser,
        poll_interval=interval,
        keep_watching=keep,
        with_bell=not no_bell,
    )


def run_watch_loop(
    urls: List[str],
    auto_open: bool,
    poll_interval: float,
    keep_watching: bool,
    with_bell: bool,
) -> None:
    store = SiteStore()
    sites: list[MonitoredSite] = []

    for u in urls:
        try:
            site = store.add(
                raw_url=u,
                auto_open=auto_open,
                notify_on_up=True,
                keep_watching=keep_watching,
            )
            sites.append(site)
        except Exception as e:
            console.print(f"[bold red]Skipping invalid URL '{u}':[/bold red] {e}")

    if not sites:
        raise typer.Exit(code=1)

    dispatcher = NotificationDispatcher(with_bell=with_bell)
    scheduler = WatchScheduler(
        store=store,
        dispatcher=dispatcher,
        poll_interval=poll_interval,
    )

    console.print(
        f"[bold cyan]Monitoring {len(sites)} site(s)...[/bold cyan] (Press [bold red]Ctrl+C[/bold red] to stop)\n"
    )

    def render_progress_table() -> Table:
        table = Table(box=None, expand=True, padding=(0, 1))
        table.add_column("Site", style="bold white", width=30)
        table.add_column("Status", width=22)
        table.add_column("Latency", justify="right", width=12)
        table.add_column("Checks", justify="right", width=10)
        table.add_column("Details", style="dim")

        for s in sites:
            badge = get_status_badge(s.status, s.status_code)
            latency = get_latency_text(s.latency_ms)
            checks_count = str(s.retries) if s.retries > 0 else "1"
            details = s.last_error or ("Ready" if s.is_up else "Checking...")
            table.add_row(s.display_name, badge, latency, checks_count, details)

        return table

    recovered_any = False

    try:
        with Live(render_progress_table(), refresh_per_second=2, console=console) as live:
            def on_tick(site: MonitoredSite, result: CheckResult, just_recovered: bool):
                nonlocal recovered_any
                if just_recovered:
                    recovered_any = True
                live.update(render_progress_table())

            asyncio.run(scheduler.watch_sites(sites, on_tick=on_tick))

    except KeyboardInterrupt:
        console.print("\n[yellow]Watch stopped by user.[/yellow]")
        return

    if recovered_any:
        console.print("\n[bold green]✓ Site is back online! Notification sent.[/bold green]")


@app.command(name="add")
def add_command(
    url: str = typer.Argument(..., help="Website URL to add to background watchlist"),
    open_browser: bool = typer.Option(
        False,
        "--open",
        "-o",
        help="Automatically launch browser when site recovers",
    ),
    keep: bool = typer.Option(
        False,
        "--keep",
        "-k",
        help="Keep monitoring continuously even after it recovers",
    ),
) -> None:
    """Add a website to the persistent background monitoring watchlist."""
    store = SiteStore()
    try:
        site = store.add(
            raw_url=url,
            auto_open=open_browser,
            notify_on_up=True,
            keep_watching=keep,
        )
        # Perform fast initial health check so numbers appear immediately
        checker = HttpChecker(timeout=4.0)
        result = asyncio.run(checker.check(site.url))
        site.status = result.status
        site.status_code = result.status_code
        site.latency_ms = result.latency_ms
        site.last_checked = result.timestamp
        site.last_error = result.error_message
        store.update_site(site)

        console.print(f"[bold green]Added:[/bold green] {site.display_name} ({site.url}) [{site.status.value}]")
    except Exception as e:
        console.print(f"[bold red]Failed to add site:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command(name="list")
def list_command(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output raw JSON array"),
) -> None:
    """List all currently watched websites and their statuses."""
    store = SiteStore()
    sites = store.load_all()

    if json_output:
        data = [s.to_dict() for s in sites]
        print(json.dumps(data, indent=2))
        return

    if not sites:
        console.print("[dim]No websites in watchlist. Add one with: [bold cyan]webstat add <url>[/bold cyan][/dim]")
        return

    console.print(build_sites_table(sites))


@app.command(name="remove")
def remove_command(
    target: str = typer.Argument(..., help="URL, domain name, or site ID to remove"),
) -> None:
    """Remove a website from the monitoring watchlist."""
    store = SiteStore()
    if store.remove(target):
        console.print(f"[bold green]Removed:[/bold green] '{target}' from watchlist.")
    else:
        console.print(f"[bold red]Not found:[/bold red] No site matching '{target}' in watchlist.")
        raise typer.Exit(code=1)


@app.command(name="clear")
def clear_command() -> None:
    """Clear all websites from the watchlist."""
    store = SiteStore()
    store.clear()
    console.print("[bold green]Watchlist cleared.[/bold green]")


@app.command(name="refresh")
def refresh_command() -> None:
    """Check all monitored websites immediately and update their status."""
    store = SiteStore()
    sites = store.load_all()
    if not sites:
        console.print("[dim]No websites in watchlist.[/dim]")
        return
    dispatcher = NotificationDispatcher()
    checker = HttpChecker()
    scheduler = WatchScheduler(store=store, dispatcher=dispatcher, checker=checker)

    async def run_all():
        sem = asyncio.Semaphore(10)

        async def bounded_check(s):
            async with sem:
                return await scheduler.check_and_update(s)

        tasks = [bounded_check(s) for s in sites]
        await asyncio.gather(*tasks)

    asyncio.run(run_all())
    console.print(f"[bold green]Refreshed {len(sites)} website(s).[/bold green]")


@app.command(name="daemon")
def daemon_command(
    interval: float = typer.Option(10.0, "--interval", "-i", help="Polling interval in seconds"),
) -> None:
    """Run the continuous background monitoring daemon."""
    if interval < 1.0:
        console.print("[bold red]Error:[/bold red] Daemon polling interval must be at least 1.0 second.")
        raise typer.Exit(code=1)

    store = SiteStore()
    dispatcher = NotificationDispatcher()
    checker = HttpChecker()
    scheduler = WatchScheduler(store=store, dispatcher=dispatcher, checker=checker, poll_interval=interval)

    console.print("[bold cyan]webstat daemon started.[/bold cyan] Watching state queue...")

    async def daemon_loop():
        while True:
            sites = store.load_all()
            # Only poll sites that are either down or marked keep_watching
            to_poll = [s for s in sites if not s.is_up or s.keep_watching or s.status == SiteStatus.UNKNOWN]
            if to_poll:
                for site in to_poll:
                    result, just_recovered = await scheduler.check_and_update(site)
                    if just_recovered:
                        console.print(f"[green]Recovered:[/green] {site.display_name} -> {result.status_code} OK")
            await asyncio.sleep(interval)

    try:
        asyncio.run(daemon_loop())
    except KeyboardInterrupt:
        console.print("\n[yellow]webstat daemon stopped.[/yellow]")


KNOWN_COMMANDS = {"check", "watch", "add", "list", "remove", "clear", "refresh", "daemon"}


@app.callback()
def main_callback() -> None:
    """webstat: Website status checker and desktop recovery reminder."""
    pass


def main() -> None:
    # If the first non-flag argument is not a known subcommand, default to "check"
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-") and sys.argv[1] not in KNOWN_COMMANDS:
        sys.argv.insert(1, "check")
    app()


if __name__ == "__main__":
    main()
