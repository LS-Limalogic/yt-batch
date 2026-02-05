import sys
import subprocess
import shutil
import argparse
import signal
from pathlib import Path

# --- KONFIGURACJA GLOBALNA ---
REQUIRED_TOOLS = ["yt-dlp", "demucs", "ffmpeg"]

# Mapowanie modeli (Aliasy)
MODEL_MAP = {
    "1": "htdemucs",        # Standard
    "2": "htdemucs_ft",     # High Quality
    "3": "mdx_extra_q",     # MDX Quantized
    "4": "mdx_extra"        # MDX Full
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

def resolve_model(model_arg):
    return MODEL_MAP.get(str(model_arg), model_arg)

def process_item(query, index, total, args, output_dir):
    # Logika detekcji źródła
    if not query.startswith(("http://", "https://")):
        print(f"\n[{index}/{total}] Wyszukiwanie: '{query}'")
        dl_source = f"ytsearch1:{query}"
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
        final_dest = output_dir / f"no-vocals-{input_mp3.name}"
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
    parser.add_argument("query", nargs="*", help="Frazy lub linki")
    
    # Parametry
    parser.add_argument("-m", "--model", default="1", help="Model: 1=htdemucs, 2=htdemucs_ft, 3=mdx_q, 4=mdx_extra")
    parser.add_argument("-o", "--outdir", default="output", help="Katalog wyjściowy")
    parser.add_argument("-q", "--quality", type=int, default=192, help="Bitrate (kbps)")
    parser.add_argument("-s", "--shifts", type=int, default=1, choices=[1, 2, 3, 4, 5], help="Passes (1-5)")
    parser.add_argument("-k", "--keep-original", action="store_true", help="Nie usuwaj pliku źródłowego")

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

    if not queue:
        parser.print_help()
        sys.exit(1)

    print(f"--- Start v4.0 | Utworów: {len(queue)} | Output: {out_path} ---")
    
    for idx, item in enumerate(queue, 1):
        process_item(item, idx, len(queue), args, out_path)
        print("-" * 60)

if __name__ == "__main__":
    main()