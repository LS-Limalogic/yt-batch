---
name: Niezależne wyszukiwanie YT Music
overview: Dodamy niezależną funkcję wyszukiwania YouTube Music opartą o ytmusicapi, która zamieni tekstowe zapytanie na URL i zasili obecny pipeline w yt-batch.py przez nową flagę CLI.
todos:
    - id: add-ytmusic-resolver
      content: Dodać izolowaną funkcję resolve_ytmusic_url z logiką song->video i budową URL
      status: completed
    - id: wire-ytm-search-flag
      content: Dodać flagę --ytm-search i podmianę query na URL przed process_item
      status: completed
    - id: docs-and-tests
      content: Zaktualizować README oraz testy jednostkowe/regresyjne dla nowej funkcjonalności
      status: completed
    - id: verify-end-to-end
      content: Uruchomić pytest i smoke test z --ytm-search --source ytm
      status: completed
isProject: false
---

# Niezależne wyszukiwanie YouTube Music → URL

## Cel

Dodać do projektu funkcjonalność, która dla tekstowego zapytania znajdzie utwór w YouTube Music i zwróci (oraz przekaże dalej) poprawny URL do istniejącego pipeline pobierania/separacji.

## Założenia (uzgodnione)

- Backend wyszukiwania: `ytmusicapi`.
- Integracja: nowa flaga CLI w głównym skrypcie [`/Users/luk452/dev/yt-batch/yt-batch.py`](/Users/luk452/dev/yt-batch/yt-batch.py).
- Strategia wyboru: preferuj wynik typu `song`, fallback do `video`.

## Zakres zmian

1. **Warstwa wyszukiwania YT Music (izolowana funkcja)**
    - W [`/Users/luk452/dev/yt-batch/yt-batch.py`](/Users/luk452/dev/yt-batch/yt-batch.py) dodać funkcję np. `resolve_ytmusic_url(query: str) -> str | None`.
    - Implementacja:
        - lazy import `YTMusic` (żeby przy `--source yt` nie wymuszać tej zależności),
        - `search(query, filter='songs', limit=1)` jako ścieżka główna,
        - fallback `search(query, filter='videos', limit=1)`,
        - budowanie URL-a z `videoId` w formacie `https://music.youtube.com/watch?v=<id>`.
    - Obsługa błędów: brak wyników / błąd API → czytelny komunikat i bezpieczny `return None`.

2. **Integracja z CLI i pipeline**
    - W [`/Users/luk452/dev/yt-batch/yt-batch.py`](/Users/luk452/dev/yt-batch/yt-batch.py):
        - dodać flagę `--ytm-search` (bool), działającą dla pozycyjnych `query` i `-i`.
        - przed `process_item(...)` transformować elementy kolejki: jeśli `--ytm-search` i element nie jest URL-em, wywołać `resolve_ytmusic_url(...)` i podmienić na zwrócony URL.
    - Zachować obecne reguły `--source ytm` (tylko URL `music.youtube.com`) — nowa flaga ma dostarczać właśnie taki URL.

3. **Zależności i dokumentacja**
    - Zaktualizować [`/Users/luk452/dev/yt-batch/README.md`](/Users/luk452/dev/yt-batch/README.md):
        - dodać `ytmusicapi` do instalacji,
        - dodać przykład użycia `--ytm-search`,
        - opisać, że flaga konwertuje tekst na URL YT Music i dopiero wtedy uruchamia standardowy pipeline.

4. **Testy regresji i jednostkowe**
    - Rozszerzyć testy w:
        - [`/Users/luk452/dev/yt-batch/tests/test_helpers.py`](/Users/luk452/dev/yt-batch/tests/test_helpers.py) – testy nowej funkcji resolvera (song → URL, fallback video, brak wyników, wyjątek API),
        - [`/Users/luk452/dev/yt-batch/tests/test_main_cli.py`](/Users/luk452/dev/yt-batch/tests/test_main_cli.py) – test, że `--ytm-search` zamienia query na URL przed dispatch do `process_item`,
        - [`/Users/luk452/dev/yt-batch/tests/test_process_item.py`](/Users/luk452/dev/yt-batch/tests/test_process_item.py) – potwierdzenie, że URL `music.youtube.com` przechodzi dalej bez odrzucenia.

## Weryfikacja

- Testy: `python3 -m pytest -q`
- Smoke test:
    - `python3 yt-batch.py "michael jackson billy jean" --ytm-search --source ytm`
- Oczekiwane:
    - query tekstowe zostaje zamienione na URL `music.youtube.com/watch?...`,
    - brak błędu o niedozwolonym text-search dla `ytm`,
    - pipeline uruchamia pobieranie z wygenerowanego URL.

## Ryzyka i zabezpieczenia

- `ytmusicapi` może zwracać wyniki zależne od regionu/treści — fallback `song -> video` minimalizuje puste wyniki.
- Dodatkowa zależność Python: lazy import + czytelny komunikat instalacyjny ogranicza impact na użytkowników, którzy używają tylko `--source yt`.
