import sys
import subprocess
import shutil
import argparse
import signal
import json
from pathlib import Path

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
    "ytm": "ytmusicsearch1",   # YouTube Music (default)
    "yt":  "ytsearch1",        # YouTube
}

# Wspólne flagi dla yt-dlp (DRY)
YT_COMMON_FLAGS = [
    "-o", "%(title)s.%(ext)s",
    "--restrict-filenames",
    "--no-mtime"  # Ważne: nie zmieniaj czasu modyfikacji pliku na czas uploadu filmu
]

def cleanup_handler(signum, frame):
    """Obsługa przerwania Ctrl+C."""
    print("\n\n!!! Przerwano przez użytkownika (SIGINT). Sprzątam i zamykam...")
    shutil.rmtree("separated", ignore_errors=True)
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

def run_command(cmd, verbose=False):
    """Wrapper na subprocess z lepszą obsługą błędów."""
    try:
        # Konwersja wszystkich elementów komendy na stringi (bezpieczeństwo typów)
        cmd_str = [str(c) for c in cmd]
        
        stdout_setting = None if verbose else subprocess.PIPE
        result = subprocess.run(
            cmd_str, 
            check=True, 
            stdout=stdout_setting, 
            stderr=subprocess.PIPE if not verbose else None, 
            text=True
        )
        return result.stdout.strip() if result.stdout else ""
    except subprocess.CalledProcessError as e:
        if not verbose and e.stderr:
            # Zwracamy stderr, żeby wyższa warstwa mogła go zalogować
            error_msg = e.stderr.decode('utf-8', errors='replace').strip() if isinstance(e.stderr, bytes) else e.stderr.strip()
            raise RuntimeError(f"Komenda nie powiodła się: {error_msg}")
        raise e

def copy_audio_metadata(metadata_source, audio_target):
    """
    Kopiuje metadane z pliku źródłowego do istniejącego pliku MP3.
    Audio pochodzi z audio_target, tagi z metadata_source.
    """
    metadata_source = Path(metadata_source)
    audio_target = Path(audio_target)
    temp_output = audio_target.with_suffix(f"{audio_target.suffix}.tmp")

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
        print(f"[WARN] Nie udało się skopiować metadanych do {audio_target.name}: {e}")
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


def resolve_album_tracks(album_query, source):
    """Wyszukaj album i zwróć listę URL-i do wszystkich utworów."""
    search_prefix = SOURCE_MAP.get(source, "ytmusicsearch1")
    search_term = f"{search_prefix}:{album_query}"

    # Krok 1: Znajdź pierwszy wynik i pobierz metadane JSON
    print(f"   >>> Szukam albumu: '{album_query}' ({source})...")
    try:
        meta_cmd = ["yt-dlp", "-j", "--no-download", search_term]
        meta_json = run_command(meta_cmd)
        meta = json.loads(meta_json)
    except Exception as e:
        print(f"[ERROR] Nie udało się znaleźć albumu: {e}")
        return []

    # Krok 2: Szukamy playlist_id (album na YT Music = playlist OLAK5uy_...)
    playlist_id = meta.get("playlist_id") or meta.get("playlist")
    album_name = meta.get("album", album_query)

    if not playlist_id:
        print(f"[ERROR] Nie znaleziono playlisty albumu dla: '{album_query}'")
        print("Spróbuj podać dokładniejszą nazwę albumu lub URL playlisty.")
        return []

    playlist_url = f"https://music.youtube.com/playlist?list={playlist_id}"
    print(f"   >>> Znaleziono album: '{album_name}' -> {playlist_url}")

    # Krok 3: Pobierz URL-e wszystkich utworów z playlisty
    try:
        tracks_cmd = ["yt-dlp", "--flat-playlist", "--print", "url", playlist_url]
        tracks_output = run_command(tracks_cmd)
        urls = [u.strip() for u in tracks_output.split('\n') if u.strip()]
        print(f"   >>> Znaleziono {len(urls)} utworów w albumie")
        return urls
    except Exception as e:
        print(f"[ERROR] Nie udało się pobrać listy utworów z albumu: {e}")
        return []

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
        print(f"[FAIL] Demucs crashed: {e}")
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
    search_prefix = SOURCE_MAP.get(args.source, "ytmusicsearch1")
    if not query.startswith(("http://", "https://")):
        print(f"\n[{index}/{total}] Wyszukiwanie ({args.source}): '{query}'")
        dl_source = f"{search_prefix}:{query}"
    else:
        print(f"\n[{index}/{total}] URL: {query}")
        dl_source = query

    selected_model = resolve_model(args.model)
    
    # 1. Pobieranie Metadanych (Nazwa pliku)
    try:
        name_cmd = ["yt-dlp", "--get-filename"] + YT_COMMON_FLAGS + ["-x", "--audio-format", "mp3", dl_source]
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
        print(f"Powód: {e}")
        return

    # 2. Pobieranie Audio
    if not input_mp3.exists():
        print(f"   >>> Pobieranie źródła ({args.quality}kbps)...")
        try:
            dl_cmd = [
                "yt-dlp", 
                "-x", "--audio-format", "mp3", 
                "-f", "bestaudio",
                "--audio-quality", "0"
            ] + YT_COMMON_FLAGS + [dl_source]
            
            run_command(dl_cmd, verbose=True)
            
            # KRYTYCZNA WALIDACJA
            if not input_mp3.exists():
                raise FileNotFoundError(f"yt-dlp zgłosił sukces, ale plik {input_mp3} nie istnieje.")
                
        except Exception as e:
            print(f"[FAIL] Błąd pobierania: {e}")
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
        print(f"[FAIL] Demucs crashed: {e}")
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
    check_dependencies()
    
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
    parser.add_argument("-a", "--album", action="append", help="Nazwa albumu (pobierz wszystkie utwory). Można podać wielokrotnie.")
    parser.add_argument("--source", default="ytm", choices=["ytm", "yt"], help="Źródło wyszukiwania: ytm=YouTube Music (domyślne), yt=YouTube")

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

    # Rozwiązywanie albumów -> lista URL-i
    if args.album:
        for album_name in args.album:
            track_urls = resolve_album_tracks(album_name, args.source)
            queue.extend(track_urls)

    if not queue:
        parser.print_help()
        sys.exit(1)

    device_info = get_demucs_device()
    device_msg = f"Device: {device_info}" if device_info else "Device: cpu (MPS niedostępne)"
    if not device_info and sys.platform == "darwin":
        device_msg += " — zobacz README sekcja Mac M1"
    print(f"--- Start v4.0 | Utworów: {len(queue)} | Output: {out_path} | {device_msg} ---")

    for idx, item in enumerate(queue, 1):
        item_path = Path(item)
        if item_path.exists() and item_path.is_file():
            process_local_file(item_path, idx, len(queue), args, out_path)
        else:
            process_item(item, idx, len(queue), args, out_path)
        print("-" * 60)

if __name__ == "__main__":
    main()