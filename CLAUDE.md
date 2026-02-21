# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YouTube audio stem extractor — a Python CLI tool that downloads audio from YouTube (via yt-dlp), removes vocals using Demucs neural network models, and outputs instrumental MP3 files.

## Architecture

Single-file Python CLI (`yt-batch.py`) with this pipeline per track:
1. **Search/resolve** — yt-dlp resolves query or URL to filename
2. **Download** — yt-dlp extracts audio as MP3
3. **Separate** — Demucs splits vocals/instrumentals using `--two-stems=vocals`
4. **Cleanup** — moves result to `output/no-vocals-<name>.mp3`, removes temp files

Demucs outputs to `separated/<model>/<track>/no_vocals.mp3`. The script handles this path automatically.

## Commands

```bash
# Run directly
python3 yt-batch.py "Song Name"
python3 yt-batch.py -i links.txt -m 2 -q 320

# Run via Docker
docker-compose run audio-extractor "Song Name"
docker-compose run audio-extractor -i links.txt

# Build Docker image
docker-compose build
```

## Key flags

- `-m 1-4` — model selection (1=htdemucs default, 2=htdemucs_ft, 3=mdx_extra_q, 4=mdx_extra)
- `-q` — output bitrate in kbps (default 192)
- `-s 1-5` — demucs shifts/passes (higher = better quality, slower)
- `-k` — keep original downloaded file
- `-i` — input text file with queries/URLs (one per line)
- `-f` — folder with local audio files (mp3, opus, m4a, wav, flac, etc.)
- `-o` — output directory (default `./output`)

## Docker setup

- `docker-compose.yml` mounts `./output`, `./yt-batch.py`, and `./demucs_models` (model cache) into the container
- NVIDIA GPU passthrough is configured in deploy section
- Model cache persists in `./demucs_models` mapped to `/root/.cache/torch`

## Dependencies

System: `ffmpeg`, `yt-dlp`, `demucs` (all must be in PATH for local runs). Python 3.9+.
