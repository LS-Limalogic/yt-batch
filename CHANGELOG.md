# Changelog

Format wg [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/). Projekt nie ma jeszcze numerowanych wydań — wpisy „wcześniej” są ułożone od najnowszego commita w `main`.

## [Unreleased]

### Added

- Flaga CLI `--cookies-from-browser` (np. `chrome`, `chrome:Default`) — przekazywana do wszystkich wywołań `yt-dlp` (pojedyncze utwory, metadane albumu, pobieranie playlisty), ułatwia treści z age-gate przy zalogowanej przeglądarce.
- Ponawianie wywołań `yt-dlp` przy błędach przejściowych (domyślnie 4 próby, backoff 3/6/12 s). Ponawiany jest cały proces, bo tylko to wymusza świeżą ekstrakcję adresów strumienia — własne `--retries` / `--extractor-retries` yt-dlp na HTTP 403 nie pomagają. Błędy trwałe (DRM, film prywatny/niedostępny, brak żądanego formatu) nie są ponawiane.
- Tryb `--album`: kilka przebiegów pobierania (domyślnie 3) z `--download-archive`, więc kolejny przebieg dobiera wyłącznie utwory, które padły. Na koniec porównanie z liczbą pozycji playlisty i ostrzeżenie, gdy czegoś brakuje — wcześniej `--ignore-errors` gubił takie utwory po cichu.

### Fixed

- Tryb `--album`: playlisty z pozycjami, których `yt-dlp` nie może pobrać (np. wiek bez logowania, usunięty film), nie kończą całego zadania błędem po częściowym pobraniu — używane jest `--ignore-errors`, a niezerowy kod wyjścia `yt-dlp` po pobraniu nie blokuje Demuksa, o ile w katalogu tymczasowym są pliki `.mp3`.
- Demucs pisze do katalogu tymczasowego systemu zamiast do `./separated` względem katalogu roboczego. Katalog jest usuwany także wtedy, gdy separacja padnie lub proces zostanie przerwany — wcześniej po błędzie zostawał w repozytorium.
- Plik źródłowy pobierany jest do `--outdir`, a nie do katalogu roboczego. Z `-k` zostaje więc obok wyniku, zamiast zaśmiecać katalog, z którego uruchomiono skrypt.

### Changed

- `run_command(..., check=True)` — opcjonalny `check=False` (ostrzeżenie zamiast wyjątku przy niezerowym kodzie w trybie verbose).

---

## Earlier changes (z historii gita)

### 2026-05-16

- Usunięcie nieużywanych plików audio z projektu (album Lucky).

### 2026-04-13

- Lepsze sprzątanie przy przerwaniu SIGINT (Ctrl+C).

### 2026-04-12

- Dokumentacja trybu albumu.
- Pobieranie albumu do podfolderu z nazwą z metadanych; numeracja plików z playlisty.

### 2026-04-07

- Lepsze komunikaty błędów i formatowanie (m.in. „hałasujące” floate w logach).
- Wyszukiwanie przez YouTube Music (`ytmusicapi`).
- `AGENTS.md`.
- Sprawdzenia środowiska Python (numpy, hashlib) przy starcie.
- Testy jednostkowe (`pytest`).

### 2026-02-21

- Python 3.13 (pyenv).
- Przetwarzanie plików z folderu (`-f` / `--folder`).
- Aktualizacje dokumentacji.

### 2026-02-09

- Wybór źródła (`ytm` / `yt`), tryb albumu, przyrostek `-no-vocals` w nazwach wyjścia.

### 2026-02-05 — 2026-01-05

- Docker / docker-compose (m.in. cache modeli Demucs, NVIDIA).
- README, parametry CLI, wczesne wersje skryptu (`1.0`, `2.0`).
