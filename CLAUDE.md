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
- Typical flags: `-f` (text file with a track list), `-i` (input folder), `-o` (output), `-m` (model), `-q` (quality)
- Requirements: Python 3.9+, `ffmpeg`, `yt-dlp`, `demucs` in `PATH`

## Gotchas
- YouTube returns HTTP 403 on roughly 40% of downloads: `android_vr` is the only player client that works without a PO token, and it is flaky. `yt-dlp`'s own `--retries` does not help — the whole process must be re-invoked to force fresh stream URLs. That is what `run_with_retries` does; keep new `yt-dlp` calls wrapped in it. `--cookies-from-browser chrome` moves `yt-dlp` onto the web client and makes 403 go away; without cookies expect retries.
- `yt-dlp` needs the EJS challenge solver to handle YouTube's JS signature/`n` challenges — without it YouTube serves images only or 403. `YT_COMMON_FLAGS` carries `--remote-components ejs:github` (fetches the solver from the yt-dlp repo); a JS runtime (`deno`/`node`) must be in `PATH`. Build every `yt-dlp` argv with `yt_dlp_base_cmd()` so the flags cannot be forgotten — the one deliberate exception is `count_playlist_entries`, where `--flat-playlist` needs no solver and a failed solver fetch would silently drop the `Pobrano X/Y` warning.
- `--cookies-from-browser` takes a value, so `--cookies-from-browser URL` silently eats the URL. `normalize_cookie_option` validates the value against `COOKIE_BROWSERS` and hands anything else back as a query.
- Nothing may be written relative to the working directory. Demucs gets an explicit `-o` into a temp dir (`demucs_workdir`), and `yt-dlp` gets `yt_output_args(output_dir)`.
- Retry backoff is real time. Tests inject a fake via the `_sleep` seam (autouse fixture in `tests/conftest.py`); do not call `time.sleep` directly in new code.
