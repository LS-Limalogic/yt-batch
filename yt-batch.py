import sys
import subprocess
import shutil
import argparse
from pathlib import Path

# --- KONFIGURACJA ---
REQUIRED_TOOLS = ["yt-dlp", "demucs", "ffmpeg"]

# Aliasy dla modeli - upraszczamy UX
MODEL_MAP = {
    "1": "htdemucs",        # Standard (Szybki, dobra jakość)
    "2": "htdemucs_ft",     # Fine-Tuned (Lepsza separacja, ten sam czas)
    "3": "mdx_extra_q",     # MDX Quantized (Klasyk, inny algorytm)
    "4": "mdx_extra"        # MDX Extra (Najcięższy, bardzo dokładny)
}

def check_dependencies():
    for tool in REQUIRED_TOOLS:
        if not shutil.which(tool):
            print(f"Błąd krytyczny: Nie znaleziono narzędzia '{tool}' w PATH.")
            sys.exit(1)

def run_command(cmd, verbose=False):
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
            print(f"[ERROR DETAILS] {e.stderr}")
        raise e

def resolve_model(model_arg):
    """Zamienia '1' na 'htdemucs' lub zwraca oryginalną nazwę."""
    return MODEL_MAP.get(str(model_arg), model_arg)

def process_item(query, index, total, args, output_dir):
    # Logika źródła
    if not query.startswith(("http://", "https://")):
        print(f"\n[{index}/{total}] Szukam: '{query}'")
        dl_source = f"ytsearch1:{query}"
    else:
        print(f"\n[{index}/{total}] URL: {query}")
        dl_source = query

    selected_model = resolve_model(args.model)
    print(f"   [Config] Model: {selected_model} | Bitrate: {args.quality}k | Output: {output_dir}")

    # 1. Pobieranie (yt-dlp)
    try:
        # Pobieramy nazwę
        name_cmd = [
            "yt-dlp", "--get-filename", "-o", "%(title)s.%(ext)s",
            "--restrict-filenames", "-x", "--audio-format", "mp3", dl_source
        ]
        filename = run_command(name_cmd)
        base_name = Path(filename).stem
        input_mp3 = Path(f"{base_name}.mp3") # Plik tymczasowy w root

        if not input_mp3.exists():
            print(">>> Pobieranie...")
            dl_cmd = [
                "yt-dlp", "-x", "--audio-format", "mp3", "-f", "bestaudio",
                "--audio-quality", "0",
                "-o", "%(title)s.%(ext)s", "--restrict-filenames", dl_source
            ]
            run_command(dl_cmd, verbose=True)
        
    except Exception:
        print(f"[SKIP] Błąd pobierania: {query}")
        return

    # 2. Separacja (Demucs)
    print(f">>> Separacja...")
    try:
        demucs_cmd = [
            "demucs", "-n", selected_model,
            "--shifts", str(args.shifts),
            "--two-stems=vocals", "--mp3", "--mp3-bitrate", str(args.quality),
            str(input_mp3)
        ]
        run_command(demucs_cmd, verbose=True)
    except Exception:
        print(f"[FAIL] Błąd Demucs dla: {input_mp3}")
        return

    # 3. Finalizacja
    # Demucs tworzy: separated/<model>/<track>/no_vocals.mp3
    source_stem = Path("separated") / selected_model / base_name / "no_vocals.mp3"
    
    # Przenosimy do folderu output
    dest_file = output_dir / f"no-vocals-{input_mp3.name}"

    if source_stem.exists():
        shutil.move(str(source_stem), str(dest_file))
        print(f">>> OK: {dest_file}")
        
        # Sprzątanie
        shutil.rmtree("separated", ignore_errors=True)
        if not args.keep_original and input_mp3.exists():
            input_mp3.unlink()
    else:
        print(f"[FAIL] Nie znaleziono wyniku w: {source_stem}")

def main():
    check_dependencies()
    parser = argparse.ArgumentParser(description="Linus Audio Extractor v3.0")
    
    parser.add_argument("-i", "--input", help="Plik z listą utworów")
    parser.add_argument("query", nargs="*", help="Frazy/Linki")
    
    # Nowe/Zmienione flagi
    parser.add_argument("-m", "--model", default="1", 
                        help="Wybór modelu: 1=htdemucs(std), 2=htdemucs_ft(hq), 3=mdx_q, 4=mdx_extra. Domyślnie: 1")
    parser.add_argument("-o", "--outdir", default="output", 
                        help="Katalog wyjściowy (Domyślnie: ./output)")
    
    parser.add_argument("-q", "--quality", type=int, default=192, help="Bitrate (kbps)")
    parser.add_argument("-s", "--shifts", type=int, default=1, help="Passes (1-5)")
    parser.add_argument("-k", "--keep-original", action="store_true", help="Zachowaj source mp3")

    args = parser.parse_args()

    # Przygotowanie katalogu output
    out_path = Path(args.outdir)
    out_path.mkdir(parents=True, exist_ok=True)

    queue = []
    if args.input and Path(args.input).exists():
        with open(args.input) as f: queue.extend([l.strip() for l in f if l.strip()])
    if args.query: queue.extend(args.query)

    if not queue:
        print("Brak danych wejściowych.")
        sys.exit(1)

    print(f"--- Start v3.0 | Kolejka: {len(queue)} | Output: {out_path} ---")
    for idx, item in enumerate(queue, 1):
        process_item(item, idx, len(queue), args, out_path)
        print("-" * 50)

if __name__ == "__main__":
    main()