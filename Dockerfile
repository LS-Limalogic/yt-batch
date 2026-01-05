# Używamy lekkiego obrazu Python 3.10
FROM python:3.10-slim

# Ustawienia środowiskowe (nie twórz plików .pyc, loguj od razu na stdout)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instalacja ffmpeg (niezbędny dla demucs i yt-dlp)
# rm -rf czyści cache apt-a, żeby obraz był mniejszy
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Ustawienie katalogu roboczego
WORKDIR /app

# Instalacja zależności Pythonowych
# Używamy --no-cache-dir, żeby nie trzymać zbędnych plików instalacyjnych
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir yt-dlp demucs

# Kopiowanie skryptu do kontenera
COPY yt-batch.py /app/yt-batch.py

# Punkt wejścia - kontener działa jak plik wykonywalny
ENTRYPOINT ["python", "yt-batch.py"]

# Domyślne argumenty (można nadpisać w docker-compose lub CLI)
CMD ["--help"]