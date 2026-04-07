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
    source = tmp_path / "separated" / model / "song" / "no_vocals.mp3"
    source.parent.mkdir(parents=True)
    source.write_text("stem", encoding="utf-8")

    calls = {"run": 0, "move": 0, "rmtree": 0, "demucs": 0, "ffmpeg": 0}

    def fake_run_command(cmd, verbose=False):
        calls["run"] += 1
        if cmd[0] == "demucs":
            calls["demucs"] += 1
            assert verbose is True
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

    def fake_rmtree(path, ignore_errors):
        if path == "separated":
            calls["rmtree"] += 1

    monkeypatch.setattr(yt_batch_module, "run_command", fake_run_command)
    monkeypatch.setattr(yt_batch_module.shutil, "move", fake_move)
    monkeypatch.setattr(yt_batch_module.shutil, "rmtree", fake_rmtree)
    monkeypatch.setattr(yt_batch_module, "get_demucs_device", lambda: None)

    yt_batch_module.process_local_file(input_file, 1, 1, args, output_dir)
    assert calls == {"run": 2, "move": 1, "rmtree": 1, "demucs": 1, "ffmpeg": 1}
    assert (output_dir / "song-no-vocals.mp3").exists()


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
