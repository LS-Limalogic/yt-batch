# CLAUDE.md

## Project
`yt-batch` is a Python CLI for creating instrumental audio by removing vocals with Demucs.

## Stable workflow
1. Input: YouTube query/URL or local audio folder.
2. Processing: download/read audio, run Demucs (`--two-stems=vocals`).
3. Output: save instrumental file in output directory.

## Run
```bash
python3 yt-batch.py "Song Name"
python3 -m pytest -q
```

## Essentials
- Main script: `yt-batch.py`
- Typical flags: `-i` (input file), `-f` (folder), `-o` (output), `-m` (model), `-q` (quality)
- Requirements: Python 3.9+, `ffmpeg`, `yt-dlp`, `demucs` in `PATH`
