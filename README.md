# Audio Stem Extractor (Linus Edition)

Narzędzie CLI do automatycznej separacji ścieżek instrumentalnych z YouTube (i innych źródeł) przy użyciu sieci neuronowych Demucs.

## 🛠 Wymagania Techniczne

System musi posiadać zainstalowane w `$PATH`:

1. **Python 3.9+**
2. **ffmpeg** (Kluczowe dla przetwarzania audio)
3. **yt-dlp** (Pobieranie źródeł)
4. **Demucs** (`pip install demucs`)
5. **ytmusicapi** (dla źródła `--source ytm`)
6. **deno** lub **node** — runtime JS, którym `yt-dlp` rozwiązuje challenge'e YouTube (bez tego YouTube oddaje same obrazki albo HTTP 403)

### Akceleracja Sprzętowa (Opcjonalne, ale zalecane)

- **NVIDIA:** Zainstalowane sterowniki CUDA + PyTorch w wersji CUDA.
- **MacOS (M1/M2/M3):** MPS (Metal) — skrypt automatycznie używa `-d mps` gdy dostępne. **Ważne:** PyTorch musi być wersja z MPS (nie CPU-only). Jeśli skrypt pokazuje "Device: cpu" na Apple Silicon, wykonaj:
    ```bash
    uv pip install --upgrade torch torchaudio
    ```
    Nie używaj `--extra-index-url https://download.pytorch.org/whl/cpu` — to instaluje wersję bez MPS.

## 🚀 Instalacja

### MacOS (uv)

```bash
# 1. Zależności systemowe
brew install ffmpeg uv

# 2. Środowisko Pythona (uv odczyta wersję z .python-version)
cd yt-batch
uv venv

# 3. Zależności Pythona
uv pip install numpy yt-dlp demucs ytmusicapi pytest

# 4. Aktywacja (yt-dlp i demucs muszą być w PATH)
source .venv/bin/activate

# 5. Weryfikacja
python -c "import torch; print('MPS:', torch.backends.mps.is_available())"  # True na Apple Silicon
python -m pytest -q
```

Zamiast aktywacji venv można używać `uv run`, np. `uv run pytest -q` lub `uv run python yt-batch.py "..."`.

### Linux (pip)

```bash
sudo apt update && sudo apt install ffmpeg
pip install numpy yt-dlp demucs ytmusicapi pytest
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

Skrypt można uruchomić na dwa sposoby:

```bash
# Opcja 1: z aktywnym venv
source .venv/bin/activate
python3 yt-batch.py "Nazwa Utworu"

# Opcja 2: bez aktywacji, przez uv
uv run python yt-batch.py "Nazwa Utworu"
```

Podstawowe wywołanie (domyślnie szuka w YouTube Music, pobiera, separuje, zapisuje w ./output):

```bash
python3 yt-batch.py "Nazwa Utworu"
```

Separacja lokalnego folderu (mp3, opus, m4a, wav, flac — Demucs obsługuje formaty wspierane przez ffmpeg):

```bash
python3 yt-batch.py -i ./moje-pliki-audio
```

## Flagi i Parametry

| Flaga             | Skrót | Opis                                                               | Domyślnie |
| ----------------- | ----- | ------------------------------------------------------------------ | --------- |
| `--model`         | `-m`  | Wybór modelu (1-4, patrz niżej)                                    | 1         |
| `--quality`       | `-q`  | Bitrate pliku wyjściowego (kbps)                                   | 192       |
| `--outdir`        | `-o`  | Katalog docelowy                                                   | ./output  |
| `--shifts`        | `-s`  | Liczba przesunięć (1=szybko, 2+=jakość)                            | 1         |
| `--keep-original` | `-k`  | Zachowaj oryginalny plik z wokalem                                 | False     |
| `--file`          | `-f`  | Plik .txt z listą linków/fraz                                      | -         |
| `--folder`        | `-i`  | Folder z plikami audio (mp3, opus, m4a, wav, flac itd.)            | -         |
| `--album`         | `-a`  | Album/playlista (patrz [Tryb albumu](#tryb-albumu)). Można podać wielokrotnie. | -         |
| `--source`        |       | Źródło **wyszukiwania tekstowego**: `ytm`=YouTube Music, `yt`=YouTube. URL-e idą wprost, niezależnie od tej flagi. | ytm       |
| `--cookies-from-browser` |  | Cookies z przeglądarki dla `yt-dlp` (`chrome`, `firefox:Profil`, …). Główny sposób na HTTP 403. | -         |

## Mapa Modeli (-m)

1. **htdemucs** (Domyślny) - Hybrid Transformer. Najlepszy balans prędkości do jakości.
2. **htdemucs_ft** (Fine-Tuned) - Wersja douczona. Lepsza separacja, to samo obciążenie obliczeniowe.
3. **mdx_extra_q** - Kwantyzowany model MDX. Lżejszy dla pamięci, "klasyczne" brzmienie.
4. **mdx_extra** - Pełny model MDX. Bardzo precyzyjny, ale wolniejszy i pamięciożerny.

## Tryb albumu

- **URL playlisty/albumu** (dowolny — `music.youtube.com`, `youtube.com`) działa zawsze, bez ustawiania `--source`. Podaj link z `list=`: skrypt nie weryfikuje kształtu URL-a, a pojedynczy `watch?v=` przejdzie jako „album” z jednym utworem, którego plik dostanie prefiks `NA_` zamiast numeru (`%(playlist_index)02d` nie ma czego wypełnić). Do pojedynczych utworów użyj zwykłego argumentu, nie `-a`.
- **`--source ytm`** (domyślne) nie obsługuje wyszukiwania albumu po nazwie — do tego podaj `--source yt`.
- **`--source yt`:** podaj **nazwę albumu** — z pierwszego wyniku wyszukiwania wybierana jest playlista YouTube Music powiązana z albumem.
- Cała playlista jest pobierana **jednym** wywołaniem `yt-dlp` (numeracja plików `01_…`, osadzanie miniatury i metadanych), następnie każdy utwór przechodzi przez Demucs.
- Utwory, które padły na błąd przejściowy (typowo HTTP 403), są dobierane w **kolejnych przebiegach** (do 3). Dzięki `--download-archive` kolejny przebieg pomija to, co już się udało. Jeśli po wszystkich przebiegach czegoś brakuje, skrypt wypisuje ostrzeżenie `Pobrano X/Y utworów` — braki nie przechodzą po cichu.
- Instrumentale zapisywane są w **podkatalogu** katalogu docelowego (`--outdir`). Nazwa folderu pochodzi z metadanych: typowy wzorzec tytułu „Album - …” jest zamieniany na **„Artysta - …”**, jeśli artysta jest dostępny w metadanych; na końcu dodawany jest **rok wydania** w nawiasie `(RRRR)`, gdy yt-dlp zwróci datę / rok.
- Pobrane pliki źródłowe trzymane są w `{outdir}/.yt-batch-album-tmp/` (razem z `.yt-dlp-archive.txt`, które steruje pomijaniem przy kolejnych przebiegach). Bez `--keep-original` katalog tymczasowy dla danego albumu jest usuwany po przetworzeniu.

## 📂 Struktura Wyjściowa

Skrypt automatycznie zarządza plikami tymczasowymi.

**Pojedyncze utwory** (query, URL utworu, `-i`, itd.):

```
{outdir}/Nazwa_Piosenki-no-vocals.mp3
{outdir}/Nazwa_Piosenki.mp3          # tylko z -k (plik źródłowy z wokalem)
```

Pliki robocze Demucsa lądują w katalogu tymczasowym systemu i są usuwane także po błędzie lub Ctrl+C — nic nie zostaje w katalogu, z którego uruchomiono skrypt.

**Album (`-a`):**

```
{outdir}/{Folder_albumu}/NN_Tytul_Utworu-no-vocals.mp3
```

`Folder_albumu` jest bezpieczną nazwą z metadanych (patrz wyżej).

## 📋 Formaty wejściowe (tryb -f)

Demucs korzysta z ffmpeg i obsługuje m.in.: **mp3**, **opus**, **m4a**, **m4b**, **wav**, **flac**, **ogg**, **aac**.

## 🐛 Rozwiązywanie problemów

- **Tryb albumu kończy się `Pobrano 0/N utworów`:** najpierw sprawdź wersję `yt-dlp` (`yt-dlp --version`) i runtime JS. Pobieranie playlisty idzie przez `--ignore-errors`, więc yt-dlp nie przerywa pracy na błędzie — komunikat mówi „błąd sieci” nawet wtedy, gdy realną przyczyną jest za stary `yt-dlp` (`no such option: --remote-components`) albo brak `deno`/`node`.
- **`HTTP Error 403: Forbidden` przy pobieraniu:** znany problem YouTube — jedyny klient odtwarzacza działający bez tokenu PO (`android_vr`) sporadycznie odrzuca żądanie. Skrypt sam ponawia wywołanie (do 4 prób), ale **najskuteczniejsze jest `--cookies-from-browser chrome`** — z cookies `yt-dlp` używa klienta `web` zamiast flaky `android_vr` i 403 znika. Alternatywnie zainstaluj provider tokenów PO ([`bgutil-ytdlp-pot-provider`](https://github.com/Brainicism/bgutil-ytdlp-pot-provider)). Podnoszenie `--retries` w samym `yt-dlp` tu nie pomaga — ponowić trzeba całe wywołanie, żeby wymusić świeżą ekstrakcję adresów strumienia.
- **`Only images are available for download` / `Signature solving failed`:** `yt-dlp` nie ma czym rozwiązać challenge'y JS. Zainstaluj runtime JS (`brew install deno`). Skrypt sam dokłada `--remote-components ejs:github`, więc skrypt solvera pobiera się automatycznie z repozytorium `yt-dlp`.
- **Błąd ffmpeg not found:** Zainstaluj ffmpeg w systemie, nie przez pip.
- **Błąd CUDA out of memory:** Użyj modelu 3 (mdx_extra_q) lub ustaw zmienną środowiskową `PYTORCH_NO_CUDA_MEMORY_CACHING=1`.
- **Prędkość:** Na samym CPU proces trwa ok. 1-2 minuty na utwór. Na GPU/Metal - sekundy.
- **Mac M1 nadal CPU:** Zweryfikuj: `python3 -c "import torch; print('MPS:', torch.backends.mps.is_available())"`. Jeśli `False`, przeinstaluj PyTorch (patrz sekcja Akceleracja).
- **`unsupported hash type blake2b/blake2s` lub `No module named 'numpy'`:** to uszkodzone/niekompletne środowisko Pythona. Napraw przez odtworzenie venv: `rm -rf .venv && uv venv && uv pip install numpy yt-dlp demucs ytmusicapi pytest`, a na końcu weryfikacja `python3 -c "import hashlib, numpy; hashlib.blake2b(b'x')"`.
