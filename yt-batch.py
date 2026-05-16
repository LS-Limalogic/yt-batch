#!/usr/bin/env python3
import sys
import subprocess
import shutil
import argparse
import signal
import json
import os
import re
import hashlib
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# --- KONFIGURACJA GLOBALNA ---
REQUIRED_TOOLS = ["yt-dlp", "demucs", "ffmpeg"]

# Obsługiwane rozszerzenia przy wejściu z folderu (Demucs używa ffmpeg)
AUDIO_EXTENSIONS = {".mp3", ".opus", ".m4a", ".m4b", ".wav", ".flac", ".ogg", ".aac", ".wma"}

# Mapowanie modeli (Aliasy)
MODEL_MAP = {
    "1": "htdemucs",        # Standard
    "2": "htdemucs_ft",     # High Quality
    "3": "mdx_extra_q",     # MDX Quantized
    "4": "mdx_extra"        # MDX Full
}

SOURCE_MAP = {
    "ytm": None,
    "yt":  "ytsearch1",        # YouTube
}

# Wspólne flagi dla yt-dlp (DRY)
YT_COMMON_FLAGS = [
    "-o", "%(title)s.%(ext)s",
    "--restrict-filenames",
    "--no-mtime"  # Ważne: nie zmieniaj czasu modyfikacji pliku na czas uploadu filmu
]

# Pojedyncze pobranie całej playlisty (album): numeracja i osadzanie metadanych
YT_ALBUM_PARSE_METADATA = "playlist_index:%(track_number)s"


def yt_dlp_cookies_args(cookies_from_browser):
    """Fragment argv dla yt-dlp --cookies-from-browser (np. chrome, firefox:Profil)."""
    if cookies_from_browser is None:
        return []
    s = str(cookies_from_browser).strip()
    if not s:
        return []
    return ["--cookies-from-browser", s]


# Ustawiane w main() przed pętlą przetwarzania — SIGINT usuwa też tymczasowe pobrania albumów.
_cleanup_sigint_outdir = None


def cleanup_handler(signum, frame):
    """Obsługa przerwania Ctrl+C."""
    global _cleanup_sigint_outdir
    print("\n\n!!! Przerwano przez użytkownika (SIGINT). Sprzątam i zamykam...")
    shutil.rmtree("separated", ignore_errors=True)
    if _cleanup_sigint_outdir is not None:
        album_tmp = _cleanup_sigint_outdir / ".yt-batch-album-tmp"
        shutil.rmtree(album_tmp, ignore_errors=True)
    sys.exit(1)

# Rejestracja sygnału
signal.signal(signal.SIGINT, cleanup_handler)

def check_dependencies():
    """Fail fast: sprawdza czy narzędzia są w systemie."""
    missing = []
    for tool in REQUIRED_TOOLS:
        if not shutil.which(tool):
            missing.append(tool)
    
    if missing:
        print(f"BŁĄD KRYTYCZNY: Brak wymaganych narzędzi w PATH: {', '.join(missing)}")
        print("Zainstaluj je (np. apt install ffmpeg / pip install demucs) i spróbuj ponownie.")
        sys.exit(1)


def check_python_runtime():
    """Fail fast: sprawdza podstawowe wymagania runtime Pythona."""
    runtime_errors = []

    try:
        import numpy  # noqa: F401
    except Exception:
        runtime_errors.append("Brak pakietu Python: numpy")

    try:
        import hashlib
        hashlib.blake2b(b"yt-batch-runtime-check").hexdigest()
        hashlib.blake2s(b"yt-batch-runtime-check").hexdigest()
    except Exception as e:
        runtime_errors.append(f"Hashlib/BLAKE2 niedostępne: {e}")

    if runtime_errors:
        print("BŁĄD KRYTYCZNY: Uszkodzone lub niekompletne środowisko Python.")
        for error in runtime_errors:
            print(f"- {error}")
        print("\nSzybka naprawa:")
        print("1) Przeinstaluj Python (pyenv), np. pyenv uninstall 3.13.0 && pyenv install 3.13.0")
        print("2) Doinstaluj zależności: python3 -m pip install --upgrade pip numpy")
        print("3) Sprawdź: python3 -c \"import hashlib, numpy; hashlib.blake2b(b'x')\"")
        sys.exit(1)

FLOAT_NOISE_RE = re.compile(r"(?<![\w.])(\d+\.\d{3,})(?![\w.])")


def format_noisy_floats(text):
    """Ucina długie rozwinięcia floatów (np. 17.549999999999997 -> 17.5)."""
    if not text:
        return text

    def _round(match):
        return f"{float(match.group(1)):.1f}"

    return FLOAT_NOISE_RE.sub(_round, text)


def run_command(cmd, verbose=False, env_overrides=None, check=True):
    """Wrapper na subprocess z lepszą obsługą błędów."""
    try:
        # Konwersja wszystkich elementów komendy na stringi (bezpieczeństwo typów)
        cmd_str = [str(c) for c in cmd]

        env = None
        if env_overrides:
            env = os.environ.copy()
            env.update(env_overrides)

        if verbose:
            process = subprocess.Popen(
                cmd_str,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env
            )
            full_output = []
            for line in process.stdout:
                clean_line = format_noisy_floats(line.rstrip("\n"))
                full_output.append(clean_line)
                print(clean_line)
            return_code = process.wait()
            if return_code != 0:
                joined_output = "\n".join(full_output)
                if check:
                    raise subprocess.CalledProcessError(
                        return_code, cmd_str, stderr=joined_output
                    )
                print(
                    f"[WARN] Komenda zakończona kodem {return_code} "
                    "(powyżej mogą być pominięte pozycje playlisty / błędy pobrania)."
                )
            return ""

        result = subprocess.run(
            cmd_str,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        return result.stdout.strip() if result.stdout else ""
    except subprocess.CalledProcessError as e:
        if not verbose and e.stderr:
            # Zwracamy stderr, żeby wyższa warstwa mogła go zalogować
            error_msg = e.stderr.decode('utf-8', errors='replace').strip() if isinstance(e.stderr, bytes) else e.stderr.strip()
            raise RuntimeError(f"Komenda nie powiodła się: {format_noisy_floats(error_msg)}")
        raise e

def copy_audio_metadata(metadata_source, audio_target):
    """
    Kopiuje metadane z pliku źródłowego do istniejącego pliku MP3.
    Audio pochodzi z audio_target, tagi z metadata_source.
    """
    metadata_source = Path(metadata_source)
    audio_target = Path(audio_target)
    # FFmpeg rozpoznaje format po ostatnim rozszerzeniu, więc ".mp3.tmp" powoduje błąd muxera.
    # Utrzymujemy końcowe rozszerzenie ".mp3", dodając znacznik tymczasowy przed suffixem.
    temp_output = audio_target.with_name(f"{audio_target.stem}.tmp{audio_target.suffix}")

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-i", str(audio_target),
        "-i", str(metadata_source),
        "-map", "0:a",
        "-map_metadata", "1",
        "-c", "copy",
        str(temp_output)
    ]

    try:
        run_command(ffmpeg_cmd, verbose=False)
        temp_output.replace(audio_target)
        return True
    except Exception as e:
        if temp_output.exists():
            temp_output.unlink()
        print(f"[WARN] Nie udało się skopiować metadanych do {audio_target.name}: {format_noisy_floats(str(e))}")
        return False

def resolve_model(model_arg):
    return MODEL_MAP.get(str(model_arg), model_arg)


def get_demucs_device():
    """Zwraca 'mps' na Apple Silicon gdy dostępne, None = domyślny (cuda/cpu)."""
    try:
        import torch
        if torch.backends.mps.is_available() and torch.backends.mps.is_built():
            return "mps"
    except Exception:
        pass
    return None


def resolve_ytmusic_url(query):
    """Resolve text query to a direct music.youtube.com track URL."""
    try:
        from ytmusicapi import YTMusic
    except Exception:
        print("[ERROR] Brak zależności: ytmusicapi.")
        print("Zainstaluj: python3 -m pip install ytmusicapi")
        return None

    try:
        ytm = YTMusic()
        songs = ytm.search(query, filter="songs", limit=1)
        if songs and songs[0].get("videoId"):
            return f"https://music.youtube.com/watch?v={songs[0]['videoId']}"

        videos = ytm.search(query, filter="videos", limit=1)
        if videos and videos[0].get("videoId"):
            return f"https://music.youtube.com/watch?v={videos[0]['videoId']}"

        print(f"[ERROR] Nie znaleziono wyniku w YouTube Music dla: {query}")
        return None
    except Exception as e:
        print(f"[ERROR] Błąd wyszukiwania YouTube Music: {format_noisy_floats(str(e))}")
        return None


def safe_album_subdir_name(raw_title, fallback="album"):
    """Bezpieczna nazwa podkatalogu dla tytułu albumu/playlisty."""
    if not raw_title or not str(raw_title).strip():
        base = fallback
    else:
        base = str(raw_title).strip()
    for c in '<>:"/\\|?*\x00':
        base = base.replace(c, "_")
    base = re.sub(r"\s+", " ", base)
    base = base.strip(" .")
    if not base:
        base = fallback
    if len(base) > 180:
        base = base[:180].rstrip(" .")
    return base


def _fallback_title_from_playlist_url(url):
    try:
        lst = parse_qs(urlparse(url).query).get("list")
        if lst and lst[0]:
            return lst[0][:48]
    except Exception:
        pass
    return "album"


def _pick_artist_from_playlist_meta(meta):
    """Artysta z metadanych playlisty (-J) lub z pierwszego wpisu."""
    if not meta:
        return ""
    for key in ("artist", "album_artist"):
        v = meta.get(key)
        if v and str(v).strip():
            return str(v).strip()
    entries = meta.get("entries") or []
    if entries and isinstance(entries[0], dict):
        e0 = entries[0]
        for key in ("artist", "album_artist"):
            v = e0.get(key)
            if v and str(v).strip():
                return str(v).strip()
    for key in ("uploader", "creator", "channel"):
        v = meta.get(key)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def playlist_folder_display_title(meta):
    """
    Tytuł katalogu dla playlisty/albumu.
    YT Music często zwraca 'Album - Nazwa' — jeśli znany jest artysta, robi 'Artysta - Nazwa'.
    """
    if not meta:
        return ""
    raw = (
        meta.get("title")
        or meta.get("playlist_title")
        or meta.get("album")
        or ""
    )
    raw = str(raw).strip()
    if not raw:
        return ""
    artist = _pick_artist_from_playlist_meta(meta)
    if artist:
        m = re.match(r"(?i)^Album\s*-\s*(.+)$", raw)
        if m:
            return f"{artist} - {m.group(1).strip()}"
    return raw


def _year_from_date_field(value):
    """Wyciąga RRRR z YYYYMMDD, YYYY-MM-DD lub samego roku."""
    if value is None:
        return ""
    s = str(value).strip()
    if len(s) >= 4 and s[:4].isdigit():
        try:
            y = int(s[:4])
            if 1900 <= y <= 2100:
                return s[:4]
        except ValueError:
            pass
    return ""


def _pick_release_year_from_playlist_meta(meta):
    """Rok wydania z metadanych playlisty / pierwszego utworu (yt-dlp)."""
    if not meta:
        return ""

    def from_entry(entry):
        if not isinstance(entry, dict):
            return ""
        for key in ("release_year", "year"):
            v = entry.get(key)
            if v is not None and str(v).strip().isdigit() and len(str(v).strip()) == 4:
                y = int(str(v).strip())
                if 1900 <= y <= 2100:
                    return str(y)
        for key in ("date", "release_date", "upload_date"):
            y = _year_from_date_field(entry.get(key))
            if y:
                return y
        return ""

    for key in ("release_year", "year"):
        v = meta.get(key)
        if v is not None and str(v).strip().isdigit() and len(str(v).strip()) == 4:
            y = int(str(v).strip())
            if 1900 <= y <= 2100:
                return str(y)
    for key in ("date", "release_date"):
        y = _year_from_date_field(meta.get(key))
        if y:
            return y

    entries = meta.get("entries") or []
    if entries:
        y = from_entry(entries[0])
        if y:
            return y

    for key in ("upload_date",):
        y = _year_from_date_field(meta.get(key))
        if y:
            return y
    return ""


def format_album_folder_name(meta):
    """Pełna nazwa podkatalogu: tytuł (+ opcjonalnie rok w nawiasie)."""
    if not meta:
        return ""
    base = playlist_folder_display_title(meta)
    if not base:
        base = (meta.get("title") or meta.get("album") or "").strip()
    year = _pick_release_year_from_playlist_meta(meta)
    if year and base:
        return f"{base} ({year})"
    return base


def resolve_album_playlist_url(album_query, source, cookies_from_browser=None):
    """
    Wyszukaj album i zwróć (url_playlisty, nazwa_podkatalogu) do wsadowego pobrania,
    albo None przy błędzie.
    """
    if source == "ytm":
        if not album_query.startswith(("http://", "https://")):
            print("[ERROR] --source ytm nie obsługuje wyszukiwania tekstowego albumu.")
            print("Podaj bezpośredni URL albumu/playlisty z music.youtube.com.")
            return None
        parsed = urlparse(album_query)
        if parsed.netloc != "music.youtube.com":
            print("[ERROR] --source ytm akceptuje tylko URL-e z music.youtube.com.")
            return None
        fallback = _fallback_title_from_playlist_url(album_query)
        try:
            # -j na URL playlisty daje wiele linii JSON (1/utwór) i psuje json.loads; -J = jeden obiekt.
            meta_cmd = (
                ["yt-dlp"]
                + yt_dlp_cookies_args(cookies_from_browser)
                + ["-J", "--no-download", album_query]
            )
            meta_json = run_command(meta_cmd)
            meta = json.loads(meta_json)
            raw_title = format_album_folder_name(meta) or meta.get("title") or ""
            subdir = safe_album_subdir_name(raw_title, fallback)
            print(f"   >>> Katalog wyjściowy: .../{subdir}/")
        except Exception as e:
            print(f"[WARN] Nie udało się odczytać tytułu playlisty: {format_noisy_floats(str(e))}")
            subdir = safe_album_subdir_name("", fallback)
            print(f"   >>> Katalog wyjściowy (fallback): .../{subdir}/")
        return (album_query, subdir)

    search_prefix = SOURCE_MAP.get(source, "ytsearch1")
    search_term = f"{search_prefix}:{album_query}"

    print(f"   >>> Szukam albumu: '{album_query}' ({source})...")
    try:
        meta_cmd = (
            ["yt-dlp"]
            + yt_dlp_cookies_args(cookies_from_browser)
            + ["-j", "--no-download", search_term]
        )
        meta_json = run_command(meta_cmd)
        meta = json.loads(meta_json)
    except Exception as e:
        print(f"[ERROR] Nie udało się znaleźć albumu: {format_noisy_floats(str(e))}")
        return None

    playlist_id = meta.get("playlist_id") or meta.get("playlist")
    album_name = meta.get("album", album_query)

    if not playlist_id:
        print(f"[ERROR] Nie znaleziono playlisty albumu dla: '{album_query}'")
        print("Spróbuj podać dokładniejszą nazwę albumu lub URL playlisty.")
        return None

    playlist_url = f"https://music.youtube.com/playlist?list={playlist_id}"
    # Wynik -j to często pojedynczy utwór — tytuł filmu nie jest nazwą albumu; bierzemy album + artystę.
    folder_meta = {
        "title": album_name,
        "album": album_name,
        "artist": meta.get("artist") or meta.get("album_artist") or meta.get("uploader"),
    }
    merged = dict(meta)
    merged.update(folder_meta)
    display = format_album_folder_name(merged) or album_name
    subdir = safe_album_subdir_name(display, album_query)
    print(f"   >>> Znaleziono album: '{album_name}' -> {playlist_url}")
    print(f"   >>> Katalog wyjściowy: .../{subdir}/")
    return (playlist_url, subdir)


def download_album_playlist(playlist_url, dest_dir, cookies_from_browser=None):
    """Jedno wywołanie yt-dlp: cała playlista do katalogu dest_dir."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = str(dest_dir / "%(playlist_index)02d_%(title)s.%(ext)s")
    dl_cmd = [
        "yt-dlp",
    ] + yt_dlp_cookies_args(cookies_from_browser) + [
        "--ignore-errors",
        "-x", "--audio-format", "mp3",
        "-f", "bestaudio",
        "--audio-quality", "0",
        "-o", output_pattern,
        "--embed-thumbnail",
        "--embed-metadata",
        "--parse-metadata", YT_ALBUM_PARSE_METADATA,
        "--restrict-filenames",
        "--no-mtime",
        playlist_url,
    ]
    # Playlisty często zawierają pozycje niedostępne (wiek, region) — yt-dlp i tak zwraca kod != 0.
    run_command(dl_cmd, verbose=True, check=False)


def list_album_mp3_files(dest_dir):
    """Posortowane ścieżki mp3 z katalogu pobrania (prefiks NN_)."""
    return sorted(Path(dest_dir).glob("*.mp3"))


def process_album_playlist(playlist_url, args, output_dir, job_index, total_jobs, album_subdir_name):
    """Pobierz playlistę wsadowo, potem Demucs dla każdego pliku jak dla pliku lokalnego."""
    album_out_dir = output_dir / album_subdir_name
    album_out_dir.mkdir(parents=True, exist_ok=True)

    tmp_root = output_dir / ".yt-batch-album-tmp"
    slug = hashlib.sha256(playlist_url.encode("utf-8")).hexdigest()[:16]
    work_dir = tmp_root / f"album_{slug}"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    print(f"\n[{job_index}/{total_jobs}] Album (playlist): {playlist_url}")
    print(f"   >>> Wyniki instrumentalne: {album_out_dir.resolve()}")
    try:
        download_album_playlist(
            playlist_url, work_dir, getattr(args, "cookies_from_browser", None)
        )
    except Exception as e:
        print(f"[FAIL] Błąd pobierania albumu: {format_noisy_floats(str(e))}")
        shutil.rmtree(work_dir, ignore_errors=True)
        return

    tracks = list_album_mp3_files(work_dir)
    if not tracks:
        print("[ERROR] Brak plików mp3 po pobraniu albumu.")
        if not args.keep_original:
            shutil.rmtree(work_dir, ignore_errors=True)
        return

    print(f"   >>> Pobrano {len(tracks)} utworów, separacja...")
    for i, track_path in enumerate(tracks, 1):
        print(f"\n   --- Utwór z albumu [{i}/{len(tracks)}]: {track_path.name} ---")
        process_local_file(track_path, i, len(tracks), args, album_out_dir)

    if not args.keep_original:
        shutil.rmtree(work_dir, ignore_errors=True)

def process_local_file(input_path, index, total, args, output_dir):
    """Separacja dla lokalnego pliku audio (bez pobierania). Obsługuje mp3, opus, m4a, wav, flac itd."""
    input_path = Path(input_path)
    if not input_path.exists():
        print(f"[ERROR] Plik nie istnieje: {input_path}")
        return

    base_name = input_path.stem
    selected_model = resolve_model(args.model)
    final_dest = output_dir / f"{base_name}-no-vocals.mp3"

    if final_dest.exists():
        print(f">>> [SKIP] Plik docelowy już istnieje: {final_dest.name}")
        return

    # Separacja (Demucs)
    device = get_demucs_device()
    print(f"   >>> Separacja (Model: {selected_model}, Shifts: {args.shifts})...")
    try:
        demucs_cmd = [
            "demucs",
            "-n", selected_model,
            "--shifts", str(args.shifts),
            "--two-stems=vocals",
            "--mp3",
            "--mp3-bitrate", str(args.quality),
            str(input_path.absolute())
        ]
        if device:
            demucs_cmd = ["demucs", "-d", device] + demucs_cmd[1:]
        run_command(demucs_cmd, verbose=True)
    except Exception as e:
        print(f"[FAIL] Demucs crashed: {format_noisy_floats(str(e))}")
        return

    # Przenoszenie i sprzątanie
    source_stem = Path("separated") / selected_model / base_name / "no_vocals.mp3"
    if source_stem.exists():
        shutil.move(str(source_stem), str(final_dest))
        copy_audio_metadata(input_path, final_dest)
        print(f">>> SUKCES: {final_dest}")
        shutil.rmtree("separated", ignore_errors=True)
        # Nie usuwamy oryginału — to plik użytkownika
    else:
        print(f"[WTF] Demucs zakończył pracę, ale nie widzę pliku: {source_stem}")


def process_item(query, index, total, args, output_dir):
    # Logika detekcji źródła
    if not query.startswith(("http://", "https://")):
        print(f"\n[{index}/{total}] Wyszukiwanie ({args.source}): '{query}'")
        if args.source == "ytm":
            dl_source = resolve_ytmusic_url(query)
            if not dl_source:
                return
        else:
            search_prefix = SOURCE_MAP.get(args.source, "ytsearch1")
            dl_source = f"{search_prefix}:{query}"
    else:
        print(f"\n[{index}/{total}] URL: {query}")
        if args.source == "ytm":
            parsed = urlparse(query)
            if parsed.netloc != "music.youtube.com":
                print("[ERROR] --source ytm akceptuje tylko URL-e z music.youtube.com.")
                return
        dl_source = query

    selected_model = resolve_model(args.model)
    cookie_spec = getattr(args, "cookies_from_browser", None)

    # 1. Pobieranie Metadanych (Nazwa pliku)
    try:
        name_cmd = (
            ["yt-dlp"]
            + yt_dlp_cookies_args(cookie_spec)
            + ["--get-filename"]
            + YT_COMMON_FLAGS
            + ["-x", "--audio-format", "mp3", dl_source]
        )
        filename = run_command(name_cmd)
        base_name = Path(filename).stem
        input_mp3 = Path(f"{base_name}.mp3")
        
        # Sprawdzenie czy wynik już istnieje w output
        final_dest = output_dir / f"{base_name}-no-vocals.mp3"
        if final_dest.exists():
            print(f">>> [SKIP] Plik docelowy już istnieje: {final_dest.name}")
            return

    except Exception as e:
        print(f"[ERROR] Nie udało się pobrać metadanych dla: {query}")
        print(f"Powód: {format_noisy_floats(str(e))}")
        return

    # 2. Pobieranie Audio
    if not input_mp3.exists():
        print(f"   >>> Pobieranie źródła ({args.quality}kbps)...")
        try:
            dl_cmd = (
                ["yt-dlp"]
                + yt_dlp_cookies_args(cookie_spec)
                + [
                    "-x", "--audio-format", "mp3",
                    "-f", "bestaudio",
                    "--audio-quality", "0",
                ]
                + YT_COMMON_FLAGS
                + [dl_source]
            )
            
            run_command(dl_cmd, verbose=True)
            
            # KRYTYCZNA WALIDACJA
            if not input_mp3.exists():
                raise FileNotFoundError(f"yt-dlp zgłosił sukces, ale plik {input_mp3} nie istnieje.")
                
        except Exception as e:
            print(f"[FAIL] Błąd pobierania: {format_noisy_floats(str(e))}")
            return
    else:
        print("   >>> Używam lokalnego pliku źródłowego (cache).")

    # 3. Separacja (Demucs)
    device = get_demucs_device()
    print(f"   >>> Separacja (Model: {selected_model}, Shifts: {args.shifts})...")
    try:
        demucs_cmd = [
            "demucs",
            "-n", selected_model,
            "--shifts", str(args.shifts),
            "--two-stems=vocals",
            "--mp3",
            "--mp3-bitrate", str(args.quality),
            str(input_mp3)
        ]
        if device:
            demucs_cmd = ["demucs", "-d", device] + demucs_cmd[1:]
        run_command(demucs_cmd, verbose=True)
    except Exception as e:
        print(f"[FAIL] Demucs crashed: {format_noisy_floats(str(e))}")
        # Sprzątamy wadliwy plik wejściowy, żeby nie blokował kolejnych prób
        if input_mp3.exists() and not args.keep_original:
            input_mp3.unlink()
        return

    # 4. Przenoszenie i Sprzątanie
    # Ścieżka generowana przez demucs: separated/<model>/<track>/no_vocals.mp3
    source_stem = Path("separated") / selected_model / base_name / "no_vocals.mp3"
    
    if source_stem.exists():
        shutil.move(str(source_stem), str(final_dest))
        copy_audio_metadata(input_mp3, final_dest)
        print(f">>> SUKCES: {final_dest}")
        
        # Sprzątanie tymczasowe
        shutil.rmtree("separated", ignore_errors=True)
        if not args.keep_original and input_mp3.exists():
            input_mp3.unlink()
    else:
        print(f"[WTF] Demucs zakończył pracę, ale nie widzę pliku: {source_stem}")

def main():
    global _cleanup_sigint_outdir

    check_dependencies()
    check_python_runtime()
    
    parser = argparse.ArgumentParser(description="Linus Audio Extractor v4.0 (Stable)")
    
    parser.add_argument("-i", "--input", help="Plik tekstowy z listą utworów")
    parser.add_argument("-f", "--folder", help="Folder z plikami audio do separacji (mp3, opus, m4a, wav, flac itd.)")
    parser.add_argument("query", nargs="*", help="Frazy, linki lub ścieżki do plików")
    
    # Parametry
    parser.add_argument("-m", "--model", default="1", help="Model: 1=htdemucs, 2=htdemucs_ft, 3=mdx_q, 4=mdx_extra")
    parser.add_argument("-o", "--outdir", default="output", help="Katalog wyjściowy")
    parser.add_argument("-q", "--quality", type=int, default=192, help="Bitrate (kbps)")
    parser.add_argument("-s", "--shifts", type=int, default=1, choices=[1, 2, 3, 4, 5], help="Passes (1-5)")
    parser.add_argument("-k", "--keep-original", action="store_true", help="Nie usuwaj pliku źródłowego")
    parser.add_argument(
        "-a",
        "--album",
        action="append",
        help="Album/playlista: ytm=wymaga URL z music.youtube.com; yt=nazwa do wyszukania. "
        "Wsadowe pobranie playlisty, wyniki w podkatalogu --outdir. Można podać wielokrotnie.",
    )
    parser.add_argument(
        "--source",
        default="ytm",
        choices=["ytm", "yt"],
        help="Źródło: ytm=YouTube Music search (domyślne), yt=YouTube search",
    )
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        default=None,
        help="Przekazuje do yt-dlp --cookies-from-browser (np. chrome). Pomaga przy age-gate, gdy jesteś zalogowany w tej przeglądarce.",
    )

    args = parser.parse_args()

    # Przygotowanie outputu
    out_path = Path(args.outdir)
    out_path.mkdir(parents=True, exist_ok=True)

    queue = []
    
    # Bezpieczne czytanie pliku (utf-8)
    if args.input:
        in_path = Path(args.input)
        if in_path.exists():
            try:
                with open(in_path, 'r', encoding='utf-8') as f:
                    queue.extend([l.strip() for l in f if l.strip()])
            except UnicodeDecodeError:
                print("Błąd: Plik wejściowy musi być zakodowany w UTF-8.")
                sys.exit(1)
        else:
            print(f"Błąd: Plik {args.input} nie istnieje.")
            sys.exit(1)

    if args.query:
        queue.extend(args.query)

    # Folder z plikami audio -> lista ścieżek
    if args.folder:
        folder_path = Path(args.folder)
        if not folder_path.is_dir():
            print(f"Błąd: Folder '{args.folder}' nie istnieje lub nie jest katalogiem.")
            sys.exit(1)
        for f in sorted(folder_path.iterdir()):
            if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
                queue.append(str(f.resolve()))

    album_jobs = []
    if args.album:
        for album_name in args.album:
            resolved = resolve_album_playlist_url(
                album_name, args.source, args.cookies_from_browser
            )
            if resolved:
                album_jobs.append(resolved)

    if not queue and not album_jobs:
        parser.print_help()
        sys.exit(1)

    _cleanup_sigint_outdir = out_path.resolve()

    total_jobs = len(queue) + len(album_jobs)

    device_info = get_demucs_device()
    device_msg = f"Device: {device_info}" if device_info else "Device: cpu (MPS niedostępne)"
    if not device_info and sys.platform == "darwin":
        device_msg += " — zobacz README sekcja Mac M1"
    print(
        f"--- Start v4.0 | Pozycji w kolejce: {total_jobs} "
        f"(utworów/plików: {len(queue)}, albumów: {len(album_jobs)}) | "
        f"Output: {out_path} | {device_msg} ---"
    )

    job_idx = 0
    for item in queue:
        job_idx += 1
        item_path = Path(item)
        if item_path.exists() and item_path.is_file():
            process_local_file(item_path, job_idx, total_jobs, args, out_path)
        else:
            process_item(item, job_idx, total_jobs, args, out_path)
        print("-" * 60)

    for playlist_url, album_subdir_name in album_jobs:
        job_idx += 1
        process_album_playlist(playlist_url, args, out_path, job_idx, total_jobs, album_subdir_name)
        print("-" * 60)

    _cleanup_sigint_outdir = None


if __name__ == "__main__":
    main()