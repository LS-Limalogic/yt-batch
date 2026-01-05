import sys
import subprocess
import shutil
import argparse
from pathlib import Path

# Linusowa zasada: Fail fast. Sprawdzamy zależności na starcie.
REQUIRED_TOOLS = ["yt-dlp", "demucs", "ffmpeg"]
for tool in REQUIRED_TOOLS:
    if not shutil.which(tool):
        print(f"Błąd krytyczny: Nie znaleziono narzędzia '{tool}' w PATH.")
        sys.exit(1)

def run_command(cmd, verbose=False):
    """Wrapper na subprocess, żeby kod był czystszy."""
    try:
        # Jeśli verbose=True, pozwalamy na wyjście na ekran (np. pasek postępu yt-dlp)
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
        print(f"\n[BŁĄD] Komenda nie powiodła się: {' '.join(cmd)}")
        if e.stderr:
            print(f"Szczegóły: {e.stderr}")
        raise e

def process_item(query, index, total):
    """Przetwarza pojedynczy wpis (URL lub frazę)."""
    
    # Logika detekcji: Jeśli to nie URL, używamy ytsearch1:
    if not query.startswith(("http://", "https://")):
        print(f"\n[{index}/{total}] Tryb wyszukiwania dla frazy: '{query}'")
        dl_source = f"ytsearch1:{query}"
    else:
        print(f"\n[{index}/{total}] Tryb bezpośredniego linku: {query}")
        dl_source = query

    # 1. Pobieranie nazwy i pliku (yt-dlp)
    # Łączymy pobieranie nazwy i pliku w logiczną całość, aby uniknąć race conditions
    print(">>> Pobieranie źródła...")
    
    try:
        # Najpierw pobieramy nazwę pliku, jaka powstanie
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
        
        # Właściwe pobieranie
        download_cmd = [
            "yt-dlp",
            "-x", "--audio-format", "mp3",
            "-f", "bestaudio",
            "-o", "%(title)s.%(ext)s",
            "--restrict-filenames",
            dl_source
        ]
        run_command(download_cmd, verbose=True)
        
    except Exception:
        print(f"[POMINIĘTO] Nie udało się pobrać: {query}")
        return

    # 2. Separacja (Demucs)
    print(f">>> Separacja wokal/instrumental: {input_mp3}")
    try:
        demucs_cmd = [
            "demucs",
            "-n", "htdemucs",
            "--two-stems=vocals",
            "--mp3",
            "--mp3-bitrate", "320",
            input_mp3
        ]
        # To może potrwać, więc verbose=True
        run_command(demucs_cmd, verbose=True)
    except Exception:
        print(f"[BŁĄD] Demucs zawiódł dla pliku: {input_mp3}")
        return

    # 3. Finalizacja
    source_stem_path = Path("separated") / "htdemucs" / base_name / "no_vocals.mp3"
    final_output = Path(f"no-vocals-{input_mp3}")

    if source_stem_path.exists():
        shutil.move(str(source_stem_path), str(final_output))
        print(f">>> SUKCES: {final_output}")
        
        # Sprzątanie
        shutil.rmtree("separated", ignore_errors=True)
        if Path(input_mp3).exists():
            Path(input_mp3).unlink() # Usuwamy oryginał z wokalem
    else:
        print(f"[BŁĄD] Nie znaleziono pliku wynikowego dla {base_name}")

def main():
    parser = argparse.ArgumentParser(description="Batch Instrumental Extractor by Linus")
    parser.add_argument("-i", "--input", help="Plik tekstowy z listą (jedna fraza/link na linię)")
    parser.add_argument("query", nargs="*", help="Pojedyncze frazy lub linki podane w argumentach")
    
    args = parser.parse_args()

    queue = []

    # Czytanie z pliku
    if args.input:
        input_path = Path(args.input)
        if input_path.exists():
            with open(input_path, 'r', encoding='utf-8') as f:
                queue.extend([line.strip() for line in f if line.strip()])
        else:
            print(f"Błąd: Plik {args.input} nie istnieje.")
            sys.exit(1)

    # Czytanie z argumentów CLI
    if args.query:
        queue.extend(args.query)

    if not queue:
        print("Nie podano żadnych danych wejściowych. Użyj pliku (-i) lub argumentów.")
        print("Przykład: python3 batch_stem.py 'Metallica Enter Sandman' 'https://youtu.be/...'")
        sys.exit(1)

    total_items = len(queue)
    print(f"--- Rozpoczynam przetwarzanie wsadowe: {total_items} pozycji ---\n")

    for idx, item in enumerate(queue, 1):
        process_item(item, idx, total_items)
        print("-" * 40)

    print("\nZakończono przetwarzanie wsadowe.")

if __name__ == "__main__":
    main()