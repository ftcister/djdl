"""Download manager with concurrency and file organization."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from dj_dl.analyzer import analyze_track, is_analyzed
from dj_dl.config import Config
from dj_dl.metadata import embed_metadata
from dj_dl.providers.base import BaseProvider, ProviderResult, Track, filename_stem
from dj_dl.rekordbox_xml import RekordboxTrack, generate_xml_file

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    pending = "pending"
    downloading = "downloading"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


@dataclass
class DownloadJob:
    track: Track
    output_dir: Path
    status: JobStatus = JobStatus.pending
    filepath: Path | None = None
    error: str | None = None
    progress: float = 0.0


@dataclass
class DownloadReport:
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    files: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class DownloadManager:
    """Orchestrates track downloads with concurrency."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self.semaphore = asyncio.Semaphore(self.config.concurrent_downloads)

    async def download(
        self,
        result: ProviderResult,
        provider: BaseProvider,
        progress_callback: Callable | None = None,
    ) -> DownloadReport:
        report = DownloadReport(total=len(result.tracks))
        jobs = [
            DownloadJob(track=t, output_dir=self._organize_path(t, result)) for t in result.tracks
        ]

        start = time.monotonic()

        async def _process_job(job: DownloadJob) -> None:
            async with self.semaphore:
                await self._process_single(job, provider, progress_callback)

        # A playlist can list the same track more than once. Copies running at the same time
        # would all pass _existing_file before any of them writes the file, so only the
        # first track under each filename is downloaded.
        unique_jobs: list[DownloadJob] = []
        filename_stems: set[str] = set()
        for job in jobs:
            stem = filename_stem(job.track)
            if stem in filename_stems:
                job.status = JobStatus.skipped
            else:
                filename_stems.add(stem)
                unique_jobs.append(job)

        await asyncio.gather(*[_process_job(j) for j in unique_jobs])

        # Downloads can fail transiently: YouTube sometimes answers HTTP 403 and serves the same
        # track a minute later. Each failed track gets one more attempt after the rest of the
        # batch, so the report is tallied only once both passes are done.
        retries = [j for j in unique_jobs if j.status == JobStatus.failed]
        await asyncio.gather(*[_process_job(j) for j in retries])

        for job in jobs:
            if job.status == JobStatus.completed:
                report.completed += 1
                if job.filepath:
                    report.files.append(job.filepath)
            elif job.status == JobStatus.failed:
                report.failed += 1
                if job.error:
                    report.errors.append(job.error)
            elif job.status == JobStatus.skipped:
                report.skipped += 1

        report.duration_seconds = time.monotonic() - start

        # Tracks skipped because an earlier run downloaded them are exported too, so a rerun
        # that fetches only the tracks that failed still exports the whole playlist.
        playlist_files = [job.filepath for job in jobs if job.filepath]
        if playlist_files:
            rb_tracks = []
            for f in playlist_files:
                try:
                    from mutagen.mp4 import MP4

                    audio = MP4(str(f))
                    rb_tracks.append(
                        RekordboxTrack(
                            path=str(f.resolve()),
                            title=audio.get("\xa9nam", [f.stem])[0],
                            artist=audio.get("\xa9ART", [""])[0],
                            album=audio.get("\xa9alb", [""])[0],
                            genre=audio.get("\xa9gen", [""])[0],
                        )
                    )
                except Exception:
                    rb_tracks.append(RekordboxTrack(path=str(f.resolve()), title=f.stem, artist=""))
            playlist_label = result.playlist_name or f"{provider.name} - Download"
            folder_name = self.config.output_dir.name or "djdl"
            xml_path = self.config.output_dir / f"{folder_name}.xml"
            generate_xml_file(self.config.output_dir, rb_tracks, playlist_label, xml_path)

        return report

    async def _process_single(
        self,
        job: DownloadJob,
        provider: BaseProvider,
        progress_callback: Callable | None = None,
    ) -> None:
        existing = self._existing_file(job)
        if existing:
            job.filepath = existing
            job.status = JobStatus.skipped
            return

        job.status = JobStatus.downloading

        async def _progress(track: Track, pct: float) -> None:
            job.progress = pct

        try:
            downloaded_path = await provider.download(job.track, job.output_dir, _progress)
            job.filepath = downloaded_path
        except Exception as e:
            job.status = JobStatus.failed
            job.error = f"{job.track.title} - {job.track.artist}: {e}"
            return

        job.status = JobStatus.processing

        try:
            await embed_metadata(downloaded_path, job.track)
        except Exception as e:
            logger.warning("Metadata embedding failed for %s: %s", downloaded_path, e)

        if self.config.auto_analyze and job.filepath and not is_analyzed(job.filepath):
            try:
                analyze_track(job.filepath)
            except Exception as e:
                logger.warning("Analysis failed for %s: %s", job.filepath, e)

        job.status = JobStatus.completed

        if progress_callback:
            await progress_callback(job)

    def _organize_path(self, track: Track, result: ProviderResult) -> Path:
        return self.config.output_dir

    def _existing_file(self, job: DownloadJob) -> Path | None:
        if not job.output_dir.exists():
            return None
        search_name = filename_stem(job.track)
        for ext in (".m4a", ".mp3", ".flac"):
            for f in job.output_dir.glob(f"*{ext}"):
                stem = f.stem
                if stem == search_name or stem.startswith(search_name + " ("):
                    return f
        return None
