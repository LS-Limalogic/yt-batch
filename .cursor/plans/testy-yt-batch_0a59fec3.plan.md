---
name: testy-yt-batch
overview: Przygotuję zestaw testów jednostkowych dla całego `yt-batch.py` w `pytest`, z izolacją od narzędzi systemowych (`yt-dlp`, `demucs`, `ffmpeg`) przez mocki. Plan obejmuje krytyczne ścieżki sukcesu i błędów oraz bezpieczną refaktoryzację pod testowalność, jeśli będzie potrzebna.
todos:
    - id: setup-pytest-structure
      content: Dodać strukturę testów (`tests/`) i podział na kilka plików testowych zgodnie ze standardem `pytest`.
      status: completed
    - id: cover-core-functions
      content: Napisać testy jednostkowe dla funkcji pomocniczych i warstw komend (`check_dependencies`, `run_command`, `resolve_model`, `get_demucs_device`, `resolve_album_tracks`).
      status: completed
    - id: cover-processing-paths
      content: Dodać testy dla `process_local_file` i `process_item` obejmujące ścieżki sukcesu i błędów.
      status: completed
    - id: cover-main-entrypoint
      content: Przetestować `main` dla różnych wejść CLI i poprawnego dispatchu zadań.
      status: completed
    - id: verify-and-polish
      content: Uruchomić testy/lint i dopracować stabilność oraz czytelność zestawu testów.
      status: completed
isProject: false
---

# Plan testów jednostkowych `yt-batch.py`

## Zakres i podejście

- Cel: pokryć testami jednostkowymi cały przepływ logiki w [`/Users/luk452/dev/yt-batch/yt-batch.py`](/Users/luk452/dev/yt-batch/yt-batch.py) bez uruchamiania realnych procesów zewnętrznych.
- Framework: `pytest` + `unittest.mock`/`monkeypatch`.
- Strategia: testy skupione na zachowaniu funkcji (`run_command`, `resolve_album_tracks`, `process_local_file`, `process_item`, `main`) i decyzjach warunkowych.

## Pliki do dodania/zmiany

- Dodać: [`/Users/luk452/dev/yt-batch/tests/test_helpers.py`](/Users/luk452/dev/yt-batch/tests/test_helpers.py)
- Dodać: [`/Users/luk452/dev/yt-batch/tests/test_process_local_file.py`](/Users/luk452/dev/yt-batch/tests/test_process_local_file.py)
- Dodać: [`/Users/luk452/dev/yt-batch/tests/test_process_item.py`](/Users/luk452/dev/yt-batch/tests/test_process_item.py)
- Dodać: [`/Users/luk452/dev/yt-batch/tests/test_main_cli.py`](/Users/luk452/dev/yt-batch/tests/test_main_cli.py)
- Dodać: [`/Users/luk452/dev/yt-batch/tests/conftest.py`](/Users/luk452/dev/yt-batch/tests/conftest.py)
- (Opcjonalnie, tylko jeśli konieczne dla testowalności) Zmienić minimalnie: [`/Users/luk452/dev/yt-batch/yt-batch.py`](/Users/luk452/dev/yt-batch/yt-batch.py)

## Scenariusze testowe

- `check_dependencies`:
    - brak narzędzi -> komunikat + `sys.exit(1)`
    - wszystkie narzędzia dostępne -> brak wyjścia awaryjnego
- `run_command`:
    - sukces (`verbose=False`) -> zwrot `stdout.strip()`
    - sukces (`verbose=True`) -> poprawne parametry `subprocess.run`
    - `CalledProcessError` z `stderr` -> `RuntimeError` z treścią błędu
- `resolve_model` i `get_demucs_device`:
    - mapowanie modeli i fallback
    - gałąź z dostępnym MPS, bez MPS oraz wyjątek przy imporcie `torch`
- `resolve_album_tracks`:
    - poprawne metadane + lista URL-i -> zwrot listy
    - brak `playlist_id` -> pusta lista
    - wyjątek przy pobieraniu metadanych/listy -> pusta lista
- `process_local_file`:
    - plik nie istnieje
    - wynik docelowy już istnieje (skip)
    - sukces: wywołanie demucs, `shutil.move`, cleanup `separated`
    - błąd demucs / brak pliku `no_vocals.mp3`
- `process_item`:
    - gałąź query vs URL
    - błąd pobrania metadanych
    - pobieranie audio + walidacja istnienia pliku
    - awaria demucs z warunkowym kasowaniem źródła (`keep_original`)
    - sukces przeniesienia stemu + cleanup
- `main`:
    - pusta kolejka -> `print_help` + `sys.exit(1)`
    - wejście z `--input` (UTF-8 i błąd dekodowania)
    - wejście z `--folder` (niepoprawny folder i poprawne filtrowanie rozszerzeń)
    - wejście z `--album` (rozszerzenie kolejki)
    - dispatch: lokalny plik -> `process_local_file`, pozostałe -> `process_item`

## Implementacja testów

- Użyć `tmp_path` do plików/katalogów roboczych.
- Globalne side-effecty mockować per test (`subprocess.run`, `shutil.which`, `Path.exists`, `sys.exit`, `argparse` parsing).
- Dla `main` sterować `sys.argv` i mockować funkcje wykonawcze (`process_item`, `process_local_file`, `resolve_album_tracks`, `check_dependencies`).
- Mockować I/O i polecenia tak, by testy były deterministyczne i szybkie.
- Podział odpowiedzialności plików:
    - `test_helpers.py` -> `check_dependencies`, `run_command`, `resolve_model`, `get_demucs_device`, `resolve_album_tracks`
    - `test_process_local_file.py` -> gałęzie funkcji `process_local_file`
    - `test_process_item.py` -> gałęzie funkcji `process_item`
    - `test_main_cli.py` -> wejścia CLI i dispatch w `main`
    - `conftest.py` -> wspólne fixture'y (np. import modułu, fabryki `args`, pomocnicze mocki)

## Weryfikacja

- Uruchomić: `pytest -q`
- Dodatkowo uruchomić każdy moduł osobno:
    - `pytest -q tests/test_helpers.py`
    - `pytest -q tests/test_process_local_file.py`
    - `pytest -q tests/test_process_item.py`
    - `pytest -q tests/test_main_cli.py`
- Sprawdzić linter dla zmienionych plików i poprawić ewentualne nowe ostrzeżenia.

## Ryzyka i ograniczenia

- `yt-batch.py` jest modułem „monolitem”, więc część testów `main` może wymagać gęstszego mockowania.
- Jeśli testowalność okaże się niska, wykonam minimalną, bezpieczną refaktoryzację (bez zmiany zachowania) wyłącznie w celu uproszczenia testów.
