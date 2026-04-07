import json
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


def test_resolve_album_tracks_success(monkeypatch, yt_batch_module):
    captured_cmds = []
    responses = [
        json.dumps({"playlist_id": "PL123", "album": "My Album"}),
        "https://youtu.be/a\nhttps://youtu.be/b\n",
    ]

    def fake_run_command(_cmd, verbose=False):
        assert verbose is False
        captured_cmds.append(_cmd)
        return responses.pop(0)

    monkeypatch.setattr(yt_batch_module, "run_command", fake_run_command)
    urls = yt_batch_module.resolve_album_tracks("album", "yt")
    assert captured_cmds[0][-1].startswith("ytsearch1:")
    assert urls == ["https://youtu.be/a", "https://youtu.be/b"]


def test_resolve_album_tracks_without_playlist_returns_empty(monkeypatch, yt_batch_module):
    monkeypatch.setattr(yt_batch_module, "run_command", lambda _cmd: json.dumps({"album": "x"}))
    assert yt_batch_module.resolve_album_tracks("album", "yt") == []


def test_resolve_album_tracks_handles_command_error(monkeypatch, yt_batch_module):
    def boom(_cmd, verbose=False):
        raise RuntimeError("bad")

    monkeypatch.setattr(yt_batch_module, "run_command", boom)
    assert yt_batch_module.resolve_album_tracks("album", "yt") == []


def test_resolve_album_tracks_ytm_requires_music_url(monkeypatch, yt_batch_module, capsys):
    monkeypatch.setattr(yt_batch_module, "run_command", lambda *_args, **_kwargs: "should not run")
    assert yt_batch_module.resolve_album_tracks("album name", "ytm") == []
    assert "ytm nie obsługuje wyszukiwania tekstowego albumu" in capsys.readouterr().out


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
