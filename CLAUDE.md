# CLAUDE.md

## Project
`yt-batch` is a Python CLI for creating instrumental audio by removing vocals with Demucs.

## Stable workflow
1. Input: YouTube query/URL or local audio folder; optional `--album` for a whole playlist (batch `yt-dlp` + Demucs per track).
2. Processing: download/read audio, run Demucs (`--two-stems=vocals`).
3. Output: instrumental files in the output directory; album mode writes to a per-album subfolder under `--outdir`.

## Run
```bash
python3 yt-batch.py "Song Name"
python3 -m pytest -q
```

## Essentials
- Main script: `yt-batch.py`
- Typical flags: `-i` (input file), `-f` (folder), `-o` (output), `-m` (model), `-q` (quality)
- Requirements: Python 3.9+, `ffmpeg`, `yt-dlp`, `demucs` in `PATH`

## Gotchas
- YouTube returns HTTP 403 on roughly 40% of downloads: `android_vr` is the only player client that works without a PO token, and it is flaky. `yt-dlp`'s own `--retries` does not help — the whole process must be re-invoked to force fresh stream URLs. That is what `run_with_retries` does; keep new `yt-dlp` calls wrapped in it.
- Nothing may be written relative to the working directory. Demucs gets an explicit `-o` into a temp dir (`demucs_workdir`), and `yt-dlp` gets `yt_output_args(output_dir)`.
- Retry backoff is real time. Tests inject a fake via the `_sleep` seam (autouse fixture in `tests/conftest.py`); do not call `time.sleep` directly in new code.
