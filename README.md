# Audio Stem Extractor (Linus Edition)

Narzędzie CLI do automatycznej separacji ścieżek instrumentalnych z YouTube (i innych źródeł) przy użyciu sieci neuronowych Demucs.

## 🛠 Wymagania Techniczne

System musi posiadać zainstalowane w `$PATH`:

1. **Python 3.9+**
2. **ffmpeg** (Kluczowe dla przetwarzania audio)
3. **yt-dlp** (Pobieranie źródeł)
4. **Demucs** (`pip install demucs`)

### Akceleracja Sprzętowa (Opcjonalne, ale zalecane)

- **NVIDIA:** Zainstalowane sterowniki CUDA + PyTorch w wersji CUDA.
- **MacOS (M1/M2/M3):** MPS (Metal) — skrypt automatycznie używa `-d mps` gdy dostępne. **Ważne:** PyTorch musi być wersja z MPS (nie CPU-only). Jeśli skrypt pokazuje "Device: cpu" na Apple Silicon, wykonaj:
  ```bash
  pip install --upgrade torch torchaudio
  ```
  Nie używaj `--extra-index-url https://download.pytorch.org/whl/cpu` — to instaluje wersję bez MPS.

## 🚀 Instalacja

```bash
# 1. Sklonuj repozytorium lub pobierz skrypt
# 2. Zainstaluj zależności Pythona
pip install yt-dlp demucs pytest

# 3. Zainstaluj ffmpeg (Ubuntu)
sudo apt update && sudo apt install ffmpeg

# 3. Zainstaluj ffmpeg (MacOS)
brew install ffmpeg
```

## ✅ Testy jednostkowe

Projekt ma testy jednostkowe w `pytest`, rozdzielone na moduły:

- `tests/test_helpers.py` - funkcje pomocnicze i warstwa komend
- `tests/test_process_local_file.py` - separacja plików lokalnych
- `tests/test_process_item.py` - pipeline dla query/URL
- `tests/test_main_cli.py` - wejście CLI i dispatch z `main`

Uruchamianie:

```bash
# Wszystkie testy
python3 -m pytest -q

# Pojedyncze moduły
python3 -m pytest -q tests/test_helpers.py
python3 -m pytest -q tests/test_process_local_file.py
python3 -m pytest -q tests/test_process_item.py
python3 -m pytest -q tests/test_main_cli.py
```

## 💻 Użycie

Podstawowe wywołanie (szuka na YT, pobiera, separuje, zapisuje w ./output):

```bash
python3 yt-batch.py "Nazwa Utworu"
```

Separacja lokalnego folderu (mp3, opus, m4a, wav, flac — Demucs obsługuje formaty wspierane przez ffmpeg):

```bash
python3 yt-batch.py -f ./moje-pliki-audio
```

## Flagi i Parametry

| Flaga             | Skrót | Opis                                                               | Domyślnie |
| ----------------- | ----- | ------------------------------------------------------------------ | --------- |
| `--model`         | `-m`  | Wybór modelu (1-4, patrz niżej)                                    | 1         |
| `--quality`       | `-q`  | Bitrate pliku wyjściowego (kbps)                                   | 192       |
| `--outdir`        | `-o`  | Katalog docelowy                                                   | ./output  |
| `--shifts`        | `-s`  | Liczba przesunięć (1=szybko, 2+=jakość)                            | 1         |
| `--keep-original` | `-k`  | Zachowaj oryginalny plik z wokalem                                 | False     |
| `--input`         | `-i`  | Plik .txt z listą linków/fraz                                      | -         |
| `--folder`        | `-f`  | Folder z plikami audio (mp3, opus, m4a, wav, flac itd.)            | -         |
| `--album`         | `-a`  | Nazwa albumu (pobiera wszystkie utwory). Można podać wielokrotnie. | -         |
| `--source`        |       | Źródło wyszukiwania: `ytm`=YouTube Music, `yt`=YouTube             | ytm       |

## Mapa Modeli (-m)

1. **htdemucs** (Domyślny) - Hybrid Transformer. Najlepszy balans prędkości do jakości.
2. **htdemucs_ft** (Fine-Tuned) - Wersja douczona. Lepsza separacja, to samo obciążenie obliczeniowe.
3. **mdx_extra_q** - Kwantyzowany model MDX. Lżejszy dla pamięci, "klasyczne" brzmienie.
4. **mdx_extra** - Pełny model MDX. Bardzo precyzyjny, ale wolniejszy i pamięciożerny.

## 📂 Struktura Wyjściowa

Skrypt automatycznie zarządza plikami tymczasowymi. Finalny plik ląduje w:

```
/output/Nazwa_Piosenki-no-vocals.mp3
```

## 📋 Formaty wejściowe (tryb -f)

Demucs korzysta z ffmpeg i obsługuje m.in.: **mp3**, **opus**, **m4a**, **m4b**, **wav**, **flac**, **ogg**, **aac**.

## 🐛 Rozwiązywanie problemów

- **Błąd ffmpeg not found:** Zainstaluj ffmpeg w systemie, nie przez pip.
- **Błąd CUDA out of memory:** Użyj modelu 3 (mdx_extra_q) lub ustaw zmienną środowiskową `PYTORCH_NO_CUDA_MEMORY_CACHING=1`.
- **Prędkość:** Na samym CPU proces trwa ok. 1-2 minuty na utwór. Na GPU/Metal - sekundy.
- **Mac M1 nadal CPU:** Zweryfikuj: `python3 -c "import torch; print('MPS:', torch.backends.mps.is_available())"`. Jeśli `False`, przeinstaluj PyTorch (patrz sekcja Akceleracja).
