import json
import signal
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

import pytest


def test_check_dependencies_exits_when_missing_tools(monkeypatch, yt_batch_module):
    missing = {"demucs", "ffmpeg"}
    monkeypatch.setattr(
        yt_batch_module.shutil, "which", lambda tool: None if tool in missing else "/usr/bin/tool"
    )

    with pytest.raises(SystemExit) as exc:
        yt_batch_module.check_dependencies()

    assert exc.value.code == 1


def test_check_dependencies_passes_when_all_tools_present(monkeypatch, yt_batch_module):
    monkeypatch.setattr(yt_batch_module.shutil, "which", lambda _tool: "/usr/bin/tool")
    yt_batch_module.check_dependencies()


def test_cleanup_handler_removes_separated_and_album_tmp(tmp_path, monkeypatch, yt_batch_module):
    tmp_root = tmp_path / "out"
    tmp_root.mkdir()
    album_tmp = tmp_root / ".yt-batch-album-tmp"
    album_tmp.mkdir()
    (album_tmp / "nested").mkdir()

    separated = tmp_path / "separated"
    separated.mkdir()

    monkeypatch.setattr(yt_batch_module, "_cleanup_sigint_outdir", tmp_root)
    monkeypatch.setattr(yt_batch_module.sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as exc:
        yt_batch_module.cleanup_handler(signal.SIGINT, None)

    assert exc.value.code == 1
    assert not album_tmp.exists()
    assert not separated.exists()


def test_check_python_runtime_passes(monkeypatch, yt_batch_module):
    class FakeHash:
        def hexdigest(self):
            return "ok"

    fake_hashlib = ModuleType("hashlib")
    fake_hashlib.blake2b = lambda _data: FakeHash()
    fake_hashlib.blake2s = lambda _data: FakeHash()

    monkeypatch.setitem(sys.modules, "numpy", ModuleType("numpy"))
    monkeypatch.setitem(sys.modules, "hashlib", fake_hashlib)
    yt_batch_module.check_python_runtime()


def test_check_python_runtime_exits_when_numpy_missing(monkeypatch, yt_batch_module):
    real_import = __import__

    class FakeHash:
        def hexdigest(self):
            return "ok"

    fake_hashlib = ModuleType("hashlib")
    fake_hashlib.blake2b = lambda _data: FakeHash()
    fake_hashlib.blake2s = lambda _data: FakeHash()
    monkeypatch.setitem(sys.modules, "hashlib", fake_hashlib)

    def fake_import(name, *args, **kwargs):
        if name == "numpy":
            raise ModuleNotFoundError("No module named 'numpy'")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "numpy", raising=False)
    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(SystemExit) as exc:
        yt_batch_module.check_python_runtime()
    assert exc.value.code == 1


def test_check_python_runtime_exits_when_blake_unavailable(monkeypatch, yt_batch_module):
    fake_hashlib = ModuleType("hashlib")
    fake_hashlib.blake2b = lambda _data: (_ for _ in ()).throw(ValueError("unsupported hash type blake2b"))
    fake_hashlib.blake2s = lambda _data: (_ for _ in ()).throw(ValueError("unsupported hash type blake2s"))

    monkeypatch.setitem(sys.modules, "numpy", ModuleType("numpy"))
    monkeypatch.setitem(sys.modules, "hashlib", fake_hashlib)

    with pytest.raises(SystemExit) as exc:
        yt_batch_module.check_python_runtime()
    assert exc.value.code == 1


def test_run_command_returns_stripped_stdout(monkeypatch, yt_batch_module):
    monkeypatch.setattr(
        yt_batch_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="  abc \n"),
    )
    out = yt_batch_module.run_command(["echo", "abc"])
    assert out == "abc"


def test_run_command_verbose_sets_streams(monkeypatch, yt_batch_module):
    captured = {}

    class FakeProcess:
        def __init__(self, lines, returncode=0):
            self.stdout = iter(lines)
            self.returncode = returncode

        def wait(self):
            return self.returncode

    def fake_popen(cmd, stdout, stderr, text, env):
        captured["cmd"] = cmd
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        captured["text"] = text
        captured["env"] = env
        return FakeProcess([])

    monkeypatch.setattr(yt_batch_module.subprocess, "Popen", fake_popen)
    out = yt_batch_module.run_command(["echo", 1], verbose=True)
    assert out == ""
    assert captured["cmd"] == ["echo", "1"]
    assert captured["stdout"] == yt_batch_module.subprocess.PIPE
    assert captured["stderr"] == yt_batch_module.subprocess.STDOUT
    assert captured["text"] is True
    assert captured["env"] is None


def test_run_command_verbose_formats_noisy_float_output(monkeypatch, yt_batch_module, capsys):
    class FakeProcess:
        def __init__(self):
            self.stdout = iter(
                [
                    "327.59999999999997/327.59999999999997 [00:41<00:00,  7.94seconds/s]\n",
                ]
            )
            self.returncode = 0

        def wait(self):
            return self.returncode

    monkeypatch.setattr(
        yt_batch_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: FakeProcess(),
    )

    yt_batch_module.run_command(["dummy"], verbose=True)
    output = capsys.readouterr().out
    assert "327.6/327.6" in output


def test_run_command_raises_runtime_error_for_stderr(monkeypatch, yt_batch_module):
    def fake_run(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "x", stderr="failure")

    monkeypatch.setattr(yt_batch_module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="Komenda nie powiodła się: failure"):
        yt_batch_module.run_command(["false"])


def test_copy_audio_metadata_uses_tmp_name_with_audio_suffix(monkeypatch, tmp_path, yt_batch_module):
    metadata_source = tmp_path / "src.mp3"
    audio_target = tmp_path / "out.mp3"
    metadata_source.write_text("meta", encoding="utf-8")
    audio_target.write_text("audio", encoding="utf-8")

    captured = {}

    def fake_run_command(cmd, verbose=False, env_overrides=None):
        captured["cmd"] = cmd
        temp_output = Path(cmd[-1])
        temp_output.write_text("tmp-audio", encoding="utf-8")
        return ""

    monkeypatch.setattr(yt_batch_module, "run_command", fake_run_command)

    ok = yt_batch_module.copy_audio_metadata(metadata_source, audio_target)

    assert ok is True
    assert captured["cmd"][-1].endswith(".tmp.mp3")
    assert audio_target.read_text(encoding="utf-8") == "tmp-audio"


def test_resolve_model_from_alias(yt_batch_module):
    assert yt_batch_module.resolve_model("2") == "htdemucs_ft"
    assert yt_batch_module.resolve_model("custom-model") == "custom-model"


def test_get_demucs_device_returns_mps(monkeypatch, yt_batch_module):
    class Backends:
        class mps:
            @staticmethod
            def is_available():
                return True

            @staticmethod
            def is_built():
                return True

    fake_torch = SimpleNamespace(backends=Backends())
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    assert yt_batch_module.get_demucs_device() == "mps"


def test_get_demucs_device_returns_none_when_unavailable(monkeypatch, yt_batch_module):
    class Backends:
        class mps:
            @staticmethod
            def is_available():
                return False

            @staticmethod
            def is_built():
                return True

    fake_torch = SimpleNamespace(backends=Backends())
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    assert yt_batch_module.get_demucs_device() is None


def test_resolve_album_playlist_url_yt_finds_playlist(monkeypatch, yt_batch_module):
    captured_cmds = []

    def fake_run_command(_cmd, verbose=False):
        assert verbose is False
        captured_cmds.append(_cmd)
        return json.dumps({"playlist_id": "PL123", "album": "My Album"})

    monkeypatch.setattr(yt_batch_module, "run_command", fake_run_command)
    url, subdir = yt_batch_module.resolve_album_playlist_url("album", "yt")
    assert captured_cmds[0][-1].startswith("ytsearch1:")
    assert url == "https://music.youtube.com/playlist?list=PL123"
    assert subdir == "My Album"


def test_resolve_album_playlist_url_without_playlist_returns_none(monkeypatch, yt_batch_module):
    monkeypatch.setattr(yt_batch_module, "run_command", lambda _cmd: json.dumps({"album": "x"}))
    assert yt_batch_module.resolve_album_playlist_url("album", "yt") is None


def test_resolve_album_playlist_url_handles_command_error(monkeypatch, yt_batch_module):
    def boom(_cmd, verbose=False):
        raise RuntimeError("bad")

    monkeypatch.setattr(yt_batch_module, "run_command", boom)
    assert yt_batch_module.resolve_album_playlist_url("album", "yt") is None


def test_resolve_album_playlist_url_ytm_requires_music_url(monkeypatch, yt_batch_module, capsys):
    monkeypatch.setattr(yt_batch_module, "run_command", lambda *_args, **_kwargs: "should not run")
    assert yt_batch_module.resolve_album_playlist_url("album name", "ytm") is None
    assert "ytm nie obsługuje wyszukiwania tekstowego albumu" in capsys.readouterr().out


def test_resolve_album_playlist_url_ytm_returns_url_and_subdir(monkeypatch, yt_batch_module):
    monkeypatch.setattr(
        yt_batch_module,
        "run_command",
        lambda _cmd: json.dumps({"title": "My Cool Album"}),
    )
    url = "https://music.youtube.com/playlist?list=OLAK5uy_abc"
    out_url, subdir = yt_batch_module.resolve_album_playlist_url(url, "ytm")
    assert out_url == url
    assert subdir == "My Cool Album"


def test_safe_album_subdir_name_sanitizes(yt_batch_module):
    assert yt_batch_module.safe_album_subdir_name('a/b:c', "fb") == "a_b_c"
    assert yt_batch_module.safe_album_subdir_name("", "fallback") == "fallback"


def test_playlist_folder_display_title_replaces_album_prefix_with_artist(yt_batch_module):
    meta = {"title": "Album - In Rainbows", "artist": "Radiohead"}
    assert yt_batch_module.playlist_folder_display_title(meta) == "Radiohead - In Rainbows"


def test_playlist_folder_display_title_artist_from_first_entry(yt_batch_module):
    meta = {"title": "Album - The Wall", "entries": [{"artist": "Pink Floyd"}]}
    assert yt_batch_module.playlist_folder_display_title(meta) == "Pink Floyd - The Wall"


def test_playlist_folder_display_title_without_artist_unchanged(yt_batch_module):
    meta = {"title": "Album - XYZ"}
    assert yt_batch_module.playlist_folder_display_title(meta) == "Album - XYZ"


def test_playlist_folder_display_title_non_album_pattern_unchanged(yt_batch_module):
    meta = {"title": "Greatest Hits", "artist": "Someone"}
    assert yt_batch_module.playlist_folder_display_title(meta) == "Greatest Hits"


def test_format_album_folder_name_appends_year_from_release_year(yt_batch_module):
    meta = {"title": "Some Album", "release_year": 2011}
    assert yt_batch_module.format_album_folder_name(meta) == "Some Album (2011)"


def test_format_album_folder_name_year_from_date_field(yt_batch_module):
    meta = {"title": "X", "date": "20070312"}
    assert yt_batch_module.format_album_folder_name(meta) == "X (2007)"


def test_format_album_folder_name_year_from_first_entry(yt_batch_module):
    meta = {
        "title": "Album - OK Computer",
        "artist": "Radiohead",
        "entries": [{"date": "19970516"}],
    }
    out = yt_batch_module.format_album_folder_name(meta)
    assert out == "Radiohead - OK Computer (1997)"


def test_yt_dlp_cookies_args_empty_when_unset(yt_batch_module):
    assert yt_batch_module.yt_dlp_cookies_args(None) == []
    assert yt_batch_module.yt_dlp_cookies_args("") == []
    assert yt_batch_module.yt_dlp_cookies_args("   ") == []


def test_yt_dlp_cookies_args_when_set(yt_batch_module):
    assert yt_batch_module.yt_dlp_cookies_args("chrome") == [
        "--cookies-from-browser",
        "chrome",
    ]
    assert yt_batch_module.yt_dlp_cookies_args("chrome:Default") == [
        "--cookies-from-browser",
        "chrome:Default",
    ]


def test_pick_release_year_empty_when_missing(yt_batch_module):
    assert yt_batch_module._pick_release_year_from_playlist_meta({}) == ""


def test_download_album_playlist_builds_expected_cmd(monkeypatch, yt_batch_module, tmp_path):
    captured = {}

    def fake_run_command(cmd, verbose=False, check=True, env_overrides=None):
        captured["cmd"] = cmd
        return ""

    monkeypatch.setattr(yt_batch_module, "run_command", fake_run_command)
    dest = tmp_path / "dl"
    yt_batch_module.download_album_playlist("https://music.youtube.com/playlist?list=X", dest)
    cmd = captured["cmd"]
    assert cmd[0] == "yt-dlp"
    assert "--ignore-errors" in cmd
    assert "--embed-thumbnail" in cmd
    assert "--embed-metadata" in cmd
    assert "--parse-metadata" in cmd
    assert yt_batch_module.YT_ALBUM_PARSE_METADATA in cmd
    assert str(dest / "%(playlist_index)02d_%(title)s.%(ext)s") in cmd
    assert cmd[-1] == "https://music.youtube.com/playlist?list=X"


def test_download_album_playlist_passes_cookies_to_yt_dlp(monkeypatch, yt_batch_module, tmp_path):
    captured = {}

    def fake_run_command(cmd, verbose=False, check=True, env_overrides=None):
        captured["cmd"] = cmd
        return ""

    monkeypatch.setattr(yt_batch_module, "run_command", fake_run_command)
    dest = tmp_path / "dl"
    yt_batch_module.download_album_playlist(
        "https://music.youtube.com/playlist?list=X",
        dest,
        cookies_from_browser="chrome",
    )
    cmd = captured["cmd"]
    i = cmd.index("--cookies-from-browser")
    assert cmd[i + 1] == "chrome"
    assert cmd.index("--ignore-errors") > i


def test_resolve_album_playlist_url_yt_inserts_cookies(monkeypatch, yt_batch_module):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return json.dumps({"playlist_id": "PL123", "album": "My Album"})

    monkeypatch.setattr(yt_batch_module, "run_command", fake_run)
    url, subdir = yt_batch_module.resolve_album_playlist_url(
        "album", "yt", cookies_from_browser="chrome"
    )
    assert url == "https://music.youtube.com/playlist?list=PL123"
    assert subdir
    assert "--cookies-from-browser" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--cookies-from-browser") + 1] == "chrome"


def test_resolve_ytmusic_url_prefers_song(monkeypatch, yt_batch_module):
    class FakeYTMusic:
        def search(self, query, filter, limit):
            assert query == "query"
            assert limit == 1
            if filter == "songs":
                return [{"videoId": "song123"}]
            return []

    fake_module = ModuleType("ytmusicapi")
    fake_module.YTMusic = FakeYTMusic
    monkeypatch.setitem(sys.modules, "ytmusicapi", fake_module)

    url = yt_batch_module.resolve_ytmusic_url("query")
    assert url == "https://music.youtube.com/watch?v=song123"


def test_resolve_ytmusic_url_fallbacks_to_video(monkeypatch, yt_batch_module):
    class FakeYTMusic:
        def search(self, query, filter, limit):
            assert query == "query"
            assert limit == 1
            if filter == "songs":
                return []
            if filter == "videos":
                return [{"videoId": "vid456"}]
            return []

    fake_module = ModuleType("ytmusicapi")
    fake_module.YTMusic = FakeYTMusic
    monkeypatch.setitem(sys.modules, "ytmusicapi", fake_module)

    url = yt_batch_module.resolve_ytmusic_url("query")
    assert url == "https://music.youtube.com/watch?v=vid456"


def test_resolve_ytmusic_url_returns_none_when_no_results(monkeypatch, yt_batch_module, capsys):
    class FakeYTMusic:
        def search(self, query, filter, limit):
            return []

    fake_module = ModuleType("ytmusicapi")
    fake_module.YTMusic = FakeYTMusic
    monkeypatch.setitem(sys.modules, "ytmusicapi", fake_module)

    assert yt_batch_module.resolve_ytmusic_url("query") is None
    assert "Nie znaleziono wyniku w YouTube Music" in capsys.readouterr().out


def test_resolve_ytmusic_url_returns_none_on_api_error(monkeypatch, yt_batch_module, capsys):
    class FakeYTMusic:
        def search(self, query, filter, limit):
            raise RuntimeError("api down")

    fake_module = ModuleType("ytmusicapi")
    fake_module.YTMusic = FakeYTMusic
    monkeypatch.setitem(sys.modules, "ytmusicapi", fake_module)

    assert yt_batch_module.resolve_ytmusic_url("query") is None
    assert "Błąd wyszukiwania YouTube Music" in capsys.readouterr().out
