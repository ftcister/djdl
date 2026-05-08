from dj_dl.rekordbox_xml import RekordboxTrack, generate_xml


def test_generate_xml_with_tracks():
    tracks = [
        RekordboxTrack(
            path="/Users/dj/Music/House/track1.m4a",
            title="Track One",
            artist="Artist A",
            album="Album X",
            bpm=128.0,
            key="8A",
            genre="House",
        ),
    ]
    xml = generate_xml(tracks, playlist_name="djdl - Spotify")
    assert "<DJ_PLAYLISTS" in xml
    assert "Track One" in xml
    assert 'Tempo="128.00"' in xml
    assert 'Key="8A"' in xml


def test_generate_xml_with_multiple_playlists():
    tracks = [
        RekordboxTrack(path="/tmp/t1.m4a", title="T1", artist="A1"),
        RekordboxTrack(path="/tmp/t2.m4a", title="T2", artist="A2"),
    ]
    xml = generate_xml(tracks, playlist_name="Test")
    assert xml.count("<TRACK TrackID=") == 2
    assert xml.count('<TRACK Key="') == 2
