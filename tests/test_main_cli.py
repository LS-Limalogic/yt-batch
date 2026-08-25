from pathlib import Path

import pytest


def test_main_exits_when_queue_empty(tmp_path, monkeypatch, yt_batch_module):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(yt_batch_module, "check_dependencies", lambda: None)
    monkeypatch.setattr(yt_batch_module, "check_python_runtime", lambda: None)
    monkeypatch.setattr(yt_batch_module, "get_demucs_device", lambda: None)
    monkeypatch.setattr(yt_batch_module.sys, "argv", ["yt-batch.py"])

    with pytest.raises(SystemExit) as exc:
        yt_batch_module.main()
    assert exc.value.code == 1
    assert not (tmp_path / "output").exists()


def test_main_reads_track_list_file_and_dispatches_process_item(tmp_path, monkeypatch, yt_batch_module):
    monkeypatch.chdir(tmp_path)
    input_file = tmp_path / "links.txt"
    input_file.write_text("track 1\nhttps://youtube.com/a\n", encoding="utf-8")
    calls = {"item": 0}

    monkeypatch.setattr(yt_batch_module, "check_dependencies", lambda: None)
    monkeypatch.setattr(yt_batch_module, "check_python_runtime", lambda: None)
    monkeypatch.setattr(yt_batch_module, "get_demucs_device", lambda: None)
    monkeypatch.setattr(
        yt_batch_module,
        "process_item",
        lambda *args, **kwargs: calls.__setitem__("item", calls["item"] + 1),
    )
    monkeypatch.setattr(yt_batch_module, "process_local_file", lambda *args, **kwargs: None)
    monkeypatch.setattr(yt_batch_module.sys, "argv", ["yt-batch.py", "-f", str(input_file)])

    yt_batch_module.main()
    assert calls["item"] == 2


def test_main_folder_flag_not_a_directory_exits(tmp_path, monkeypatch, yt_batch_module):
    monkeypatch.chdir(tmp_path)
    non_dir = tmp_path / "missing-folder"
    monkeypatch.setattr(yt_batch_module, "check_dependencies", lambda: None)
    monkeypatch.setattr(yt_batch_module, "check_python_runtime", lambda: None)
    monkeypatch.setattr(yt_batch_module.sys, "argv", ["yt-batch.py", "-i", str(non_dir)])

    with pytest.raises(SystemExit) as exc:
        yt_batch_module.main()
    assert exc.value.code == 1


def test_main_file_is_directory_exits(tmp_path, monkeypatch, capsys, yt_batch_module):
    monkeypatch.chdir(tmp_path)
    a_dir = tmp_path / "ASAP"
    a_dir.mkdir()
    monkeypatch.setattr(yt_batch_module, "check_dependencies", lambda: None)
    monkeypatch.setattr(yt_batch_module, "check_python_runtime", lambda: None)
    monkeypatch.setattr(yt_batch_module.sys, "argv", ["yt-batch.py", "-f", str(a_dir)])

    with pytest.raises(SystemExit) as exc:
        yt_batch_module.main()
    assert exc.value.code == 1
    # Komunikat musi kierować na -i/--folder, inaczej test przechodzi na samym
    # "pusta kolejka -> print_help()" i nie pilnuje już walidacji -f.
    assert "-i/--folder" in capsys.readouterr().out


def test_main_does_not_create_outdir_when_args_invalid(tmp_path, monkeypatch, yt_batch_module):
    monkeypatch.chdir(tmp_path)
    a_dir = tmp_path / "ASAP"
    a_dir.mkdir()
    monkeypatch.setattr(yt_batch_module, "check_dependencies", lambda: None)
    monkeypatch.setattr(yt_batch_module, "check_python_runtime", lambda: None)
    monkeypatch.setattr(yt_batch_module.sys, "argv", ["yt-batch.py", "-f", str(a_dir)])

    with pytest.raises(SystemExit):
        yt_batch_module.main()
    assert not (tmp_path / "output").exists()


def test_main_dispatches_local_and_remote_items(tmp_path, monkeypatch, yt_batch_module):
    monkeypatch.chdir(tmp_path)
    local = tmp_path / "local.mp3"
    local.write_text("x", encoding="utf-8")

    calls = {"local": 0, "remote": 0, "album": 0}
    monkeypatch.setattr(yt_batch_module, "check_dependencies", lambda: None)
    monkeypatch.setattr(yt_batch_module, "check_python_runtime", lambda: None)
    monkeypatch.setattr(yt_batch_module, "get_demucs_device", lambda: "mps")
    monkeypatch.setattr(
        yt_batch_module,
        "process_local_file",
        lambda *args, **kwargs: calls.__setitem__("local", calls["local"] + 1),
    )
    monkeypatch.setattr(
        yt_batch_module,
        "process_item",
        lambda *args, **kwargs: calls.__setitem__("remote", calls["remote"] + 1),
    )
    monkeypatch.setattr(
        yt_batch_module,
        "resolve_album_playlist_url",
        lambda *_args: (
            "https://music.youtube.com/playlist?list=from_album",
            "Test Album Dir",
        ),
    )
    monkeypatch.setattr(
        yt_batch_module,
        "process_album_playlist",
        lambda *_args, **kwargs: calls.__setitem__("album", calls["album"] + 1),
    )
    monkeypatch.setattr(
        yt_batch_module.sys,
        "argv",
        ["yt-batch.py", str(local), "query song", "-a", "album name"],
    )

    yt_batch_module.main()
    assert calls["local"] == 1
    assert calls["remote"] == 1
    assert calls["album"] == 1


def test_main_track_list_file_non_utf8_exits(tmp_path, monkeypatch, yt_batch_module):
    monkeypatch.chdir(tmp_path)
    input_file = tmp_path / "bad.txt"
    input_file.write_bytes(b"\xff\xfe\x00\x00")

    monkeypatch.setattr(yt_batch_module, "check_dependencies", lambda: None)
    monkeypatch.setattr(yt_batch_module, "check_python_runtime", lambda: None)
    monkeypatch.setattr(yt_batch_module.sys, "argv", ["yt-batch.py", "-f", str(input_file)])

    with pytest.raises(SystemExit) as exc:
        yt_batch_module.main()
    assert exc.value.code == 1


def test_main_exits_when_python_runtime_invalid(monkeypatch, yt_batch_module):
    monkeypatch.setattr(yt_batch_module, "check_dependencies", lambda: None)
    monkeypatch.setattr(yt_batch_module, "check_python_runtime", lambda: (_ for _ in ()).throw(SystemExit(1)))
    monkeypatch.setattr(yt_batch_module.sys, "argv", ["yt-batch.py", "query"])

    with pytest.raises(SystemExit) as exc:
        yt_batch_module.main()
    assert exc.value.code == 1


def test_main_stray_cookie_value_becomes_query(tmp_path, monkeypatch, capsys, yt_batch_module):
    """`--cookies-from-browser URL` połykał URL i program kończył bez roboty."""
    monkeypatch.chdir(tmp_path)
    url = "https://music.youtube.com/watch?v=Udfa-bZXQ5s"
    seen = []

    monkeypatch.setattr(yt_batch_module, "check_dependencies", lambda: None)
    monkeypatch.setattr(yt_batch_module, "check_python_runtime", lambda: None)
    monkeypatch.setattr(yt_batch_module, "get_demucs_device", lambda: None)
    monkeypatch.setattr(yt_batch_module, "process_local_file", lambda *a, **k: None)
    monkeypatch.setattr(
        yt_batch_module,
        "process_item",
        lambda item, _idx, _total, args, _out: seen.append(
            (item, args.cookies_from_browser)
        ),
    )
    monkeypatch.setattr(
        yt_batch_module.sys,
        "argv",
        ["yt-batch.py", "--cookies-from-browser", url],
    )

    yt_batch_module.main()
    assert seen == [(url, None)]
    assert "--cookies-from-browser" in capsys.readouterr().out


def test_main_keeps_valid_cookie_browser(tmp_path, monkeypatch, yt_batch_module):
    monkeypatch.chdir(tmp_path)
    seen = []
    monkeypatch.setattr(yt_batch_module, "check_dependencies", lambda: None)
    monkeypatch.setattr(yt_batch_module, "check_python_runtime", lambda: None)
    monkeypatch.setattr(yt_batch_module, "get_demucs_device", lambda: None)
    monkeypatch.setattr(yt_batch_module, "process_local_file", lambda *a, **k: None)
    monkeypatch.setattr(
        yt_batch_module,
        "process_item",
        lambda _item, _idx, _total, args, _out: seen.append(args.cookies_from_browser),
    )
    monkeypatch.setattr(
        yt_batch_module.sys,
        "argv",
        ["yt-batch.py", "--cookies-from-browser", "safari:Default", "some query"],
    )

    yt_batch_module.main()
    assert seen == ["safari:Default"]


def test_main_empty_queue_with_args_prints_hint_not_help(tmp_path, monkeypatch, capsys, yt_batch_module):
    monkeypatch.chdir(tmp_path)
    empty_list = tmp_path / "empty.txt"
    empty_list.write_text("\n", encoding="utf-8")
    monkeypatch.setattr(yt_batch_module, "check_dependencies", lambda: None)
    monkeypatch.setattr(yt_batch_module, "check_python_runtime", lambda: None)
    monkeypatch.setattr(yt_batch_module.sys, "argv", ["yt-batch.py", "-f", str(empty_list)])

    with pytest.raises(SystemExit) as exc:
        yt_batch_module.main()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "brak utworów" in out
    assert "usage:" not in out


def test_main_without_any_input_prints_help(tmp_path, monkeypatch, capsys, yt_batch_module):
    """Brak wejścia (fraza/-f/-i/-a) to nadal pełny help, także gdy podano samo --source."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(yt_batch_module, "check_dependencies", lambda: None)
    monkeypatch.setattr(yt_batch_module, "check_python_runtime", lambda: None)
    monkeypatch.setattr(yt_batch_module.sys, "argv", ["yt-batch.py", "--source", "yt"])

    with pytest.raises(SystemExit) as exc:
        yt_batch_module.main()
    assert exc.value.code == 1
    assert "usage:" in capsys.readouterr().out


def test_main_default_source_is_ytm(tmp_path, monkeypatch, yt_batch_module):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(yt_batch_module, "check_dependencies", lambda: None)
    monkeypatch.setattr(yt_batch_module, "check_python_runtime", lambda: None)
    monkeypatch.setattr(yt_batch_module, "get_demucs_device", lambda: None)
    monkeypatch.setattr(yt_batch_module, "process_local_file", lambda *args, **kwargs: None)
    seen_sources = []
    monkeypatch.setattr(
        yt_batch_module,
        "process_item",
        lambda _item, _idx, _total, args, _out: seen_sources.append(args.source),
    )
    monkeypatch.setattr(yt_batch_module.sys, "argv", ["yt-batch.py", "some query"])
    yt_batch_module.main()
    assert seen_sources == ["ytm"]
