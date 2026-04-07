from pathlib import Path


def test_process_item_metadata_failure_stops(tmp_path, args_factory, yt_batch_module, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    def fail_metadata(cmd, verbose=False):
        if "--get-filename" in cmd:
            raise RuntimeError("meta fail")
        return ""

    monkeypatch.setattr(yt_batch_module, "run_command", fail_metadata)
    yt_batch_module.process_item("query", 1, 1, args_factory(source="yt"), output_dir)
    assert "Nie udało się pobrać metadanych" in capsys.readouterr().out


def test_process_item_download_then_success_move(tmp_path, args_factory, yt_batch_module, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    args = args_factory(model="1", keep_original=False, source="yt")

    base_name = "song"
    input_mp3 = tmp_path / f"{base_name}.mp3"
    source_stem = tmp_path / "separated" / yt_batch_module.resolve_model("1") / base_name / "no_vocals.mp3"

    state = {"downloaded": False}

    def fake_run_command(cmd, verbose=False):
        if "--get-filename" in cmd:
            return f"{base_name}.mp3"
        if cmd[0] == "yt-dlp" and "-x" in cmd and "--get-filename" not in cmd:
            input_mp3.write_text("audio", encoding="utf-8")
            state["downloaded"] = True
            return ""
        if cmd[0] == "demucs":
            source_stem.parent.mkdir(parents=True, exist_ok=True)
            source_stem.write_text("stem", encoding="utf-8")
            return ""
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(yt_batch_module, "run_command", fake_run_command)
    monkeypatch.setattr(yt_batch_module, "get_demucs_device", lambda: None)
    monkeypatch.setattr(yt_batch_module.shutil, "rmtree", lambda *_args, **_kwargs: None)

    yt_batch_module.process_item("my song", 1, 1, args, output_dir)
    assert state["downloaded"] is True
    assert (output_dir / f"{base_name}-no-vocals.mp3").exists()
    assert not input_mp3.exists()


def test_process_item_ytm_uses_resolved_music_url(tmp_path, args_factory, yt_batch_module, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    args = args_factory(source="ytm")
    seen_sources = []

    def fake_run_command(cmd, verbose=False):
        if "--get-filename" in cmd:
            seen_sources.append(cmd[-1])
            raise RuntimeError("stop after source capture")
        return ""

    monkeypatch.setattr(yt_batch_module, "run_command", fake_run_command)
    monkeypatch.setattr(yt_batch_module, "resolve_ytmusic_url", lambda _q: "https://music.youtube.com/watch?v=abc")
    yt_batch_module.process_item("some track", 1, 1, args, output_dir)
    assert seen_sources == ["https://music.youtube.com/watch?v=abc"]


def test_process_item_ytm_rejects_non_music_url(tmp_path, args_factory, yt_batch_module, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    args = args_factory(source="ytm")

    def fake_run_command(cmd, verbose=False):
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(yt_batch_module, "run_command", fake_run_command)
    yt_batch_module.process_item("https://www.youtube.com/watch?v=abc", 1, 1, args, output_dir)
    out = capsys.readouterr().out
    assert "URL: https://www.youtube.com/watch?v=abc" in out
    assert "akceptuje tylko URL-e z music.youtube.com" in out


def test_process_item_ytm_accepts_music_url(tmp_path, args_factory, yt_batch_module, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    args = args_factory(source="ytm", keep_original=False)
    input_mp3 = tmp_path / "song.mp3"
    source_stem = tmp_path / "separated" / yt_batch_module.resolve_model("1") / "song" / "no_vocals.mp3"

    def fake_run_command(cmd, verbose=False):
        if "--get-filename" in cmd:
            return "song.mp3"
        if cmd[0] == "yt-dlp" and "-x" in cmd and "--get-filename" not in cmd:
            input_mp3.write_text("audio", encoding="utf-8")
            return ""
        if cmd[0] == "demucs":
            source_stem.parent.mkdir(parents=True, exist_ok=True)
            source_stem.write_text("stem", encoding="utf-8")
            return ""
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(yt_batch_module, "run_command", fake_run_command)
    monkeypatch.setattr(yt_batch_module, "get_demucs_device", lambda: None)
    monkeypatch.setattr(yt_batch_module.shutil, "rmtree", lambda *_args, **_kwargs: None)

    yt_batch_module.process_item("https://music.youtube.com/watch?v=abc", 1, 1, args, output_dir)
    assert (output_dir / "song-no-vocals.mp3").exists()


def test_process_item_demucs_error_deletes_input_when_not_keep(
    tmp_path, args_factory, yt_batch_module, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    args = args_factory(keep_original=False, source="yt")
    input_mp3 = tmp_path / "song.mp3"
    input_mp3.write_text("audio", encoding="utf-8")

    def fake_run_command(cmd, verbose=False):
        if "--get-filename" in cmd:
            return "song.mp3"
        if cmd[0] == "demucs":
            raise RuntimeError("boom")
        return ""

    monkeypatch.setattr(yt_batch_module, "run_command", fake_run_command)
    monkeypatch.setattr(yt_batch_module, "get_demucs_device", lambda: None)

    yt_batch_module.process_item("https://youtube.com/x", 1, 1, args, output_dir)
    assert "Demucs crashed" in capsys.readouterr().out
    assert not input_mp3.exists()
