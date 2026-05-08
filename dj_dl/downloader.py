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
from dj_dl.providers.base import BaseProvider, ProviderResult, Track
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

        await asyncio.gather(*[_process_job(j) for j in jobs])

        report.duration_seconds = time.monotonic() - start

        if report.files:
            rb_tracks = []
            for f in report.files:
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
        if self._file_already_exists(job):
            job.status = JobStatus.skipped
            return

        job.status = JobStatus.downloading

        async def _progress(track: Track, pct: float) -> None:
            job.progress = pct
            if progress_callback:
                await progress_callback(job)

        try:
            downloaded_path = await provider.download(job.track, job.output_dir, _progress)
            job.filepath = downloaded_path
        except Exception as e:
            job.status = JobStatus.failed
            job.error = str(e)
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

    def _organize_path(self, track: Track, result: ProviderResult) -> Path:
        return self.config.output_dir

    def _file_already_exists(self, job: DownloadJob) -> bool:
        if not job.output_dir.exists():
            return False
        search_name = f"{job.track.title} - {job.track.artist}"
        for ext in (".m4a", ".mp3", ".flac"):
            for f in job.output_dir.glob(f"*{ext}"):
                stem = f.stem
                if stem == search_name or stem.startswith(search_name + " ("):
                    return True
        return False
