---
name: Naprawa błędu hashlib/numpy
overview: Zdiagnozowano, że błąd wynika z problemu środowiska Python (pyenv 3.13) i brakującego numpy, a nie z logiki separacji audio. Plan obejmuje dodanie preflight-checków w CLI, testów jednostkowych i krótkiej dokumentacji naprawy środowiska.
todos:
    - id: add-runtime-preflight
      content: Dodać check_python_runtime() do yt-batch.py i podpiąć go w main()
      status: completed
    - id: add-runtime-tests
      content: Dodać testy helperów i main dla przypadków numpy/hashlib
      status: completed
    - id: update-readme-troubleshooting
      content: Dopisać instrukcję naprawy blake2/numpy w README
      status: completed
    - id: run-test-suite
      content: Uruchomić pytest i potwierdzić brak regresji
      status: completed
isProject: false
---

# Naprawa błędu środowiskowego Demucs/Torch

## Co już ustalone (root cause)

- Komunikaty `unsupported hash type blake2b/blake2s` pojawiają się już przy samym `import hashlib` w interpreterze `python3` (`/Users/luk452/.pyenv/versions/3.13.0`).
- Ostrzeżenie Torch `No module named 'numpy'` potwierdza brak wymaganej zależności runtime.
- Pipeline w [`/Users/luk452/dev/yt-batch/yt-batch.py`](/Users/luk452/dev/yt-batch/yt-batch.py) działa dalej, ale startuje w niestabilnym środowisku i emituje mylące błędy.

## Plan zmian w kodzie

1. Dodać w [`/Users/luk452/dev/yt-batch/yt-batch.py`](/Users/luk452/dev/yt-batch/yt-batch.py) funkcję preflight (np. `check_python_runtime()`), uruchamianą w `main()` zaraz po `check_dependencies()`:
    - sprawdza import `numpy`;
    - weryfikuje możliwość wywołania `hashlib.blake2b` i `hashlib.blake2s` (bez przerywania tracebackiem);
    - w przypadku problemu kończy skrypt czytelnym komunikatem z konkretnymi krokami naprawy (`pyenv reinstall`, `pip install numpy`).
2. Zachować prosty, kompatybilny mechanizm (bez nowych bibliotek), zgodny z obecną strukturą helperów i obsługą `SystemExit`.

## Plan testów

3. Rozszerzyć testy w [`/Users/luk452/dev/yt-batch/tests/test_helpers.py`](/Users/luk452/dev/yt-batch/tests/test_helpers.py):
    - test przejścia dla zdrowego runtime;
    - test błędu przy brakującym `numpy`;
    - test błędu przy niedostępnym BLAKE2.
4. Rozszerzyć testy w [`/Users/luk452/dev/yt-batch/tests/test_main_cli.py`](/Users/luk452/dev/yt-batch/tests/test_main_cli.py), aby potwierdzić, że `main()` wywołuje nowy preflight i kończy się kodem 1 przy niespełnionych warunkach.

## Plan dokumentacji

5. Uzupełnić sekcję troubleshooting w [`/Users/luk452/dev/yt-batch/README.md`](/Users/luk452/dev/yt-batch/README.md) o:
    - objaw `blake2b/blake2s` na Python 3.13;
    - szybkie kroki naprawy środowiska (przeinstalowanie Pythona przez `pyenv` i doinstalowanie `numpy`).

## Weryfikacja końcowa

6. Uruchomić testy jednostkowe (`python3 -m pytest -q`) i potwierdzić brak regresji.
7. Opcjonalnie: krótki smoke-check uruchomienia CLI bez obciążającej separacji (sama walidacja startowa).
