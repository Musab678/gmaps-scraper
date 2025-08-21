FROM python:3.11-slim

# System deps for Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libgbm1 libasound2 libxshmfence1 libx11-6 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgtk-3-0 libpango-1.0-0 \
    libpangocairo-1.0-0 libcairo2 fonts-liberation \
    wget unzip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium) + OS deps
RUN python -m playwright install --with-deps chromium

# Copy app source
COPY app.py /app/app.py

ENV PYTHONUNBUFFERED=1
ENV PORT=7860

EXPOSE 7860

CMD ["python", "app.py"]
