from pathlib import Path


def test_process_local_file_missing_input(tmp_path, args_factory, yt_batch_module, capsys):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    missing = tmp_path / "missing.mp3"

    yt_batch_module.process_local_file(missing, 1, 1, args_factory(), output_dir)
    assert "Plik nie istnieje" in capsys.readouterr().out


def test_process_local_file_skips_existing_destination(tmp_path, args_factory, yt_batch_module, capsys):
    input_file = tmp_path / "song.mp3"
    input_file.write_text("x", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "song-no-vocals.mp3").write_text("done", encoding="utf-8")

    yt_batch_module.process_local_file(input_file, 1, 1, args_factory(), output_dir)
    assert "[SKIP]" in capsys.readouterr().out


def test_process_local_file_success_moves_output(
    tmp_path, args_factory, yt_batch_module, monkeypatch
):
    input_file = tmp_path / "song.mp3"
    input_file.write_text("x", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    args = args_factory(model="1", quality=192, shifts=1)

    monkeypatch.chdir(tmp_path)
    model = yt_batch_module.resolve_model(args.model)

    calls = {"run": 0, "move": 0, "demucs": 0, "ffmpeg": 0}
    seen = {}

    def fake_run_command(cmd, verbose=False, env_overrides=None):
        calls["run"] += 1
        if cmd[0] == "demucs":
            calls["demucs"] += 1
            assert verbose is True
            work_dir = Path(cmd[cmd.index("-o") + 1])
            seen["work_dir"] = work_dir
            source = work_dir / model / "song" / "no_vocals.mp3"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("stem", encoding="utf-8")
            return ""
        if cmd[0] == "ffmpeg":
            calls["ffmpeg"] += 1
            assert verbose is False
            return ""
        raise AssertionError(f"Unexpected command: {cmd}")

    def fake_move(src, dst):
        calls["move"] += 1
        Path(dst).write_text(Path(src).read_text(encoding="utf-8"), encoding="utf-8")
        Path(src).unlink()

    monkeypatch.setattr(yt_batch_module, "run_command", fake_run_command)
    monkeypatch.setattr(yt_batch_module.shutil, "move", fake_move)
    monkeypatch.setattr(yt_batch_module, "get_demucs_device", lambda: None)

    yt_batch_module.process_local_file(input_file, 1, 1, args, output_dir)
    assert calls == {"run": 2, "move": 1, "demucs": 1, "ffmpeg": 1}
    assert (output_dir / "song-no-vocals.mp3").exists()
    # Demucs pisze do katalogu tymczasowego, nie do ./separated w cwd
    assert not (tmp_path / "separated").exists()
    assert not seen["work_dir"].exists()


def test_process_local_file_cleans_workdir_after_demucs_crash(
    tmp_path, args_factory, yt_batch_module, monkeypatch
):
    input_file = tmp_path / "song.mp3"
    input_file.write_text("x", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.chdir(tmp_path)

    seen = {}

    def fake_run_command(cmd, verbose=False, env_overrides=None):
        seen["work_dir"] = Path(cmd[cmd.index("-o") + 1])
        raise RuntimeError("boom")

    monkeypatch.setattr(yt_batch_module, "run_command", fake_run_command)
    monkeypatch.setattr(yt_batch_module, "get_demucs_device", lambda: None)

    yt_batch_module.process_local_file(input_file, 1, 1, args_factory(), output_dir)
    assert not seen["work_dir"].exists()
    assert yt_batch_module._active_demucs_dirs == set()


def test_process_local_file_demucs_error_returns(tmp_path, args_factory, yt_batch_module, monkeypatch, capsys):
    input_file = tmp_path / "song.mp3"
    input_file.write_text("x", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    def boom(*_args, **_kwargs):
        raise RuntimeError("demucs failed")

    monkeypatch.setattr(yt_batch_module, "run_command", boom)
    monkeypatch.setattr(yt_batch_module, "get_demucs_device", lambda: None)
    yt_batch_module.process_local_file(input_file, 1, 1, args_factory(), output_dir)
    assert "Demucs crashed" in capsys.readouterr().out
