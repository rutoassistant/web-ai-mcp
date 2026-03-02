# Lightweight Python base
FROM python:3.11-slim

# Set environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99

# Install system dependencies for Playwright/Patchright and Xvfb
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11-utils \
    libgtk-3-0 \
    libgbm1 \
    libnss3 \
    libasound2 \
    libxtst6 \
    libxss1 \
    libx11-xcb1 \
    fonts-liberation \
    libappindicator3-1 \
    libxdamage1 \
    xdg-utils \
    libnspr4 \
    libdrm2 \
    libxcomposite1 \
    libxrandr2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libxshmfence1 \
    wget \
    curl \
    unzip \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install UV (fast, reliable)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy dependency files
COPY pyproject.toml uv.lock .python-version ./

# Create virtual environment and install dependencies via UV (include dev for tests)
RUN uv sync --frozen --all-extras

# Ensure the venv is used by default
ENV PATH="/app/.venv/bin:$PATH"

# Install Patchright browser binaries (Chromium only for stealth)
RUN patchright install chromium

# Copy application source code
COPY . .

# Clean any stale X11 lock and start Xvfb, then run the application
CMD ["/bin/sh", "-c", "rm -f /tmp/.X99-lock && Xvfb :99 -screen 0 1280x1024x24 & sleep 2 && python server.py"]
