"""CLI entry point using Typer and Rich."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TaskProgressColumn
from rich.table import Table

from dj_dl.analyzer import analyze_track, is_analyzed
from dj_dl.auth import authenticate_apple_music_interactive
from dj_dl.config import Config, load_config
from dj_dl.downloader import DownloadJob, DownloadManager
from dj_dl.providers.applemusic import AppleMusicProvider
from dj_dl.providers.base import detect_provider
from dj_dl.providers.spotify import SpotifyProvider
from dj_dl.providers.youtube import YouTubeProvider

app = typer.Typer(no_args_is_help=True)
console = Console()

KNOWN_COMMANDS = {"download", "set-folder", "analyze", "auth", "update"}


def get_provider(name: str, config: Config) -> Any:
    if name == "youtube":
        return YouTubeProvider()
    elif name == "spotify":
        return SpotifyProvider(
            client_id=config.spotify.client_id,
            client_secret=config.spotify.client_secret,
        )
    elif name == "apple_music":
        return AppleMusicProvider(cookies_path=config.apple_music.cookies_path)
    else:
        raise typer.BadParameter(f"Unknown provider: {name}")


@app.command()
def download(
    url: str = typer.Argument(..., help="YouTube / Spotify / Apple Music URL"),
) -> None:
    config = load_config()
    provider_name = detect_provider(url)

    if provider_name == "unknown":
        console.print("[red]Error:[/red] Could not detect platform from URL.")
        raise typer.Exit(1)

    provider = get_provider(provider_name, config)
    manager = DownloadManager(config)

    async def _download() -> None:
        with Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            result = await provider.extract(url)
            if not result.tracks:
                console.print("[red]No tracks found.[/red]")
                raise typer.Exit(1)

            task = progress.add_task(
                f"[cyan]Downloading from {provider_name}...",
                total=len(result.tracks),
                completed=0,
            )

            async def _track_cb(job: DownloadJob) -> None:
                progress.update(task, advance=1)
                progress.print(f"[green]✓[/green] {job.track.title}")

            report = await manager.download(result, provider, _track_cb)

        table = Table(title="Download Report")
        table.add_column("Status", style="cyan")
        table.add_column("Count", style="magenta")
        table.add_row("Completed", str(report.completed))
        table.add_row("Failed", str(report.failed))
        table.add_row("Skipped", str(report.skipped))
        console.print(table)

        if report.errors:
            console.print("[red]Errors:[/red]")
            for err in report.errors:
                console.print(f"  - {err}")

        # Raised after the report is printed, so the counts stay visible. Without this a
        # run where every track failed is indistinguishable from a successful one to any
        # caller that checks the exit status.
        if report.failed:
            raise typer.Exit(1)

    asyncio.run(_download())


@app.command()
def set_folder(
    path: str = typer.Argument(None, help="Output directory path"),
) -> None:
    config = load_config()

    if path is None:
        console.print(f"Current output folder: [cyan]{config.output_dir}[/cyan]")
        return

    new_path = Path(path).expanduser().resolve()
    new_path.mkdir(parents=True, exist_ok=True)
    config.output_dir = new_path
    config.save()
    console.print(f"Output folder set to: [green]{new_path}[/green]")


@app.command()
def analyze(
    folder: str = typer.Argument(None, help="Folder to scan. Defaults to set-folder path."),
) -> None:
    config = load_config()
    target = Path(folder).expanduser() if folder else config.output_dir

    if not target.exists():
        console.print(f"[red]Folder not found: {target}[/red]")
        raise typer.Exit(1)

    audio_files = (
        list(target.rglob("*.m4a")) + list(target.rglob("*.mp3")) + list(target.rglob("*.flac"))
    )

    analyzed = 0
    skipped = 0
    errors = 0

    with Progress(console=console) as progress:
        task = progress.add_task("[cyan]Analyzing tracks...", total=len(audio_files))

        for filepath in audio_files:
            if is_analyzed(filepath):
                skipped += 1
                progress.advance(task)
                continue

            try:
                result = analyze_track(filepath)
                analyzed += 1
                progress.print(
                    f"[green]✓[/green] {filepath.name} — {result.bpm:.1f} BPM, {result.key}"
                )
            except Exception as e:
                errors += 1
                progress.print(f"[red]✗[/red] {filepath.name} — {e}")

            progress.advance(task)

    table = Table(title="Analysis Report")
    table.add_column("Status", style="cyan")
    table.add_column("Count", style="magenta")
    table.add_row("Analyzed", str(analyzed))
    table.add_row("Skipped (already analyzed)", str(skipped))
    table.add_row("Errors", str(errors))
    console.print(table)


@app.command()
def auth(
    token: str = typer.Option(
        None, "--token", help="Paste media-user-token directly (non-interactive)"
    ),
) -> None:
    if token:
        from dj_dl.auth import _save_cookies

        config = load_config()
        config.apple_music.cookies_path = _save_cookies(token)
        config.save()
        console.print("[green]Apple Music auth saved.[/green]")
        return

    success, message = authenticate_apple_music_interactive()
    if not success:
        console.print(f"[red]{message}[/red]")
        raise typer.Exit(1)


@app.command()
def update() -> None:
    repo_dir = Path.home() / ".djdl"

    if not (repo_dir / ".git").exists():
        console.print("[red]Error:[/red] Repository not found at ~/.djdl")
        raise typer.Exit(1)

    console.print("[cyan]Pulling latest changes...[/cyan]")
    result = subprocess.run(["git", "pull"], cwd=repo_dir, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[red]git pull failed:[/red] {result.stderr}")
        raise typer.Exit(1)
    console.print(result.stdout)

    console.print("[cyan]Upgrading djdl...[/cyan]")
    result = subprocess.run(
        ["uv", "tool", "install", "-e", ".", "--quiet"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        console.print(f"[red]Upgrade failed:[/red] {result.stderr}")
        raise typer.Exit(1)
    console.print("[green]djdl updated successfully![/green]")


def main() -> None:
    args = sys.argv[1:]
    if args and not args[0].startswith("-") and args[0] not in KNOWN_COMMANDS:
        sys.argv.insert(1, "download")
    app()


if __name__ == "__main__":
    main()
