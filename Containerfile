FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Mount /app/data as a volume so the cache survives container recreation.
# Without this, the bot re-uploads all images on every restart (~30-60s).
# With it, restarts are near-instant.
VOLUME ["/app/data"]

# Run as non-root
RUN useradd -r -s /bin/false botuser && \
    chown --recursive botuser:botuser /app

COPY --chown=botuser:botuser bot.py ffg_dice.py dice_image_gen.py generate_dice_images.py ./

USER botuser

# Pre-generate all dice face images at build time.
# These are baked into the image so the bot doesn't need Pillow at runtime
# (though it's still available for fallback rendering of non-standard dice).
RUN python generate_dice_images.py --output-dir /app/assets

# Create writable data directory for mxc:// cache persistence
RUN mkdir -p /app/data

ENV ASSETS_DIR=/app/assets
ENV CACHE_FILE=/app/data/mxc_cache.json

CMD ["python", "-u", "bot.py"]
