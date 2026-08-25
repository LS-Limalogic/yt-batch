# Changelog

Format wg [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/). Projekt nie ma jeszcze numerowanych wydań — wpisy „wcześniej” są ułożone od najnowszego commita w `main`.

## [Unreleased]

### Added

- Flaga CLI `--cookies-from-browser` (np. `chrome`, `chrome:Default`) — przekazywana do wszystkich wywołań `yt-dlp` (pojedyncze utwory, metadane albumu, pobieranie playlisty). Z cookies `yt-dlp` używa klienta `web` zamiast flaky `android_vr`, więc to główny sposób na uporczywe HTTP 403; pomaga też przy age-gate.
- `--remote-components ejs:github` we wspólnych flagach `yt-dlp` — bez skryptu EJS challenge'e JS (signature/`n`) nie są rozwiązywane i YouTube oddaje same obrazki albo 403. Wymaga runtime'u JS (`deno`/`node`) w `PATH`. Argv każdego wywołania powstaje w `yt_dlp_base_cmd()`, więc flag nie da się pominąć; jedyny świadomy wyjątek to `count_playlist_entries` (`--flat-playlist` nie rozwija formatów).
- Ponawianie wywołań `yt-dlp` przy błędach przejściowych (domyślnie 4 próby, backoff 3/6/12 s). Ponawiany jest cały proces, bo tylko to wymusza świeżą ekstrakcję adresów strumienia — własne `--retries` / `--extractor-retries` yt-dlp na HTTP 403 nie pomagają. Błędy trwałe (DRM, film prywatny/niedostępny, brak żądanego formatu) nie są ponawiane.
- Tryb `--album`: kilka przebiegów pobierania (domyślnie 3) z `--download-archive`, więc kolejny przebieg dobiera wyłącznie utwory, które padły. Na koniec porównanie z liczbą pozycji playlisty i ostrzeżenie, gdy czegoś brakuje — wcześniej `--ignore-errors` gubił takie utwory po cichu.

### Fixed

- `--cookies-from-browser` nie połyka już kolejnego argumentu w ciszy. Flaga wymaga wartości, więc `--cookies-from-browser <URL>` zabierał URL jako nazwę przeglądarki, kolejka zostawała pusta i skrypt kończył się helpem bez wykonania roboty. Wartość jest teraz sprawdzana względem zamkniętej listy przeglądarek `yt-dlp`; cokolwiek innego wraca do kolejki jako utwór, z ostrzeżeniem i podpowiedzią poprawnej składni.
- Pusta kolejka kończy się jednozdaniowym komunikatem zamiast pełnego helpa. Help zostaje tam, gdzie nie podano żadnego wejścia (frazy, `-f`, `-i`, `-a`) — łatwiej zauważyć, co poszło nie tak.
- Błąd „nieznana opcja” z `yt-dlp` (za stara wersja, np. bez `--remote-components`) trafił do listy błędów trwałych, więc pada natychmiast zamiast po 4 próbach z backoffem na każdy utwór. Wzorzec to `no such option` — `yt-dlp` stoi na `optparse`, nie na `argparse`.
- Flaga pliku z listą utworów wskazująca na katalog kończy się czytelnym błędem z podpowiedzią, żeby użyć flagi folderu, zamiast wysypywać się na `IsADirectoryError` (walidacja sprawdzała tylko `exists()`, nie odróżniając pliku od katalogu).
- Katalog wyjściowy powstaje dopiero po walidacji argumentów — błędne wywołanie nie zostawia już pustego `./output` w katalogu roboczym.
- Tryb `--album`: playlisty z pozycjami, których `yt-dlp` nie może pobrać (np. wiek bez logowania, usunięty film), nie kończą całego zadania błędem po częściowym pobraniu — używane jest `--ignore-errors`, a niezerowy kod wyjścia `yt-dlp` po pobraniu nie blokuje Demuksa, o ile w katalogu tymczasowym są pliki `.mp3`.
- Demucs pisze do katalogu tymczasowego systemu zamiast do `./separated` względem katalogu roboczego. Katalog jest usuwany także wtedy, gdy separacja padnie lub proces zostanie przerwany — wcześniej po błędzie zostawał w repozytorium.
- Plik źródłowy pobierany jest do `--outdir`, a nie do katalogu roboczego. Z `-k` zostaje więc obok wyniku, zamiast zaśmiecać katalog, z którego uruchomiono skrypt.
- Tryb `--album` dostaje wspólne flagi `yt-dlp`. `download_album_playlist` powtarzało własną wklejkę `--restrict-filenames`/`--no-mtime`, więc `--remote-components ejs:github` do niego nie docierało i całe pobranie playlisty padało po cichu przez wszystkie przebiegi — na wyjściu było tylko `Pobrano 0/N`.
- Help `-a/--album` nie twierdzi już, że `ytm` wymaga URL-a z `music.youtube.com` — to ograniczenie zniknęło razem z przejściem `--source` na samo wyszukiwanie tekstowe.
- Ostrzeżenia o `--cookies-from-browser` idą na stdout, jak wszystkie pozostałe `[WARN]`/`[ERROR]` w skrypcie (wcześniej jako jedyne trafiały na stderr).

### Changed

- `--source` dotyczy wyłącznie **wyszukiwania tekstowego**. URL — pojedynczy utwór (`process_item`) i playlista (`--album`) — jest brany wprost, niezależnie od `--source`. Wcześniej domyślne `--source ytm` odrzucało każdy URL spoza `music.youtube.com`, więc zwykły link z `youtube.com` wymagał dopisania `--source yt`.
- **Breaking:** zamiana skrótów flag wejściowych — `-f/--file` to plik tekstowy z listą utworów (dawniej `-i/--input`), a `-i/--folder` to folder z plikami audio (dawniej `-f/--folder`). Długa nazwa `--input` została wycofana, więc stare wywołanie kończy się błędem argparse zamiast po cichu zrobić coś innego.
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
