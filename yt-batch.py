import sys
import subprocess
import shutil
import argparse
import os
from pathlib import Path

# Lista wymaganych narzędzi
REQUIRED_TOOLS = ["yt-dlp", "demucs", "ffmpeg"]

def check_dependencies():
    for tool in REQUIRED_TOOLS:
        if not shutil.which(tool):
            print(f"Błąd krytyczny: Nie znaleziono narzędzia '{tool}' w PATH.")
            sys.exit(1)

def run_command(cmd, verbose=False):
    """Wrapper na subprocess."""
    try:
        stdout_setting = None if verbose else subprocess.PIPE
        result = subprocess.run(
            cmd, 
            check=True, 
            stdout=stdout_setting, 
            stderr=subprocess.PIPE if not verbose else None, 
            text=True
        )
        return result.stdout.strip() if result.stdout else ""
    except subprocess.CalledProcessError as e:
        if not verbose and e.stderr:
            print(f"Szczegóły błędu: {e.stderr}")
        raise e

def process_item(query, index, total, args):
    """
    Główna logika przetwarzania pojedynczego utworu.
    Teraz przyjmuje obiekt 'args' z konfiguracją.
    """
    
    # Detekcja URL vs Fraza
    if not query.startswith(("http://", "https://")):
        print(f"\n[{index}/{total}] Szukam: '{query}'")
        dl_source = f"ytsearch1:{query}"
    else:
        print(f"\n[{index}/{total}] Link: {query}")
        dl_source = query

    print(f"   [Opcje] Bitrate: {args.quality}k | Model: {args.model} | Shifts: {args.shifts}")

    # 1. Pobieranie (yt-dlp)
    try:
        # Najpierw ustalamy nazwę
        get_name_cmd = [
            "yt-dlp",
            "--get-filename",
            "-o", "%(title)s.%(ext)s",
            "--restrict-filenames",
            "-x", "--audio-format", "mp3",
            dl_source
        ]
        filename = run_command(get_name_cmd)
        base_name = Path(filename).stem
        input_mp3 = f"{base_name}.mp3"
        
        # Jeśli plik już istnieje, pomijamy pobieranie (cache)
        if not Path(input_mp3).exists():
            print(">>> Pobieranie źródła...")
            download_cmd = [
                "yt-dlp",
                "-x", "--audio-format", "mp3",
                "-f", "bestaudio",
                "--audio-quality", "0", # Pobieramy w najlepszej możliwej jakości
                "-o", "%(title)s.%(ext)s",
                "--restrict-filenames",
                dl_source
            ]
            run_command(download_cmd, verbose=True)
        else:
            print(">>> Plik źródłowy już istnieje, pomijam pobieranie.")
        
    except Exception:
        print(f"[POMINIĘTO] Problem z pobraniem: {query}")
        return

    # 2. Separacja (Demucs)
    print(f">>> Separacja ({args.model})...")
    try:
        demucs_cmd = [
            "demucs",
            "-n", args.model,          # Wybór modelu
            "--shifts", str(args.shifts), # Ilość przesunięć (jakość vs czas)
            "--two-stems=vocals",
            "--mp3",
            "--mp3-bitrate", str(args.quality), # Bitrate wyjściowy
            input_mp3
        ]
        run_command(demucs_cmd, verbose=True)
    except Exception:
        print(f"[BŁĄD] Demucs zawiódł dla pliku: {input_mp3}")
        return

    # 3. Finalizacja i Sprzątanie
    source_stem_path = Path("separated") / args.model / base_name / "no_vocals.mp3"
    final_output = Path(f"no-vocals-{input_mp3}")

    if source_stem_path.exists():
        # Przeniesienie pliku wynikowego
        shutil.move(str(source_stem_path), str(final_output))
        print(f">>> GOTOWE: {final_output}")
        
        # Sprzątanie folderu demucs
        shutil.rmtree("separated", ignore_errors=True)
        
        # Obsługa flagi --keep-original
        if args.keep_original:
            print(f">>> Zachowano oryginał: {input_mp3}")
        else:
            if Path(input_mp3).exists():
                Path(input_mp3).unlink()
                print(">>> Usunięto plik źródłowy (z wokalem).")
    else:
        print(f"[BŁĄD] Nie znaleziono pliku wynikowego w {source_stem_path}")

def main():
    check_dependencies()

    parser = argparse.ArgumentParser(description="Advanced Instrumental Extractor v2.0")
    
    # Argumenty wejściowe
    parser.add_argument("-i", "--input", help="Plik tekstowy z listą utworów")
    parser.add_argument("query", nargs="*", help="Frazy lub linki bezpośrednie")
    
    # Nowe flagi konfiguracyjne
    parser.add_argument("-k", "--keep-original", action="store_true", 
                        help="Zachowaj oryginalny plik mp3 z wokalem (domyślnie: usuń)")
    
    parser.add_argument("-q", "--quality", type=int, default=192, 
                        help="Bitrate pliku wyjściowego w kbps (domyślnie: 192)")
    
    parser.add_argument("-m", "--model", type=str, default="htdemucs", 
                        help="Model Demucs: htdemucs, htdemucs_ft, mdx, mdx_extra (domyślnie: htdemucs)")
    
    parser.add_argument("-s", "--shifts", type=int, default=1, 
                        help="Liczba przesunięć dla poprawy jakości (1=szybko, 2+=lepiej). Domyślnie: 1")

    args = parser.parse_args()

    # Budowanie kolejki
    queue = []
    if args.input:
        if Path(args.input).exists():
            with open(args.input, 'r', encoding='utf-8') as f:
                queue.extend([line.strip() for line in f if line.strip()])
        else:
            print(f"Błąd: Nie znaleziono pliku {args.input}")
            sys.exit(1)
            
    if args.query:
        queue.extend(args.query)

    if not queue:
        print("Brak danych wejściowych. Użyj -h aby zobaczyć pomoc.")
        sys.exit(1)

    # Info o konfiguracji
    total = len(queue)
    print(f"--- Start v2.0 | Kolejka: {total} | Jakość: {args.quality}kbps | Keep: {args.keep_original} ---")

    for idx, item in enumerate(queue, 1):
        process_item(item, idx, total, args)
        print("-" * 50)

if __name__ == "__main__":
    main()