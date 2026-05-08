"""Rekordbox XML export with playlists."""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from dj_dl import __version__


@dataclass
class RekordboxTrack:
    path: str
    title: str
    artist: str
    album: str = ""
    bpm: float = 0.0
    key: str = ""
    genre: str = ""
    duration: int = 0


def generate_xml(tracks: list[RekordboxTrack], playlist_name: str) -> str:
    root = Element("DJ_PLAYLISTS", {"Version": "1.0.0"})

    SubElement(root, "PRODUCT", {"Name": "djdl", "Version": __version__})

    collection = SubElement(root, "COLLECTION", {"Entries": str(len(tracks))})

    for idx, track in enumerate(tracks, 1):
        location = track.path
        if not location.startswith("file://"):
            location = "file://localhost" + location

        track_elem = SubElement(
            collection,
            "TRACK",
            {
                "TrackID": str(idx),
                "Name": html.escape(track.title),
                "Artist": html.escape(track.artist),
                "Album": html.escape(track.album),
                "Genre": html.escape(track.genre),
                "Location": location,
                "TotalTime": str(track.duration),
                "Kind": "MP4",
            },
        )
        if track.bpm > 0:
            track_elem.set("Tempo", f"{track.bpm:.2f}")
        if track.key:
            track_elem.set("Key", track.key)

    playlists = SubElement(root, "PLAYLISTS")
    root_node = SubElement(playlists, "NODE", {"Name": "djdl", "Type": "0", "KeyType": "0"})
    playlist_node = SubElement(
        root_node, "NODE", {"Name": html.escape(playlist_name), "Type": "0", "KeyType": "0"}
    )

    for idx in range(1, len(tracks) + 1):
        SubElement(playlist_node, "TRACK", {"Key": str(idx)})

    xml_bytes = tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_bytes}'


def generate_xml_file(
    output_dir: Path,
    tracks: list[RekordboxTrack],
    playlist_name: str,
    xml_path: Path | None = None,
) -> Path:
    if xml_path is None:
        xml_path = Path.home() / ".config" / "dj-dl" / "rekordbox.xml"

    xml_path.parent.mkdir(parents=True, exist_ok=True)
    xml_content = generate_xml(tracks, playlist_name)
    xml_path.write_text(xml_content, encoding="utf-8")
    return xml_path
