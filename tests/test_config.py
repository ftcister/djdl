from pathlib import Path

from dj_dl.config import Config, load_config


def test_load_config_defaults():
    config = Config()
    assert config.output_dir == Path.home() / "Music" / "DJ"
    assert config.audio_format == "m4a"
    assert config.audio_quality == 0


def test_load_config_from_yaml(tmp_path):
    yaml_content = (
        'output_dir: /custom/path\nspotify:\n  client_id: "abc123"\n  client_secret: "secret456"\n'
    )
    temp_file = tmp_path / "config.yaml"
    temp_file.write_text(yaml_content)

    config = load_config(temp_file)
    assert config.output_dir == Path("/custom/path")
    assert config.spotify.client_id == "abc123"
