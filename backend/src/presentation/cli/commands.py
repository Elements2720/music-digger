"""Typer + Rich command line: catalog, indexing, and similarity digging."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, TypeVar

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from container import Container
from domain.entities.search import SearchFilter
from domain.use_cases import (
    DEFAULT_TECHNO_TERMS,
    SetNotEmbeddedError,
    SetNotFoundError,
    TrackNotEmbeddedError,
    TrackNotFoundError,
)

T = TypeVar("T")

app = typer.Typer(
    name="dig",
    help="DigDeeper Local: local DJ catalog and seed management.",
    no_args_is_help=True,
)
console = Console()


def main() -> None:
    """Console-script entry point."""
    app()


@app.command("check-hw")
def check_hw() -> None:
    """Verify ffmpeg, PyTorch, CUDA, GPU, VRAM, and RAM on this machine."""

    async def run() -> None:
        async with Container() as container:
            assert container.hardware_probe is not None
            info = await asyncio.to_thread(container.hardware_probe.probe)

        table = Table(title="Hardware check")
        table.add_column("Component")
        table.add_column("Value")
        table.add_row(
            "ffmpeg",
            (
                f"[green]{info.ffmpeg_path}[/]\n[dim]{info.ffmpeg_version}[/]"
                if info.has_ffmpeg
                else "[red]not found — install FFmpeg and add it to PATH[/]"
            ),
        )
        table.add_row(
            "PyTorch",
            info.torch_version or "[red]not installed[/]",
        )
        if info.cuda_available:
            assert info.gpu_name is not None
            table.add_row(
                "CUDA",
                f"[green]available[/] (CUDA {info.cuda_version or '?'})",
            )
            table.add_row("GPU", info.gpu_name)
            table.add_row("VRAM (free/total)", info.vram_summary())
        else:
            table.add_row(
                "CUDA",
                "[yellow]unavailable — CLAP will run on CPU[/]",
            )
            table.add_row("GPU", "[dim]none detected[/]")
        table.add_row("RAM (free/total)", info.ram_summary())
        console.print(table)

        if not info.has_ffmpeg or info.torch_version is None:
            console.print(
                "[yellow]Warning:[/] audio indexing needs both ffmpeg and "
                "PyTorch installed."
            )

    _run(run())


@app.command("index")
def index(
    limit: int = typer.Option(
        500,
        "--limit",
        min=0,
        help="Maximum tracks to index in this run (0 = all pending).",
    ),
    batch_size: int = typer.Option(
        16,
        "--batch-size",
        min=1,
        max=48,
        help="GPU micro-batch size (cap 48; lower it if VRAM runs out).",
    ),
    retry_failed: bool = typer.Option(
        False,
        "--retry-failed",
        help="Re-queue tracks that failed on earlier runs (ignore failure counts).",
    ),
    reindex: bool = typer.Option(
        False,
        "--reindex",
        help="Re-embed tracks that already have embeddings (after ML changes).",
    ),
    turbo: bool = typer.Option(
        False,
        "--turbo",
        help="Max out the hardware: 10 analysis workers, batch 48, "
        "24 concurrent downloads.",
    ),
) -> None:
    """Download previews, extract BPM/key, embed with CLAP, and persist."""

    if turbo:
        # Must be set before Container() builds Settings, which reads env at
        # instantiation time (.env values never override the process env).
        os.environ["ANALYSIS_MAX_WORKERS"] = "10"
        os.environ["CLAP_BATCH_SIZE"] = "48"
        os.environ["PREVIEW_CONCURRENCY"] = "24"

    async def run() -> None:
        async with Container() as container:
            assert container.index_catalog is not None
            assert container.track_repository is not None
            assert container.hardware_probe is not None
            if reindex:
                # Re-embedding touches every catalog track with a preview.
                total_estimate = await container.track_repository.count()
            else:
                total_estimate = await container.track_repository.count() - (
                    await container.track_repository.count_embedded()
                )
            total = min(total_estimate, limit) if limit else total_estimate
            # Warm the ffmpeg/torch caches so per-tick probes stay cheap.
            await asyncio.to_thread(container.hardware_probe.probe)

            progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TextColumn("{task.fields[speed]}"),
                TextColumn("{task.fields[failed]}"),
                TextColumn("{task.fields[memory]}"),
                TimeElapsedColumn(),
                console=console,
            )
            start = time.monotonic()
            with progress:
                task = progress.add_task(
                    "Indexing", total=total, speed="", failed="", memory=""
                )

                def on_progress(event: Any) -> None:
                    elapsed = max(time.monotonic() - start, 1e-6)
                    speed = event.processed / elapsed
                    progress.update(
                        task,
                        completed=event.processed,
                        description="[cyan]Indexing previews[/]",
                        speed=f"[blue]{speed:.1f} tracks/s[/]",
                        failed=f"[red]failed: {event.failed}[/]"
                        if event.failed
                        else "",
                        memory=_format_memory(container.hardware_probe),
                    )

                result = await container.index_catalog.execute(
                    # `--limit 0` means "no cap": translate to a huge number.
                    limit=limit or 10**9,
                    batch_size=batch_size,
                    # `--retry-failed` re-queues tracks regardless of how many
                    # times they have failed before (transient-bug recovery).
                    max_failures=10**9 if retry_failed else 3,
                    reindex=reindex,
                    progress=on_progress,
                )

            table = Table(title="Index run")
            table.add_column("Metric")
            table.add_column("Value", justify="right")
            table.add_row("Tracks indexed", str(result.processed))
            table.add_row("Tracks failed", str(result.failed))
            table.add_row("Embedded total", str(result.embedded_total))
            console.print(table)

    _run(run())


@app.command("import-local")
def import_local(
    folder_path: Path = typer.Argument(
        ...,
        help="Path to local folder containing audio files.",
    ),
    recursive: bool = typer.Option(
        True,
        "--recursive/--no-recursive",
        help="Recursively scan subfolders for audio files.",
    ),
    batch_size: int = typer.Option(
        16,
        "--batch-size",
        min=1,
        max=48,
        help="GPU micro-batch size for CLAP embeddings.",
    ),
    reindex: bool = typer.Option(
        False,
        "--reindex",
        help="Re-embed already embedded local tracks.",
    ),
    seed_artists: bool = typer.Option(
        True,
        "--seed-artists/--no-seed-artists",
        help="Seed unique artists into discovery at priority 1.0.",
    ),
) -> None:
    """Scan local audio folder, decode middle windows, embed, and seed artists."""

    async def run() -> None:
        async with Container() as container:
            assert container.import_local_library is not None

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Importing local library", total=None)

                def on_progress(event: Any) -> None:
                    desc = f"[cyan]{event.stage}[/]"
                    if event.message:
                        desc = f"[cyan]{event.stage}[/] {event.message}"
                    progress.update(
                        task,
                        total=event.total,
                        completed=event.completed,
                        description=desc,
                    )

                result = await container.import_local_library.execute(
                    folder_path,
                    recursive=recursive,
                    batch_size=batch_size,
                    reindex=reindex,
                    seed_artists=seed_artists,
                    progress=on_progress,
                )

            table = Table(title="Local library import")
            table.add_column("Metric")
            table.add_column("Value", justify="right")
            table.add_row("Files scanned", str(result.scanned))
            table.add_row("Tracks imported", str(result.imported))
            table.add_row("Tracks embedded", str(result.embedded))
            table.add_row("Tracks failed", str(result.failed))
            table.add_row("Artists seeded", str(result.artists_seeded))
            console.print(table)

    _run(run())


@app.command("reset-embeddings")
def reset_embeddings(
    force: bool = typer.Option(
        False,
        "--force",
        help="Skip the confirmation prompt.",
    ),
) -> None:
    """Drop all stored embeddings so the next `dig index` re-embeds cleanly."""

    async def run() -> None:
        async with Container() as container:
            assert container.track_repository is not None
            embedded = await container.track_repository.count_embedded()
            if embedded == 0:
                console.print("No embeddings stored — nothing to reset.")
                return
            if not force:
                confirmed = typer.confirm(
                    f"Delete {embedded} stored embedding(s)? Track metadata is kept."
                )
                if not confirmed:
                    raise typer.Abort()
            cleared = await container.track_repository.reset_embeddings()
            console.print(
                f"[green]Cleared {cleared} embedding(s).[/] "
                "Run `dig index` to re-embed the catalog."
            )

    _run(run())


@app.command("dig")
def dig(
    track_id: str = typer.Argument(..., help="Track id to dig from."),
    limit: int = typer.Option(10, "--limit", min=1, help="Matches to show."),
    bpm_tolerance: float | None = typer.Option(
        None,
        "--bpm-tolerance",
        help="Restrict matches to reference BPM ± tolerance.",
    ),
    harmonic: bool = typer.Option(
        False,
        "--harmonic",
        help="Restrict matches to harmonically compatible Camelot keys.",
    ),
    genre: str | None = typer.Option(
        None,
        "--genre",
        help="Exact genre filter (case-insensitive).",
    ),
    exclude_heard: bool = typer.Option(
        False, "--exclude-heard", help="Skip tracks already marked heard."
    ),
) -> None:
    """Find the closest sounding tracks to a catalog track."""

    async def run() -> None:
        async with Container() as container:
            assert container.dig_similar_tracks is not None
            search_filter = SearchFilter(
                limit=limit, genre_filter=genre, exclude_heard=exclude_heard
            )
            try:
                result = await container.dig_similar_tracks.execute(
                    track_id,
                    search_filter,
                    bpm_tolerance=bpm_tolerance,
                    harmonic=harmonic,
                )
            except (TrackNotFoundError, TrackNotEmbeddedError) as exc:
                console.print(f"[red]Error:[/] {exc}")
                raise typer.Exit(1) from exc

        reference = result.reference
        console.print(
            f"[bold]Digging from:[/] {reference.display_name}"
            + (f" [dim]({reference.bpm}, {reference.key})[/]" if reference.bpm else "")
        )
        if not result.matches:
            console.print("[yellow]No matching tracks found.[/]")
            return
        table = Table(title=f"Top {len(result.matches)} matches")
        table.add_column("Title")
        table.add_column("Artist")
        table.add_column("Match %", justify="right")
        table.add_column("BPM", justify="right")
        table.add_column("Key", justify="center")
        table.add_column("Genre")
        for match in result.matches:
            track = match.track
            table.add_row(
                track.title,
                track.artist,
                f"{match.similarity_percent:.1f}",
                f"{track.bpm.value:g}" if track.bpm else "—",
                track.key.notation if track.key else "—",
                track.genre or "—",
            )
        console.print(table)

    _run(run())


@app.command("list-tracks")
def list_tracks(
    limit: int = typer.Option(20, "--limit", min=1, help="Rows to show."),
    offset: int = typer.Option(0, "--offset", min=0, help="Rows to skip."),
) -> None:
    """List embedded tracks (id, BPM, key) so you can pick one to dig from."""

    async def run() -> None:
        async with Container() as container:
            assert container.track_repository is not None
            tracks = await container.track_repository.list_embedded(
                limit=limit, offset=offset
            )
            embedded_total = await container.track_repository.count_embedded()

        if not tracks:
            console.print("[yellow]No embedded tracks yet.[/] Run `dig index` first.")
            return
        table = Table(title=f"Embedded tracks ({embedded_total} total)")
        table.add_column("ID", style="dim")
        table.add_column("Artist")
        table.add_column("Title")
        table.add_column("BPM", justify="right")
        table.add_column("Key", justify="center")
        for track in tracks:
            table.add_row(
                track.id,
                track.artist,
                track.title,
                f"{track.bpm.value:g}" if track.bpm else "—",
                track.key.notation if track.key else "—",
            )
        console.print(table)

    _run(run())


@app.command("analyze-set")
def analyze_set(
    source: str = typer.Argument(
        ...,
        help="DJ set URL (YouTube/SoundCloud/Mixcloud/...) or local audio file path.",
    ),
    shazam: bool = typer.Option(
        True,
        "--shazam/--no-shazam",
        help="Identify unidentified passages via Shazam fingerprinting.",
    ),
    comments: bool = typer.Option(
        True,
        "--comments/--no-comments",
        help="Extract a tracklist from post comments via the local LLM.",
    ),
    keep_audio: bool = typer.Option(
        False,
        "--keep-audio",
        help="Keep the downloaded audio in the storage cache after analysis.",
    ),
    shazam_probes: int = typer.Option(
        3,
        "--shazam-probes",
        min=1,
        max=5,
        help="Number of Shazam probe positions per passage (default 3: 50%, 30%, 70% with early exit).",
    ),
    cookies: Path | None = typer.Option(
        None,
        "--cookies",
        help="Netscape cookies.txt for this run (one-off override for "
        "YTDLP_COOKIES_FILE; wins over --cookies-from-browser).",
    ),
    cookies_from_browser: str | None = typer.Option(
        None,
        "--cookies-from-browser",
        help="Browser profile to read cookies from for this run (one-off "
        "override for YTDLP_COOKIES_FROM_BROWSER): firefox, edge, chrome, "
        "brave, chromium, ...",
    ),
) -> None:
    """Download (or locate) a DJ set, split it into passages, and identify them."""

    async def run() -> None:
        async with Container() as container:
            assert container.analyze_dj_set is not None
            assert container.set_downloader is not None
            container.set_downloader.apply_cookie_overrides(
                cookies_file=cookies,
                cookies_from_browser=cookies_from_browser,
            )
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TextColumn("{task.fields[detail]}"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Analyzing set", total=None, detail="")

                def on_progress(event: Any) -> None:
                    progress.update(
                        task,
                        total=event.total or None,
                        completed=event.completed,
                        description=f"[cyan]{event.stage}[/]",
                        detail=event.message,
                    )

                dj_set = await container.analyze_dj_set.execute(
                    source,
                    destination_dir=container.settings.set_cache_dir,
                    use_shazam=shazam,
                    use_comments=comments,
                    keep_audio=keep_audio,
                    shazam_probes=shazam_probes,
                    progress=on_progress,
                )

        identified = sum(1 for p in dj_set.passages if p.exact_id_match)
        table = Table(title="Set analyzed")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        table.add_row("Set ID", dj_set.id)
        table.add_row("Title", dj_set.title)
        if dj_set.artist:
            table.add_row("Artist", dj_set.artist)
        table.add_row("Passages", str(len(dj_set.passages)))
        table.add_row("Identified", str(identified))
        if dj_set.bpm_min is not None and dj_set.bpm_max is not None:
            table.add_row(
                "BPM range",
                f"{dj_set.bpm_min.value:g} - {dj_set.bpm_max.value:g}",
            )
        console.print(table)
        console.print(
            f"Dig into it with: [bold]dig show-set {dj_set.id} --tab tracks[/]"
        )

    _run(run())


@app.command("show-set")
def show_set(
    set_id: str = typer.Argument(..., help="DJ set id (see `dig list-sets`)."),
    tab: str = typer.Option(
        "tracklist",
        "--tab",
        help="Which view to show: tracklist (IDs), tracks (dig), or sets.",
    ),
    limit: int = typer.Option(30, "--limit", min=1, help="Rows to show."),
    bpm_tolerance: float | None = typer.Option(
        None,
        "--bpm-tolerance",
        help="Restrict the tracks view to passage BPM ± tolerance.",
    ),
    exclude_heard: bool = typer.Option(
        False, "--exclude-heard", help="Skip tracks already marked heard."
    ),
    genre: str | None = typer.Option(
        None,
        "--genre",
        help="Exact genre filter (case-insensitive) for the tracks view.",
    ),
) -> None:
    """Show a stored DJ set: its IDs, its closest tracks, or similar sets."""

    async def run() -> None:
        async with Container() as container:
            assert container.set_repository is not None
            assert container.find_similar_for_set is not None
            try:
                found = await container.set_repository.get_by_id(set_id)
                if found is None:
                    raise SetNotFoundError(f"DJ set {set_id!r} is not stored locally")
                if tab == "tracklist":
                    _print_set_tracklist(found)
                elif tab == "tracks":
                    search_filter = SearchFilter(
                        limit=min(limit, 500),
                        genre_filter=genre,
                        exclude_heard=exclude_heard,
                    )
                    dig_result = await container.find_similar_for_set.similar_tracks(
                        set_id,
                        search_filter,
                        limit=limit,
                        bpm_tolerance=bpm_tolerance,
                    )
                    _print_set_dig(found, dig_result.matches)
                elif tab == "sets":
                    matches = await container.find_similar_for_set.similar_sets(
                        set_id, limit=limit
                    )
                    _print_similar_sets(found, matches)
                else:
                    console.print(
                        f"[red]Error:[/] unknown --tab {tab!r} "
                        "(use tracklist, tracks, or sets)"
                    )
                    raise typer.Exit(1)
            except (SetNotFoundError, SetNotEmbeddedError) as exc:
                console.print(f"[red]Error:[/] {exc}")
                raise typer.Exit(1) from exc

    _run(run())


@app.command("list-sets")
def list_sets(
    limit: int = typer.Option(20, "--limit", min=1, help="Rows to show."),
) -> None:
    """List analyzed DJ sets so you can pick one to show or dig from."""

    async def run() -> None:
        async with Container() as container:
            assert container.set_repository is not None
            sets = await container.set_repository.list_all(limit=limit)
            total = await container.set_repository.count()

        if not sets:
            console.print(
                "[yellow]No analyzed sets yet.[/] Run `dig analyze-set` first."
            )
            return
        table = Table(title=f"Analyzed sets ({total} total)")
        table.add_column("ID", style="dim")
        table.add_column("Artist")
        table.add_column("Title")
        table.add_column("Passages", justify="right")
        table.add_column("IDs", justify="right")
        table.add_column("BPM", justify="right")
        for dj_set in sets:
            identified = sum(1 for p in dj_set.passages if p.exact_id_match)
            bpm = (
                f"{dj_set.bpm_min.value:g}–{dj_set.bpm_max.value:g}"
                if dj_set.bpm_min is not None and dj_set.bpm_max is not None
                else "—"
            )
            table.add_row(
                dj_set.id,
                dj_set.artist or "—",
                dj_set.title,
                str(len(dj_set.passages)),
                str(identified),
                bpm,
            )
        console.print(table)

    _run(run())


@app.command("mark-heard")
def mark_heard(
    track_id: str = typer.Argument(..., help="Track id to mark as heard."),
) -> None:
    """Mark a track as heard so `--exclude-heard` skips it in future digs."""

    async def run() -> None:
        async with Container() as container:
            assert container.track_repository is not None
            found = await container.track_repository.get_by_id(track_id)
            if found is None:
                console.print(
                    f"[red]Error:[/] track {track_id!r} is not in the catalog"
                )
                raise typer.Exit(1)
            await container.track_repository.mark_heard(track_id)
        console.print(f"[green]Marked {found.display_name} as heard.[/]")

    _run(run())


def _print_set_tracklist(dj_set: Any) -> None:
    """The classic tracklist view: every identified passage in order."""
    console.print(
        f"[bold]{dj_set.title}[/]"
        + (f" [dim]by {dj_set.artist}[/]" if dj_set.artist else "")
        + f" [dim]({dj_set.id})[/]"
    )
    identified = [passage for passage in dj_set.passages if passage.exact_id_match]
    if not identified:
        console.print(
            "[yellow]No identified tracks.[/] "
            "Try `--tab tracks` for the closest matches found per passage."
        )
        return
    table = Table(title=f"Tracklist ({len(identified)} identified)")
    table.add_column("Start")
    table.add_column("Artist")
    table.add_column("Title")
    table.add_column("Via", justify="center")
    table.add_column("BPM", justify="right")
    for passage in identified:
        start_seconds = passage.time_range.start_seconds
        minutes, seconds = divmod(int(start_seconds), 60)
        hours, minutes = divmod(minutes, 60)
        clock = (
            f"{hours:d}:{minutes:02d}:{seconds:02d}"
            if hours
            else f"{minutes:02d}:{seconds:02d}"
        )
        table.add_row(
            clock,
            passage.exact_id_artist or "—",
            passage.exact_id_title or "—",
            passage.exact_id_source or "—",
            f"{passage.bpm.value:g}" if passage.bpm else "—",
        )
    console.print(table)


def _print_set_dig(dj_set: Any, matches: Any) -> None:
    console.print(f"[bold]Digging from set:[/] {dj_set.title} [dim]({dj_set.id})[/]")
    if not matches:
        console.print("[yellow]No matching tracks found.[/]")
        return
    table = Table(title=f"Top {len(matches)} matches across all passages")
    table.add_column("Title")
    table.add_column("Artist")
    table.add_column("Match %", justify="right")
    table.add_column("BPM", justify="right")
    table.add_column("Key", justify="center")
    table.add_column("Genre")
    for match in matches:
        track = match.track
        table.add_row(
            track.title,
            track.artist,
            f"{match.similarity_percent:.1f}",
            f"{track.bpm.value:g}" if track.bpm else "—",
            track.key.notation if track.key else "—",
            track.genre or "—",
        )
    console.print(table)


def _print_similar_sets(dj_set: Any, matches: Any) -> None:
    console.print(f"[bold]Sets like:[/] {dj_set.title} [dim]({dj_set.id})[/]")
    if not matches:
        console.print(
            "[yellow]No similar sets yet.[/] Analyze more sets with `dig analyze-set`."
        )
        return
    table = Table(title=f"Top {len(matches)} similar sets")
    table.add_column("ID", style="dim")
    table.add_column("Artist")
    table.add_column("Title")
    table.add_column("Match %", justify="right")
    for match in matches:
        table.add_row(
            match.dj_set.id,
            match.dj_set.artist or "—",
            match.dj_set.title,
            f"{match.similarity_percent:.1f}",
        )
    console.print(table)


def _format_memory(probe: Any) -> str:
    """One-line RAM/VRAM readout from the wired hardware probe."""
    try:
        info = probe.probe()
        parts: list[str] = []
        if info.ram_total_mb is not None:
            used = info.ram_total_mb - (info.ram_free_mb or 0)
            parts.append(f"RAM {used / 1024:.1f}/{info.ram_total_mb / 1024:.1f} GB")
        if info.vram_total_mb is not None and info.vram_free_mb is not None:
            used = info.vram_total_mb - info.vram_free_mb
            parts.append(f"VRAM {used / 1024:.1f}/{info.vram_total_mb / 1024:.1f} GB")
        return f"[dim]{' · '.join(parts)}[/]" if parts else ""
    except Exception:  # noqa: BLE001 - memory display must never break indexing
        return ""


@app.command("seed-crawl")
def seed_crawl(
    electronic_limit: int = typer.Option(
        1000,
        "--electronic-limit",
        min=0,
        help="Maximum electronic/club seeds to discover.",
    ),
    general_limit: int = typer.Option(
        300,
        "--general-limit",
        min=0,
        help="Maximum general-genre seeds to discover.",
    ),
    max_depth: int = typer.Option(
        2,
        "--max-depth",
        min=0,
        help="Deezer related-artist BFS depth.",
    ),
    use_local_seeds: bool = typer.Option(
        False,
        "--use-local-seeds",
        help="Use artists discovered from local library as crawl roots.",
    ),
) -> None:
    """Populate seed_artists from Deezer's related-artist graph and charts."""

    async def run() -> None:
        async with Container() as container:
            assert container.build_seed_list is not None
            total = electronic_limit + general_limit
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Crawling Deezer", total=total)

                def on_progress(event: Any) -> None:
                    desc = f"[cyan]{event.stage}[/]"
                    if event.name:
                        desc = f"[cyan]{event.stage}[/] {event.name}"
                    progress.update(
                        task,
                        completed=event.found,
                        description=desc,
                    )

                result = await container.build_seed_list.execute(
                    electronic_limit=electronic_limit,
                    general_limit=general_limit,
                    max_depth=max_depth,
                    use_deezer=True,
                    progress=on_progress,
                    use_local_seeds=use_local_seeds,
                )
            _print_seed_result(result)

    _run(run())


@app.command("seed-llm")
def seed_llm(
    genre: str = typer.Option(
        ...,
        "--genre",
        "-g",
        help='Genre focus, for example "Melodic Techno & Afro House".',
    ),
    count: int = typer.Option(
        100,
        "--count",
        min=1,
        help="Number of curated artists to request from the LLM.",
    ),
) -> None:
    """Ask the configured local LLM for additional underground seed artists."""

    async def run() -> None:
        async with Container() as container:
            assert container.build_seed_list is not None
            genres = tuple(part.strip() for part in genre.split(",") if part.strip())
            result = await container.build_seed_list.execute(
                use_deezer=False,
                llm_genres=genres,
                llm_count=count,
            )
            _print_seed_result(result)

    _run(run())


@app.command("seed-itunes")
def seed_itunes(
    terms: str | None = typer.Option(
        None,
        "--terms",
        "-t",
        help="Comma-separated keywords/labels to crawl (omitted = built-in techno list).",
    ),
    tracks_per_term: int = typer.Option(
        200,
        "--tracks-per-term",
        min=1,
        max=200,
        help="Maximum tracks per keyword (iTunes limit 200).",
    ),
    expand_compilations: bool = typer.Option(
        True,
        "--expand-compilations/--no-expand-compilations",
        help="Expand multi-artist compilation albums into full tracklists.",
    ),
    save_tracks: bool = typer.Option(
        True,
        "--save-tracks/--no-save-tracks",
        help="Persist tracks immediately into track repository.",
    ),
) -> None:
    """Crawl underground techno terms, labels, and compilations on iTunes."""

    async def run() -> None:
        async with Container() as container:
            assert container.crawl_itunes_seeds is not None
            parsed_terms: tuple[str, ...] | None = None
            if terms is not None:
                parts = tuple(p.strip() for p in terms.split(",") if p.strip())
                if not parts:
                    console.print("[red]Error:[/] --terms must not be empty")
                    raise typer.Exit(1)
                parsed_terms = parts
            effective_terms = (
                parsed_terms if parsed_terms is not None else DEFAULT_TECHNO_TERMS
            )
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    "Crawling iTunes keywords", total=len(effective_terms)
                )

                def on_progress(
                    term: str, index: int, total: int, tracks_found: int
                ) -> None:
                    progress.update(
                        task,
                        total=total,
                        completed=index,
                        description=f"[cyan]{term}[/] ({tracks_found} tracks)",
                    )

                result = await container.crawl_itunes_seeds.execute(
                    terms=parsed_terms,
                    tracks_per_term=tracks_per_term,
                    expand_compilations=expand_compilations,
                    save_tracks=save_tracks,
                    progress=on_progress,
                )

            table = Table(title="iTunes keyword crawl")
            table.add_column("Metric")
            table.add_column("Value", justify="right")
            table.add_row("Terms processed", str(result.terms_processed))
            table.add_row("Terms failed", str(result.terms_failed))
            table.add_row("Tracks found", str(result.tracks_found))
            table.add_row("Tracks saved", str(result.tracks_saved))
            table.add_row("Artists discovered", str(result.artists_discovered))
            console.print(table)

    _run(run())


@app.command("fetch-metadata")
def fetch_metadata(
    artists_limit: int = typer.Option(
        50,
        "--artists-limit",
        min=1,
        help="Maximum pending/failed seeds to fetch in this run.",
    ),
    tracks_per_artist: int = typer.Option(
        200,
        "--tracks-per-artist",
        min=1,
        help="Maximum tracks to keep per artist (iTunes returns up to 200).",
    ),
    retry_failed: bool = typer.Option(
        False,
        "--retry-failed",
        help="Retry seeds marked failed by an earlier run.",
    ),
) -> None:
    """Fetch iTunes metadata for the highest-priority pending seeds."""

    async def run() -> None:
        async with Container() as container:
            assert container.fetch_catalog_metadata is not None
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Fetching iTunes metadata", total=None)

                def on_progress(seed: Any, index: int, total: int) -> None:
                    progress.update(
                        task,
                        total=total,
                        completed=index - 1,
                        description=f"[cyan]{seed.name}[/]",
                    )

                result = await container.fetch_catalog_metadata.execute(
                    artists_limit=artists_limit,
                    tracks_per_artist=tracks_per_artist,
                    retry_failed=retry_failed,
                    progress=on_progress,
                )
                progress.update(task, completed=result.artists_processed)

            table = Table(title="Metadata fetch")
            table.add_column("Metric")
            table.add_column("Value", justify="right")
            table.add_row("Artists processed", str(result.artists_processed))
            table.add_row("Artists failed", str(result.artists_failed))
            table.add_row("Tracks found", str(result.tracks_found))
            table.add_row("Tracks saved", str(result.tracks_saved))
            console.print(table)

    _run(run())


@app.command("fetch-artist")
def fetch_artist(
    artist: str = typer.Argument(
        ...,
        help="Artist name to fetch from iTunes.",
    ),
    tracks: int = typer.Option(
        50,
        "--tracks",
        "-t",
        min=1,
        max=200,
        help="Maximum tracks to fetch for this artist (up to 200).",
    ),
    auto_index: bool = typer.Option(
        True,
        "--auto-index/--no-auto-index",
        help="Automatically embed audio previews for newly fetched tracks.",
    ),
    discover_related: bool = typer.Option(
        False,
        "--discover-related/--no-discover-related",
        help="Discover related artists via Deezer and add as pending seeds.",
    ),
    related_limit: int = typer.Option(
        10,
        "--related-limit",
        min=1,
        max=50,
        help="Maximum related artists to discover when --discover-related is enabled.",
    ),
) -> None:
    """Fetch tracks for a specific artist, auto-index audio, and optionally discover related seeds."""

    async def run() -> None:
        async with Container() as container:
            assert container.fetch_artist_tracks is not None
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(f"Fetching '{artist}'", total=None)

                def on_progress(p: Any) -> None:
                    progress.update(
                        task,
                        total=p.total or None,
                        completed=p.processed,
                        description=f"[cyan]{p.stage}[/] - {p.message}",
                    )

                result = await container.fetch_artist_tracks.execute(
                    artist,
                    tracks_limit=tracks,
                    auto_index=auto_index,
                    discover_related=discover_related,
                    related_limit=related_limit,
                    progress=on_progress,
                )
                progress.update(task, completed=result.tracks_saved)

            table = Table(title=f"Fetch Artist: {result.artist}")
            table.add_column("Metric")
            table.add_column("Value", justify="right")
            table.add_row("Artist", result.artist)
            table.add_row("Tracks found", str(result.tracks_found))
            table.add_row("Tracks saved", str(result.tracks_saved))
            table.add_row("Tracks indexed", str(result.tracks_indexed))
            table.add_row("Related seeds discovered", str(result.related_seeds_found))
            console.print(table)

    _run(run())


@app.command("stats")
def stats() -> None:
    """Print seed, track, and catalog analytics."""

    async def run() -> None:
        async with Container() as container:
            assert container.seed_repository is not None
            assert container.track_repository is not None
            pending = await container.seed_repository.count_by_status("pending")
            fetched = await container.seed_repository.count_by_status("fetched")
            failed = await container.seed_repository.count_by_status("failed")
            total_seeds = await container.seed_repository.count()
            electronic = await container.seed_repository.count_by_category("electronic")
            general = await container.seed_repository.count_by_category("general")
            analytics = await container.track_repository.get_catalog_analytics()

            table = Table(title="DigDeeper Local stats")
            table.add_column("Metric")
            table.add_column("Value", justify="right")
            table.add_row("Seeds total", str(total_seeds))
            table.add_row("Seeds pending", str(pending))
            table.add_row("Seeds fetched", str(fetched))
            table.add_row("Seeds failed", str(failed))
            table.add_row("Seeds electronic", str(electronic))
            table.add_row("Seeds general", str(general))
            table.add_row("Tracks total", str(analytics.total_tracks))
            table.add_row("Tracks embedded", str(analytics.total_embedded))
            table.add_row("Total artists", str(analytics.total_artists))
            table.add_row("Local tracks", str(analytics.total_local))
            table.add_row("iTunes tracks", str(analytics.total_itunes))
            console.print(table)

            if analytics.genres:
                genre_table = Table(title="Top Genres")
                genre_table.add_column("Genre")
                genre_table.add_column("Tracks", justify="right")
                genre_table.add_column("Embedded", justify="right")
                for g in analytics.genres[:8]:
                    genre_table.add_row(
                        g.genre, str(g.track_count), str(g.embedded_count)
                    )
                console.print(genre_table)

    _run(run())


@app.command("delete-track")
def delete_track(
    track_id: str = typer.Argument(..., help="Track id to delete from the catalog."),
    blacklist: bool = typer.Option(
        False,
        "--blacklist/--no-blacklist",
        help="Also add to blacklist to prevent re-import.",
    ),
    reason: str | None = typer.Option(
        None, "--reason", help="Optional blacklist reason."
    ),
) -> None:
    """Delete a track from the catalog, optionally blacklisting it.

    Never deletes user audio files on disk (only DB rows).
    """

    async def run() -> None:
        async with Container() as container:
            assert container.manage_catalog is not None
            res = await container.manage_catalog.delete_track(
                track_id, blacklist=blacklist, reason=reason
            )
            if not res.deleted:
                console.print(
                    f"[yellow]Track {track_id!r} not found or already deleted.[/]"
                )
                return
            msg = f"[green]Deleted track {track_id}[/]"
            if res.blacklisted:
                msg += " [cyan](blacklisted)[/]"
            console.print(msg)

    _run(run())


@app.command("delete-artist")
def delete_artist(
    artist_name: str = typer.Argument(
        ..., help="Artist name to delete from the catalog."
    ),
    blacklist: bool = typer.Option(
        False,
        "--blacklist/--no-blacklist",
        help="Also add to blacklist to prevent re-crawling.",
    ),
    reason: str | None = typer.Option(
        None, "--reason", help="Optional blacklist reason."
    ),
) -> None:
    """Delete an artist, all their tracks, and their seeds from the catalog.

    Never deletes user audio files on disk (only DB rows).
    """

    async def run() -> None:
        async with Container() as container:
            assert container.manage_catalog is not None
            res = await container.manage_catalog.delete_artist(
                artist_name, blacklist=blacklist, reason=reason
            )
            msg = (
                f"[green]Deleted artist {artist_name!r}: "
                f"{res.tracks_deleted} tracks removed, seed removed: {res.seed_removed}[/]"
            )
            if res.blacklisted:
                msg += " [cyan](blacklisted)[/]"
            console.print(msg)

    _run(run())


@app.command("blacklist-list")
def blacklist_list(
    kind: str | None = typer.Option(
        None, "--kind", help="Filter by kind: 'artist' or 'track'."
    ),
    query: str | None = typer.Option(
        None, "--query", "-q", help="Filter by search query."
    ),
    limit: int = typer.Option(50, "--limit", min=1, help="Max entries to list."),
) -> None:
    """List blacklisted artists and tracks."""

    async def run() -> None:
        async with Container() as container:
            assert container.manage_catalog is not None
            entries = await container.manage_catalog.list_blacklist(
                kind=kind, query=query, limit=limit
            )
            total = await container.manage_catalog.count_blacklist(kind=kind)

        if not entries:
            console.print("[yellow]No blacklist entries found.[/]")
            return

        table = Table(title=f"Blacklist ({total} total)")
        table.add_column("ID", justify="right")
        table.add_column("Kind")
        table.add_column("Display Name")
        table.add_column("Key", style="dim")
        table.add_column("Reason")
        table.add_column("Created", style="dim")
        for e in entries:
            table.add_row(
                str(e.id or "-"),
                e.kind,
                e.display_name,
                e.normalized_key,
                e.reason or "-",
                e.created_at or "-",
            )
        console.print(table)

    _run(run())


@app.command("blacklist-remove")
def blacklist_remove(
    entry_id: int = typer.Argument(..., help="Blacklist entry ID to remove."),
) -> None:
    """Remove an artist or track from the blacklist by ID."""

    async def run() -> None:
        async with Container() as container:
            assert container.manage_catalog is not None
            removed = await container.manage_catalog.remove_blacklist_entry(entry_id)
            if not removed:
                console.print(f"[red]Error:[/] Blacklist entry {entry_id} not found.")
                raise typer.Exit(1)
            console.print(f"[green]Removed blacklist entry {entry_id}.[/]")

    _run(run())


@app.command("serve")
def serve(
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Bind address (localhost by default; there is no authentication).",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        min=1,
        max=65535,
        help="HTTP port for the web UI.",
    ),
) -> None:
    """Launch the local Mission Control web UI (FastAPI + SSE)."""

    # Imported lazily: the CLI stays fast for users who never open the UI.
    import uvicorn

    from presentation.api import create_app

    console.print(
        f"[green]DigDeeper Local[/] -> [bold]http://{host}:{port}[/] (Ctrl+C to stop)"
    )
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


def _print_seed_result(result: Any) -> None:
    table = Table(title="Seed list")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Discovered", str(result.discovered))
    table.add_row("LLM generated", str(result.llm_generated))
    table.add_row("Rows written", str(result.written))
    table.add_row("Electronic total", str(result.electronic_total))
    table.add_row("General total", str(result.general_total))
    console.print(table)


def _run(coroutine: Coroutine[Any, Any, T]) -> T:
    try:
        return asyncio.run(coroutine)
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted[/]")
        raise typer.Exit(130) from None
    except Exception as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    main()
